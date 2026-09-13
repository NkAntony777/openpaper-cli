#!/usr/bin/env python3
"""
ABOUTME: Blind review panel for the workflow's review phase — the host harness
ABOUTME: spawns one independent subagent per seat (fresh context each), seats
ABOUTME: commit findings to reviews/<seat>.md without seeing each other, and a
ABOUTME: synthesis step (main agent) merges them into global_issues.md under
ABOUTME: iron rules: every finding traces to a seat, the synthesizer invents
ABOUTME: nothing, and Devil's-Advocate CRITICALs must be visibly adjudicated.
ABOUTME: Borrowed from the academic-paper-reviewer panel pattern; role
ABOUTME: separation is a perspective device, not a claim of independent error
ABOUTME: processes — the provenance of each report stays on disk.
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.review_task import (  # noqa: E402
    GLOBAL_ISSUES_HEADING,
    LEDGER_DIR_REL,
    NO_ISSUES_TEXT,
    STATUS_REL,
    _ledger_summaries,
    _status_digest,
)

REVIEWS_DIR_REL = "reviews"
ADJUDICATION_REL = f"{REVIEWS_DIR_REL}/adjudication.md"

# seat id -> review angle (fixed panel; the synthesis layer is the fifth view)
SEAT_FOCUS = {
    "methodology": (
        "Research design and claims-evidence chains. Check: does every strong "
        "claim carry support (citation, data, or explicit hedging); are the "
        "methodology/results/discussion internally consistent; are quantitative "
        "statements sound and reproducible; does any claim outrun its evidence?"
    ),
    "domain": (
        "Literature coverage and contribution. Check: does the bibliography "
        "cover what the outline promises; which key threads are missing (suggest "
        "concrete search queries — NEVER invent citations); is the theoretical "
        "framing coherent; what is the actual contribution and is it stated "
        "honestly?"
    ),
    "coherence": (
        "Cross-section coherence. Check: terminology/symbol consistency; the "
        "narrative line (introduction promises vs sections deliver vs conclusion "
        "echoes); redundancy and contradictions between sections; citation "
        "consistency; outline conformance; unresolved claims-ledger entries."
    ),
    "devils_advocate": (
        "Adversarial challenge. Produce the STRONGEST counter-argument to the "
        "paper's core claim (200-300 words), then: overclaims, cherry-picking, "
        "logic gaps, ignored alternative explanations, and a 'so what?' test. "
        "Mark as CRITICAL any issue that, if valid, undermines the core claim."
    ),
}

SEAT_ORDER = list(SEAT_FOCUS)


def seats_reported(root: Path) -> List[str]:
    """Seat ids whose report file exists on disk (panel progress = disk truth)."""
    d = Path(root) / REVIEWS_DIR_REL
    if not d.is_dir():
        return []
    return [s for s in SEAT_ORDER if (d / f"{s}.md").is_file()]


def _common_material(root: Path) -> List[str]:
    root = Path(root)
    material = [
        "- `AGENTS.md` — the paper map (outline digest, per-section status, summaries).",
        f"- `{STATUS_REL}` — the machine-readable status ledger.",
        "- Section drafts under `drafts/` and, when relevant, the claims ledger "
        f"`{LEDGER_DIR_REL}/*.claims.jsonl`.",
    ]
    summaries = _ledger_summaries(root)
    if summaries:
        material.append("- Section summaries (read each): " + ", ".join(summaries))
    return material


def seat_card(root, seat: str) -> str:
    """The self-contained brief one subagent receives. Raises KeyError for
    unknown seats."""
    root = Path(root)
    if seat not in SEAT_FOCUS:
        raise KeyError(f"unknown review seat: {seat} (valid: {SEAT_ORDER})")
    digest = _status_digest(_read_status(root))
    digest_block = "\n".join(f"- {ln}" for ln in digest) or "(status ledger empty)"

    return (
        "\n".join(
            [
                f"BLIND REVIEW PANEL — seat: {seat}",
                "",
                "You are one seat of a blind review panel for the academic paper in this "
                "directory. Review it ONLY from your assigned angle below.",
                "",
                f"Your angle: {SEAT_FOCUS[seat]}",
                "",
                "Material to read first:",
                *_common_material(root),
                "",
                "Current status digest (from the ledger):",
                digest_block,
                "",
                "IRON RULES:",
                "1. READ-ONLY: never edit the paper, ledgers, or other reviews. Your ONLY "
                f"write is your report file `{REVIEWS_DIR_REL}/{seat}.md`.",
                "2. BLIND: do not read other seats' reports — commit your own findings "
                "first. Overlap with other seats is expected and fine; do not self-censor "
                "(deduplication happens at synthesis).",
                "3. SPECIFIC: every finding states severity (critical/major/minor), the "
                "section or location, what is wrong, and a suggested fix. Generic "
                "feedback ('the methodology could be stronger') is forbidden.",
                "4. BALANCED: note genuine merits in one short paragraph — no manufactured "
                "severity, no finding quotas.",
                "5. This role separation is a perspective device, not a claim of "
                "independent error processes. Never invent citations; suggest search "
                "queries instead.",
                "",
                "Report format (markdown):",
                f"# Review — {seat}",
                "",
                "## Merits",
                "<short paragraph>",
                "",
                "## Findings",
                "### [severity] <one-line title>",
                "- Section: <section or location>",
                "- Problem: <what is wrong>",
                "- Suggested fix: <concrete fix>",
                "(repeat per finding; zero findings is a valid result — say so explicitly)",
            ]
        )
        + "\n"
    )


def _read_status(root: Path) -> dict:
    from agent_tools.common import read_section_status

    return read_section_status(root)


def build_panel_dispatch_prompt(root) -> str:
    """Host-agent task: spawn one subagent per seat (fresh contexts), wait for
    all reports. Includes the degraded single-context fallback."""
    root = Path(root)
    reported = seats_reported(root)
    missing = [s for s in SEAT_ORDER if s not in reported]

    lines = [
        "Run the BLIND REVIEW PANEL for the paper in this directory.",
        "",
        "Step 1 — dispatch the seats. Spawn one independent subagent per seat "
        "below (your Task/Agent tool; a FRESH context per seat is the whole "
        "point — the author's context is exactly what the panel must not "
        "inherit). Give each subagent its card verbatim as its prompt. "
        "Subagents read the paper themselves and write "
        f"`{REVIEWS_DIR_REL}/<seat>.md`.",
    ]
    if reported:
        lines.append(
            f"(Resume state: {len(reported)}/{len(SEAT_ORDER)} reports already on "
            f"disk: {', '.join(reported)}. Dispatch only the missing seats: "
            f"{', '.join(missing)}.)"
        )
    lines += [
        "",
        "Step 2 — do NOT review the paper yourself and do NOT peek at reports "
        "as they land. When all seats have reported, call "
        "`opendraft workflow next --root .` — the synthesis task will be "
        "issued from disk state.",
        "",
        "Fallback (only if your harness has no subagent capability): run the "
        "four cards yourself as four STRICTLY SEPARATE sequential passes "
        "(finish one report completely before starting the next), and head "
        "each report with `> single-context panel (degraded)` — the "
        "provenance disclosure must survive.",
        "",
        "=" * 70,
        "SEAT CARDS (verbatim, one per subagent)",
        "=" * 70,
    ]
    for seat in missing or SEAT_ORDER:
        lines.append("")
        lines.append(seat_card(root, seat))
        lines.append("")
        lines.append("-" * 70)
    return "\n".join(lines) + "\n"


def build_synthesis_prompt(root) -> str:
    """Host-agent task: merge reviews/*.md into global_issues.md under the
    iron rules (traceability, no fabrication, DA-CRITICAL adjudication)."""
    root = Path(root)
    reported = seats_reported(root)
    digest = _status_digest(_read_status(root))
    digest_lines = [f"- {ln}" for ln in digest] or ["- (ledger empty)"]

    return (
        "\n".join(
            [
                "SYNTHESIZE the blind review panel into the paper's global issue list.",
                "",
                f"Panel reports on disk: {', '.join(reported)} under `{REVIEWS_DIR_REL}/`. "
                "Read every one of them in full.",
                "Current status digest:",
                *digest_lines,
                "",
                "IRON RULES:",
                "1. TRACEABLE: every issue you emit must trace to specific seat "
                "report(s). Cite them inline like `(methodology)` or "
                "`(domain, coherence)`. Corroboration across seats raises priority.",
                "2. NO FABRICATION: never emit an issue no seat reported. Never "
                "silently drop a seat finding: findings you reject go to "
                f"`{ADJUDICATION_REL}` with the seat id, the finding, and why it was "
                "dismissed.",
                "3. DA-CRITICAL: every Devil's-Advocate CRITICAL finding becomes an "
                "issue tagged `[da-critical]`. Each must end the run either FIXED "
                "in the fix phase or explicitly adjudicated (rationale) in "
                f"`{ADJUDICATION_REL}` — silent bypass is forbidden.",
                "4. ROUTABLE: map every issue to a section where possible — the fix "
                "phase routes by section names appearing in `Suggested fix`.",
                "",
                "Output format — strict markdown. Start with the heading "
                f"`{GLOBAL_ISSUES_HEADING}`, then one block per issue, ordered by "
                "severity (high first):",
                "",
                "## GI-1 [high|medium|low] scope: global|<section name> [da-critical]",
                "Issue: <one sentence> (source: methodology)",
                "Suggested fix: <a fix directed at a specific section>",
                "",
                "Number issues GI-1, GI-2, ... If — and only if — the panel found no "
                "cross-section issues, write exactly:",
                "",
                NO_ISSUES_TEXT,
                "",
                "Write the result to `global_issues.md` in this directory (plain file "
                "write), then call `opendraft workflow next --root .`.",
            ]
        )
        + "\n"
    )
