#!/usr/bin/env python3
"""
ABOUTME: Host-harness workflow state machine (`opendraft workflow init|next|finish`).
ABOUTME: The USER's harness (Claude Code, ZCode, Cursor, ... via its shell tool) asks
ABOUTME: "what's next?" after every step, and this module answers from DISK TRUTH
ABOUTME: (section_status.json, drafts/.ledger/, global_issues.md, checkpoint.json) —
ABOUTME: never from in-memory session state. The workflow, gates and guardrails live
ABOUTME: in code + disk; the host model only decides how to execute each task.
ABOUTME: There is NO budget/cost control here by design: the user's harness (or the
ABOUTME: user) owns run duration and aborts. --max-fix-rounds is an escalation policy
ABOUTME: (fix N rounds, then full-section rework), not a budget.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_tools.common import (  # noqa: E402
    SECTION_FILES,
    read_section_status,
    update_section_status,
    word_target_max,
)
from harness.acceptance import run_finish_acceptance  # noqa: E402
from harness.paper_map import seed_approved_lessons, write_paper_map  # noqa: E402
from harness.review_task import build_review_prompt  # noqa: E402
from harness.section_task import build_fix_prompt, build_section_prompt  # noqa: E402

DEFAULT_PAPER_SECTIONS = [
    "introduction",
    "literature_review",
    "methodology",
    "results",
    "discussion",
    "conclusion",
]

GLOBAL_ISSUES_NAME = "global_issues.md"

DEFAULT_MIN_FULL_SCORE = 75
DEFAULT_MAX_FIX_ROUNDS = 1

# Word targets for `workflow init --topic ...` on a checkpoint-less directory.
DEFAULT_WORD_TARGETS = {
    "introduction": "800-1200",
    "literature_review": "2000-3000",
    "methodology": "1500-2500",
    "results": "1500-2500",
    "discussion": "1500-2500",
    "conclusion": "600-1000",
}

# ------------------------------------------------------------- global-issue parsing

GI_HEADER_RE = re.compile(
    r"^##\s+(GI-\d+)\s*(?:\[([^\]]*)\])?(?:\s*scope:\s*([^\s]+))?", re.IGNORECASE
)
ISSUE_LINE_RE = re.compile(r"^Issue:\s*(.*)$", re.IGNORECASE)
FIX_LINE_RE = re.compile(r"^Suggested fix:\s*(.*)$", re.IGNORECASE)


def parse_global_issues(text: str) -> List[Dict]:
    """Parse global_issues.md into [{id, severity, scope, issue, fix}].

    Tolerant by design: missing severity defaults to medium, missing scope to global,
    missing Suggested fix to "", paragraphs without a GI header are ignored.
    """
    issues: List[Dict] = []
    if not text:
        return issues
    current: Optional[Dict] = None
    for raw in text.splitlines():
        line = raw.strip()
        m = GI_HEADER_RE.match(line)
        if m:
            if current is not None:
                issues.append(current)
            severity = (m.group(2) or "medium").strip().lower() or "medium"
            scope = (m.group(3) or "global").strip() or "global"
            current = {
                "id": m.group(1),
                "severity": severity,
                "scope": scope,
                "issue": "",
                "fix": "",
            }
            continue
        if current is None:
            continue
        im = ISSUE_LINE_RE.match(line)
        if im:
            current["issue"] = im.group(1).strip()
            continue
        fm = FIX_LINE_RE.match(line)
        if fm:
            current["fix"] = fm.group(1).strip()
    if current is not None:
        issues.append(current)
    return [i for i in issues if i["issue"] or i["fix"]]


def group_issues_by_section(
    issues: List[Dict], planned: List[str]
) -> Tuple[Dict[str, List[Dict]], List[str]]:
    """Bucket issues per section. scope: <section> goes to that section; scope: global is
    distributed to the sections its Suggested fix names (word-boundary match); anything
    unresolvable is skipped with a note."""
    groups: Dict[str, List[Dict]] = {}
    notes: List[str] = []
    for it in issues:
        scope = it.get("scope", "global")
        if scope == "global":
            named = [
                s
                for s in planned
                if re.search(rf"\b{re.escape(s)}\b", it.get("fix") or "", re.IGNORECASE)
            ]
            if not named:
                notes.append(
                    f"{it['id']}: skipped — global-scope issue names no section in its fix"
                )
                continue
            targets = named
        elif scope in SECTION_FILES:
            targets = [scope]
        else:
            notes.append(f"{it['id']}: skipped — unknown scope '{scope}'")
            continue
        for t in targets:
            if t not in planned:
                notes.append(f"{it['id']}: skipped — '{t}' is not in this run's plan")
                continue
            groups.setdefault(t, []).append(it)
    return groups, notes


# ------------------------------------------------------------------ CLI adapter header

TOOL_NAMES = [
    "read_artifact",
    "write_section",
    "score_draft",
    "search_literature",
    "verify_claims",
    "revise_section",
    "compile_draft",
    "write_outline",
    "manage_claims",
]

CLI_ADAPTER_HEADER = """You are driving the OpenPaper tool CLI through your shell. Every
"tool call" named below (read_artifact, write_section, ...) is a shell command:

    opendraft tool <name> --root . --args '<json>'

