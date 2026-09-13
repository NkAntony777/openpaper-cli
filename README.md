# OpenPaper CLI

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Quality Gates](https://github.com/NkAntony777/openpaper-cli/actions/workflows/quality.yml/badge.svg)](https://github.com/NkAntony777/openpaper-cli/actions/workflows/quality.yml)

> **Paper writing workflows for any harness.** Keep your coding agent and your
> subscription — Claude Code, ZCode, Cursor, Codex, anything with a shell.
> OpenPaper brings the discipline: guardrails that make lazy writing and
> hallucinated citations structurally impossible, a blind review panel, a claims
> audit, and a finish gate that reads disk truth. The model is your model.

Unattended runs with the built-in pi driver live in the sibling repo
[OpenPaper](https://github.com/NkAntony777/openpaper) — same engine, different
deployment model. This repo: **your harness drives, OpenPaper answers.**

---

## The workflow: six guarded stages

Tell your agent *"write a paper about X"* and it runs this loop. Each stage is
enforced by code and disk state — not by hoping the model behaves.

**1 · Setup** — `opendraft workflow init --root . --topic "Your topic"` prepares
the paper directory: a starter checkpoint with your topic, language, and
per-section word targets (tune them in `checkpoint.json`), plus an `AGENTS.md`
paper map the agent re-reads at every step. Already have research material?
Drop it in `research/` and the workflow builds on it.

**2 · Guarded section writing** — the agent writes each section through a CLI
that **rejects bad output at write time**: citations not in
`research/bibliography.json` are refused (hallucinated references never reach
disk), TODO/[INSERT]-style placeholders are refused, sections below the word
floor are refused. Every section is immediately scored against a 100-point
quality gate and must pass before the workflow moves on.

**3 · Claims audit** — the agent records hard factual claims (numbers, dates,
causal statements) into a persistent ledger as it writes. Claims get verified
against live web evidence; a CONTRADICTED claim comes back with the exact wrong
text and the correct value, and **must be fixed and resolved on disk** —
unresolved ones fail the paper outright.

**4 · Blind review panel** — the review is not self-review. Your harness spawns
**four independent subagents with fresh contexts** — methodology, domain
coverage, cross-section coherence, and a devil's advocate — each committing
findings without seeing the others (the author's context is exactly the bias a
panel must not inherit). Findings are merged under strict rules: every issue
traces to a reviewer, the synthesizer invents nothing, and devil's-advocate
CRITICALs must be either fixed or explicitly adjudicated — never silently
dropped.

**5 · Targeted fixes, traceable** — every review finding becomes a fix task
against a specific section. Each fix lands as a row in a traceability matrix
(`fix_report.md`: FIXED / NOT FIXED / ADJUDICATED + evidence), and a section
only counts as fixed when its **on-disk re-score passes** — no rubber-stamping,
no trusting the agent's self-report.

**6 · Finish gate & export** — an offline gate checks the final state: every
planned section present and above its word floor, zero hallucinated citations,
zero unresolved contradicted claims, zero forbidden-claim hits, quality score
≥ 75. Only then does the deterministic compile produce your PDF/DOCX with a
complete reference list.

## How it talks to your harness

```
┌ Your harness (Claude Code / ZCode / Cursor / … + YOUR subscription) ┐
│ the agent loop, the context, the budget — all yours                  │
└──────────────┬────────────────────────────────────────────────────────┘
               │ shell
               ▼
  opendraft workflow next --root .      ← the state machine: one JSON task at a time
  opendraft tool <name> --root . …      ← 9 guardrailed tools, one JSON envelope line
               │
               ▼
  <paper dir>/ ← the single source of truth: drafts/ · research/bibliography.json ·
                 section_status.json · AGENTS.md · reviews/ · fix_report.md
```

- **The workflow is code + disk, not prompts.** `workflow next` decides the next
  stage from disk state; task prompts arrive as data your agent executes. If a
  subagent crashes mid-run, the next `workflow next` resumes from what's on disk.
- **The budget is yours.** No cost breaker exists here by design — your harness's
  limits (or you) decide when to stop. The one tunable, `--max-fix-rounds`, is an
  escalation policy: after N failed fix rounds a section is escalated to a full
  rewrite, not silently abandoned.
- **Zero standing context cost.** Your harness's shell is the protocol — no MCP
  server to keep connected. The bundled skill's ~100-token trigger is the only
  thing resident.

## Quickstart

```bash
# 1. Install the CLI (from this repo)
pip install -e ./engine
opendraft tool list                       # sanity check: no keys needed

# 2. (Recommended) install the skill into your harness
#    Claude Code / ZCode / anything speaking the SKILL.md convention:
mkdir -p ~/.claude/skills && cp -r skill/openpaper-cli ~/.claude/skills/

# 3. In your harness, from a paper directory:
opendraft workflow init --root . --topic "Your topic here"   # + --lang, word targets
opendraft workflow next --root .          # execute the returned task, repeat
opendraft workflow finish --root .        # explicit finish-gate run (optional)
```

With the skill installed, just tell your agent *"write a paper about X"* — it
picks up the workflow from there. Want to try it without writing research
material first? `python scripts/make_poc_fixture.py` builds a ready-made
research directory.

## API keys: what actually needs them

**The core loop needs no LLM keys at all** — your harness's model does the
thinking; the guardrails, scoring, and citation search (Crossref / OpenAlex /
Semantic Scholar — free public APIs) are pure code. Optional enhancements:
`SERPER_API_KEY` (web-search fallback), `GOOGLE_API_KEY` (grounded
fact-check), `OPENAI_API_KEY` (the LLM pass inside `revise_section` — in CLI
mode your agent usually rewrites via `write_section` instead).

## Current scope, honestly

Research material is a prepared directory (bring your own, or use the fixture
generator); the workflow owns writing, review, claims audit, and the finish
gate. Design background: [docs/AGENT_HARNESS_DESIGN.md](docs/AGENT_HARNESS_DESIGN.md).

## Testing

```bash
pytest tests/ -q        # 590+ offline tests; no network, no LLM calls
```

CI runs the same suite plus `ruff` lint/format gates on every push.

## Credits & license

Continues the work of [OpenDraft](https://github.com/federicodeponte/opendraft)
(Federico De Ponte, MIT) and [OpenPaper](https://github.com/NkAntony777/openpaper).
MIT License.
