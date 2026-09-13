# OpenPaper CLI

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Quality Gates](https://github.com/NkAntony777/openpaper-cli/actions/workflows/quality.yml/badge.svg)](https://github.com/NkAntony777/openpaper-cli/actions/workflows/quality.yml)
[![Built on OpenDraft](https://img.shields.io/badge/Built%20on-OpenDraft-orange)](https://github.com/federicodeponte/opendraft)

> **Paper writing workflows for any harness.** Keep your coding agent and your
> subscription — Claude Code, ZCode, Cursor, Codex, anything with a shell. OpenPaper
> contributes the workflow: guardrailed writing tools, quality gates, a claims
> ledger, and a finish gate that reads disk truth. The model is your model.

This is the CLI-native sibling of [OpenPaper](https://github.com/NkAntony777/openpaper)
(which ships its own pi-based driver for unattended runs). Same tool layer, same
guardrails — different deployment model: **your harness drives, OpenPaper answers.**

---

## How it works

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
                 section_status.json · AGENTS.md · drafts/.ledger/
```

- **The workflow is code + disk, not prompts.** `workflow next` reads
  `section_status.json`, the claims ledger, and `global_issues.md` to decide the
  next task (write a section → global review → targeted fixes → finish gate).
  Task prompts are returned as data; your agent just executes them.
- **The budget is yours.** There is no cost breaker here by design. Your harness's
  limits — or you — decide when to stop. (`--max-fix-rounds` is not a budget: it is
  an escalation policy — after N fix rounds a still-failing section is escalated to
  a full rewrite.)
- **Zero standing context cost.** No MCP server to keep connected: your harness's
  own shell tool is the protocol. Install the bundled skill (below) and its
  ~100-token trigger description is the only thing resident.

## Quickstart

```bash
# 1. Install the CLI (from this repo)
pip install -e ./engine
opendraft tool list                       # sanity: 9 tools, no keys needed

# 2. (Optional, recommended) install the skill into your harness
#    Claude Code / ZCode / anything speaking the SKILL.md convention:
mkdir -p ~/.claude/skills && cp -r skill/openpaper-cli ~/.claude/skills/

# 3. In your harness, from a paper directory:
opendraft workflow init --root . --topic "Your topic here"
opendraft workflow next --root .          # execute the returned task, repeat
opendraft workflow finish --root .        # explicit finish-gate run (optional)
```

With the skill installed, just tell your agent *"write a paper about X"* — it picks
up the workflow from there. A ready-made research fixture for trying things out:
`python scripts/make_poc_fixture.py` builds one under `tests/fixtures/poc_output/`.

## The tools

| Tool | What it does | Guardrails |
|---|---|---|
| `read_artifact` | Read research notes, outline, bibliography, drafts | path-confined to the paper root, paged reads |
| `write_section` | Idempotent full-section write + checkpoint sync | citation whitelist, word floor, placeholder rejection, snapshots |
| `score_draft` | 100-point gate, structured issues as the fix backlog | read-only, idempotent |
| `search_literature` | Search Crossref / OpenAlex / Semantic Scholar; results become citable immediately | LLM-fabricated citations stay disabled |
| `verify_claims` | Web-grounded fact-check → `wrong_part`/`correct_value` pairs | — |
| `manage_claims` | Persistent claims ledger: record / list / verify / resolve | resolve is evidence-checked against the draft on disk |
| `revise_section` | Targeted revision (exact `find_replace` or LLM pass) | same guardrails as `write_section`; invalidates the section's passed bit |
| `write_outline` | Non-linear structure control mid-writing | merge=true does heading-keyed replacement |
| `compile_draft` | Deterministic compile + PDF/DOCX export | auto-backfills `{cite_MISSING}` into the reference list |

Every tool prints exactly one JSON envelope line: `{"ok": true, "data": ...}` or
`{"ok": false, "error": "...", "is_retryable": bool}`. Errors are feedback, not
crashes — your agent reads them and retries.

## API keys: what actually needs them

**The core writing loop needs no LLM keys at all** — your harness's model does the
thinking; `write_section` / `score_draft` / `read_artifact` / `write_outline` /
`manage_claims` (record/list/resolve) are pure code, and `search_literature`'s main
cascade (Crossref / OpenAlex / Semantic Scholar) is free public HTTP APIs.

Optional enhancements use keys, and the workflow degrades gracefully without them:
`SERPER_API_KEY` (web-search fallback in citation research), `GOOGLE_API_KEY`
(Gemini-grounded search for `verify_claims` and citation backfill),
`OPENAI_API_KEY`/`OPENAI_BASE_URL` (the LLM pass inside `revise_section` — in CLI
mode you usually don't need it: your agent rewrites via `write_section` instead).

## Current scope, honestly

Research material is a prepared directory (bring your own, or
`scripts/make_poc_fixture.py`); the workflow covers writing, review, claim audits,
and the finish gate. A finish gate that passes means: every planned section present
and above its word floor, zero hallucinated citations, zero unresolved
CONTRADICTED claims, zero forbidden-claim hits, and a full-draft score ≥ 75.

## Testing

```bash
pytest tests/ -q        # 580+ offline tests; no network, no LLM calls
```

CI runs the same suite plus `ruff` lint/format gates on every push.

## Relationship map

| | OpenPaper (sibling repo) | **OpenPaper CLI** (this repo) |
|---|---|---|
| Who runs the agent | its own pi driver (RPC mode) | **your harness** |
| Model access | API keys (MiniMax/…) | your subscription |
| Budget control | built-in cost/turns/wall-clock breaker | you / your harness |
| TS extension, run journal, distill | ✔ | ✘ (not applicable) |
| Tool layer, gates, claims ledger, finish gate | ✔ | ✔ (same code) |

Design background (the audit that motivated all of this):
[docs/AGENT_HARNESS_DESIGN.md](docs/AGENT_HARNESS_DESIGN.md).

## Credits & license

Built on [OpenDraft](https://github.com/federicodeponte/opendraft) by Federico De
Ponte (MIT), continuing the work in
[OpenPaper](https://github.com/NkAntony777/openpaper). MIT License.
