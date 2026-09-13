---
name: openpaper-cli
description: >-
  Academic paper writing workflow with structural guardrails (citation whitelist,
  quality gates, claims ledger, finish gate), driven through the opendraft CLI.
  Use when the user asks to write, draft, or substantially revise an academic
  paper, thesis, or long-form research manuscript. Not for general writing tasks.
---

# OpenPaper CLI workflow

The workflow, quality gates and guardrails live in the `opendraft` CLI — not in
this skill. Your job is only to run the loop and execute each task it returns.

## Prerequisites

`opendraft` must be runnable from the shell (`pip install -e <path-to-openpaper-cli>/engine`,
or set OPENDRAFT_BIN). Verify once with `opendraft tool list`.

## The loop

1. `cd <paper-directory>` (create it if this is a fresh start).
2. Fresh start only: `opendraft workflow init --root . --topic "<topic>"`.
3. `opendraft workflow next --root .` — it returns ONE task prompt plus phase info.
4. Execute that task exactly as prompted (it tells you which `opendraft tool ...`
   shell commands to use), then call `next` again.
5. Repeat until `next` reports `"phase": "done"` (finish gate passed). Exit code 1
   from `next` means the gate is failing — read the `gaps` it returns and remediate.

## Hard rules

- Section content goes through `opendraft tool write_section` ONLY — never your own
  file-write tools. The citation whitelist, word floor and placeholder checks only
  run there; bypassing them breaks the finish gate.
- Cite only `cite_XXX` ids that exist in `research/bibliography.json`. Need a new
  source? `opendraft tool search_literature` first, then cite the ids it returns.
- Tool errors come back as one-line JSON envelopes (`{"ok": false, ...}`). They are
  feedback, not crashes: read `error`, fix the arguments, retry.
- There is no cost breaker in this mode: you are the budget. If a task loops twice
  without progress, stop and report the blocker to the user.