Rules of engagement:
- Always run commands from the paper's output directory (the `--root .` above), and
  read files through `read_artifact`, not your own file tools, so path guardrails apply.
- Every command prints exactly ONE JSON envelope line: {"ok": true, "data": ...} or
  {"ok": false, "error": "...", "is_retryable": bool}. ok=false is feedback, not a
  crash: fix the arguments and retry per the error message.
- Long JSON arguments (e.g. write_section's content) are painful to inline — write the
  args to a temp file and use `--args-file`:
    opendraft tool write_section --root . --args-file /tmp/args.json
- `opendraft tool list` shows every tool; `opendraft tool <name> --schema` shows one
  tool's input schema.
- Do NOT write section files with your own file-write tools: write_section's guardrails
  (citation whitelist, word floor, placeholder rejection) only run through the CLI.
"""


def cli_prompt(body: str) -> str:
    """Wrap a pi-style task prompt with the CLI adapter header."""
    return CLI_ADAPTER_HEADER + "\n" + body


# ------------------------------------------------------------------------- helpers


def _section_is_done(root: Path, section: str) -> bool:
    entry = (read_section_status(root).get("sections") or {}).get(section)
    if not isinstance(entry, dict):
        return False
    return entry.get("status") in ("written", "revised") and entry.get("passed") is True


def plan_sections(root: Path) -> List[str]:
    """Outline-order sections; appendices join only when its word target is real."""
    planned = list(DEFAULT_PAPER_SECTIONS)
    if word_target_max(root, SECTION_FILES["appendices"]["wt_key"]) > 0:
        planned.append("appendices")
    return planned


def _inventory(root: Path) -> Dict:
    """What the host agent has to work with (drives init's guidance)."""
    checks = {
        "checkpoint": root / "checkpoint.json",
        "outline": root / "drafts" / "00_formatted_outline.md",
        "bibliography": root / "research" / "bibliography.json",
        "research_notes": root / "research" / "combined_research.md",
    }
    missing = [name for name, p in checks.items() if not p.exists()]
    if not (root / "research" / "papers").is_dir():
        missing.append("paper_notes")
    return {
        "present": [name for name in checks if name not in missing],
        "missing": missing,
        "sections_done": [s for s in plan_sections(root) if _section_is_done(root, s)],
        "planned": plan_sections(root),
    }


# ----------------------------------------------------------------------------- init


def workflow_init(root, topic: Optional[str] = None, language: str = "en") -> Dict:
    """Prepare the directory for a CLI-mode run: minimal checkpoint when a topic is
    given (and none exists), approved-lesson seeding, and a fresh AGENTS.md paper map.
    Idempotent — safe to re-run."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    checkpoint_state = "present"
    ckpt = root / "checkpoint.json"
    if not ckpt.exists():
        if topic:
            import json

            ckpt.write_text(
                json.dumps(
                    {
                        "topic": topic,
                        "academic_level": "research_paper",
                        "citation_style": "apa",
                        "language": language,
                        "word_targets": dict(DEFAULT_WORD_TARGETS),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            checkpoint_state = "created"
        else:
            checkpoint_state = "absent"

    lessons = seed_approved_lessons(root)
    paper_map = write_paper_map(root)

    inv = _inventory(root)
    return {
        "root": str(root),
        "paper_map": str(paper_map),
        "checkpoint": checkpoint_state,
        "lessons_seeded": lessons,
        "inventory": inv,
        "next": "opendraft workflow next --root .",
    }


# ----------------------------------------------------------------------------- next


def workflow_next(root, max_fix_rounds: int = DEFAULT_MAX_FIX_ROUNDS) -> Dict:
    """Return the next task for the host agent, decided entirely from disk state.
    Order: pending sections → global review → per-section fixes → finish gate.
    Never raises; unexpected states degrade into readable tasks."""
    root = Path(root)
    if not (root / "checkpoint.json").exists() and not (root / "AGENTS.md").exists():
        return {
            "phase": "uninitialized",
            "prompt": (
                "This directory has no checkpoint.json and no AGENTS.md paper map.\n"
                'Run `opendraft workflow init --root . --topic "<topic>"` first '
                "(or bring a research/ directory from your own pipeline), then call "
                "`opendraft workflow next --root .` again."
            ),
        }

    # Refresh the paper map so the host agent always sees current disk state.
    write_paper_map(root)
    planned = plan_sections(root)

    issues_path = root / GLOBAL_ISSUES_NAME
    if not issues_path.exists():
        # Pre-review world: write sections in outline order, then review once.
        for section in planned:
            if not _section_is_done(root, section):
                return {
                    "phase": "sections",
                    "section": section,
                    "prompt": cli_prompt(build_section_prompt(root, section)),
                    "hint": (
                        "Execute the task, then call `opendraft workflow next --root .` "
                        "to receive the next one."
                    ),
                }
        return {
            "phase": "review",
            "prompt": cli_prompt(build_review_prompt(root))
            + (
                "\nDeliverable: write your final issue list to `global_issues.md` in "
                "this directory (plain file write), using exactly the `## GI-N "
                "[severity] scope: <section>` heading format from the instructions. "
                "If everything is consistent, write the no-issues text instead. "
                "Then call `opendraft workflow next --root .`."
            ),
            "hint": "The review's findings drive the fix phase; the file must exist either way.",
        }

    # Post-review world: targeted fixes first (round-limited per section; a passing
    # on-disk re-score closes one), then full-section rework for anything still
    # not passing, and only then the finish gate.
    issues = parse_global_issues(issues_path.read_text(encoding="utf-8"))
    groups, notes = group_issues_by_section(issues, planned)
    for section, sec_issues in groups.items():
        entry = (read_section_status(root).get("sections") or {}).get(section) or {}
        rounds = int(entry.get("fix_rounds") or 0)
        if entry.get("passed") is True and rounds >= 1:
            continue  # fixed and confirmed on disk
        if rounds >= max_fix_rounds:
            continue  # fix budget spent -> the rework loop below picks it up
        update_section_status(root, section, fix_rounds=rounds + 1)
        return {
            "phase": "fixes",
            "section": section,
            "issues": sec_issues,
            "fix_round": rounds + 1,
            "prompt": cli_prompt(build_fix_prompt(root, section, sec_issues))
            + (
                "\nThen call `opendraft workflow next --root .` — the section is "
                "only confirmed fixed when its on-disk re-score passes."
            ),
            "hint": f"fix round {rounds + 1}/{max_fix_rounds} for this section",
        }

    # Rework: any planned section still not written-and-passed gets a full
    # section task again (fix rounds were spent or it never passed). Host mode
    # has no cost breaker — the user watches the loop and aborts when it stops
    # making progress.
    for section in planned:
        if not _section_is_done(root, section):
            return {
                "phase": "sections",
                "section": section,
                "rework": True,
                "prompt": cli_prompt(build_section_prompt(root, section))
                + "\n(This is a REWORK pass: earlier attempts or fix rounds did not "
                "leave this section passing on disk. Read score_draft's issues in "
                "section_status.json and AGENTS.md before rewriting.)",
                "hint": "rework dispatch — the finish gate runs only when this passes",
            }

    # Finish gate (offline; failing gaps come back as remediation instructions).
    return _finish_task(root, notes)


def _finish_task(root: Path, notes: Optional[List[str]] = None) -> Dict:
    """Run the full score + finish acceptance and shape it as the next task."""
    from agent_tools.score import run as score_run

    score = score_run({"scope": "full"}, root)
    full_score = score.get("data", {}).get("total") if score.get("ok") else None
    gate = run_finish_acceptance(root, min_full_score=DEFAULT_MIN_FULL_SCORE, full_score=full_score)

    base = {
        "phase": "finish",
        "full_score": full_score,
        "min_full_score": DEFAULT_MIN_FULL_SCORE,
        "passed": gate.passed,
        "gaps": list(gate.gaps) + list(notes or []),
        "claims_clean": gate.claims_clean,
        "citation_rate": gate.citation_rate,
        "forbidden_hits": len(gate.forbidden_hits),
    }
    if gate.passed:
        base["phase"] = "done"
        base["prompt"] = (
            "Finish gate PASSED. Remaining optional step:\n"
            "- compile the paper: `opendraft tool compile_draft --root . "
            '--args \'{"format": "all"}\'`\n'
            "Report the exported paths to the user."
        )
        return base

    base["prompt"] = cli_prompt(
        "The paper FAILED the finish gate. Gaps (each must be closed on disk):\n"
        + "\n".join(f"- {g}" for g in base["gaps"])
        + "\n\nRemediate with the tool CLI (revise_section / write_section for word "
        "floors, manage_claims action=resolve for CONTRADICTED claims, "
        "search_literature + rewrite for unknown citations), then call "
        "`opendraft workflow next --root .` to re-run the gate."
    )
    return base


# --------------------------------------------------------------------------- finish


def workflow_finish(root, min_full_score: Optional[int] = None) -> Dict:
    """Explicit finish-gate invocation: full 100-point score + acceptance checks."""
    root = Path(root)
    from agent_tools.score import run as score_run

    score = score_run({"scope": "full"}, root)
    full_score = score.get("data", {}).get("total") if score.get("ok") else None
    gate = run_finish_acceptance(
        root,
        min_full_score=min_full_score if min_full_score is not None else DEFAULT_MIN_FULL_SCORE,
        full_score=full_score,
    )
    return {
        "passed": gate.passed,
        "full_score": full_score,
        "min_full_score": min_full_score if min_full_score is not None else DEFAULT_MIN_FULL_SCORE,
        "claims_clean": gate.claims_clean,
        "unresolved_contradicted": len(gate.unresolved_contradicted),
        "forbidden_hits": len(gate.forbidden_hits),
        "citation_rate": gate.citation_rate,
        "missing_sections": gate.missing_sections,
        "thin_sections": gate.thin_sections,
        "gaps": gate.gaps,
    }
