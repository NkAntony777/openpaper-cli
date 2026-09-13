# Changelog

All notable changes are documented in this file.

## 2026-09-13 — OpenPaper CLI 2.1.0 (repo fork)

Forked from [OpenPaper](https://github.com/NkAntony777/openpaper) as the CLI-native
deployment model: **your harness drives, OpenPaper answers.** Everything below is
on top of the 2026-09-13 OpenPaper refactor (see the prior entry).

### Added
- `opendraft workflow init|next|finish` — the host-harness state machine
  (`engine/harness/workflow.py`). `next` decides the next task purely from disk
  truth (section_status.json, claims ledger, global_issues.md): pending sections →
  global review → round-limited targeted fixes → full-section rework escalation →
  offline finish gate. Task prompts are returned as JSON data with a CLI adapter
  header (shell syntax, `--args-file` guidance, envelope semantics).
- `opendraft eval` — the offline eval suite promoted to a top-level command.
- `skill/openpaper-cli/SKILL.md` — a thin bootstrap skill (trigger + loop rules,
  ~100-token resident cost). The workflow lives in code + disk, never in the skill.

### Removed (the pi driver mode)
- `harness/driver.py` (PiDriver RPC loop + budget breaker), `harness/paper_task.py`
  (session orchestration), `harness/journal_distill.py`, the pi TS extension and its
  smoke/parity tests, `opendraft harness` CLI group, and the pi demo scripts. This
  repo has exactly one deployment model; the driver mode lives on in OpenPaper.
- Budget control is delegated to the user BY DESIGN: no cost/turn/wall-clock
  breaker exists in CLI mode. `--max-fix-rounds` is an escalation policy (fix N
  rounds, then full-section rework), not a budget.

### Changed
- Package identity: `openpaper-cli` 2.1.0, URLs to NkAntony777/openpaper-cli.
- README rewritten CLI-first (bring-your-own-harness, subscription-friendly, honest
  API-key matrix); engine/README structure section now matches the actual tree.

### Verification
- `pytest tests -q` → 582 passed, 11 skipped, 15 deselected (fully offline).
- `ruff check` / `ruff format --check` clean.

## 2026-09-13

### Refactored (legacy layer)
- Split the 1340-line `utils/agent_runner.py` god object into `utils/llm_runtime.py`
  (model setup, prompt loading, the retrying `run_agent` loop) and
  `utils/citation_research.py` (the Scout: deep-research planning, parallel query
  execution, relevance filter, tiered quality gate). All importers updated;
  `agent_runner.py` deleted.
- Split the 1083-line `opendraft/cli.py` into `opendraft/ui.py` (TUI chrome,
  setup wizard, config), `opendraft/commands.py` (tldr/digest/revise/data),
  `opendraft/tool_cli.py` (machine JSON-envelope CLI), and
  `opendraft/harness_cli.py`; `cli.py` is now a thin dispatcher that re-exports
  the `run_*` handlers, so `from opendraft.cli import X` keeps working.
- Removed all vestigial `#region agent log` debug blocks (hardcoded
  `/tmp/opendraft_debug.log`, fake session ids) from `agent_runner` and
  `deep_research`.

### Fixed
- `research_citations_via_api(output_path=None)` no longer crashes at the
  markdown-write step (latent AttributeError).
- Smart double quotes (U+201C/U+201D) were never normalized in
  `pandoc_engine` — both dict keys had been typed as the ASCII quote.
- `deep_research` closure captured a loop-rebound variable (B023); now bound
  at definition.
- Missing `subprocess` import in `test_harness` (a NameError was being
  swallowed by the driver's `except`, so the test passed for the wrong reason).
- Windows-only path assertion in `test_checkpoint` (POSIX string compare →
  Path roundtrip compare).
- `openpaper[all]` extra self-referenced the old package name `opendraft[...]`.

### Changed
- No machine-specific defaults in code: `PI_BIN` falls back to `which pi`
  instead of `E:\npm-global\pi.cmd`; the TS smoke honors `PI_NODE_MODULES` /
  `OD_PY` env overrides (Linux-CI compatible).
- Project metadata unified as OpenPaper (authors/URLs/keywords point at
  `NkAntony777/openpaper`; console scripts stay `opendraft*` for the
  OPENDRAFT_BIN contract). Upstream credit unchanged in README.
- Removed the dead `[tool.pytest.ini_options]` from `engine/pyproject.toml`
  (repo-root `pytest.ini` is the single source of truth — the engine copy
  required pytest-cov and broke `pytest` run from `engine/`).
- Replaced never-enforced black/flake8/isort/mypy configs with `ruff`
  (lint + format, line length 100). One-time `ruff format` over the repo;
  715 lint violations fixed to zero (including 9 undefined names, bare
  excepts, ambiguous loop-variable captures).
- `engine/tests/` (never collected by CI) folded into root `tests/`: the
  revise/data CLI tests were previously untracked by CI entirely. Live-API
  tests are marked `network` and deselected like `integration`.
- egg-info build artifacts untracked and gitignored.

### Added
- TS↔Python **tool-schema parity test**: the smoke test dumps each tool's
  TypeBox schema (`OD_TS_SCHEMA_DUMP`) and pytest compares property sets,
  required lists, and enums against the Python `INPUT_SCHEMA` — drift now
  fails CI.
- CI installs `@earendil-works/pi-coding-agent` on Linux and runs the TS
  extension smoke + parity test (previously Windows-dev-box-only), plus
  `ruff check` / `ruff format --check` gates.

### Verification
- `python -m pytest tests -q` → 626 passed, 11 skipped, 15 deselected (fully
  offline; was 586+1 failing on Windows before).
- TS smoke: 24 assertions pass against both the author's global pi install
  and a fresh `npm install` (hoisted layout) of `pi-coding-agent@0.85.1`.
- `ruff check` and `ruff format --check` clean over `engine tests scripts`.

## 2026-02-16

### Added
- CI quality gate workflow: `.github/workflows/quality.yml`
- Maintainer push/auth runbook: `docs/MAINTAINER_PUSH_RUNBOOK.md`
- Automated push preflight checker: `scripts/push-preflight.sh`

### Changed
- Migrated Gemini runtime usage from legacy SDK to `google-genai` wrappers across engine modules.
- Replaced deprecated `google-generativeai` dependency pins with `google-genai>=1.0.0`.
- Stabilized pytest harness with strict markers and integration test separation.

### Fixed
- Output cleaning regression that could strip real references sections.
- Live factcheck integration tests now skip safely in offline/restricted environments.

### Verification
- `python3 -W error::SyntaxWarning -m compileall -q engine tests` passed.
- `python3 -m pytest tests -q` passed (`286 passed, 4 deselected`).
- Push preflight passed with clean sync and correct maintainer account.

### Follow-up
- Aligned CLI/npm requirement consistency (`6e74e75`).
- Hardened live script execution paths (`python tests/test_live_crafter.py`, `python tests/audit_output.py`) with prerequisite-aware skip behavior.
- Expanded CI quality workflow to execute `python -m pytest tests -q`.
- Added secret-gated live-validation workflow (`.github/workflows/live-validation.yml`) for weekly/manual execution of API-backed checks.
- Fixed live audit model selection to use `GEMINI_MODEL` override with `gemini-2.0-flash` fallback (`f8b8a6c`).
- Verified live-validation workflow success on GitHub Actions (`run 22061717973`).
- Fixed quality CI pytest collection error by removing stale `genai.GenerativeModel` annotation from `engine/utils/citation_compiler.py`.
