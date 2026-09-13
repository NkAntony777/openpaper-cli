# OpenPaper CLI — Engine

The Python engine behind the `opendraft` CLI: the guardrailed agent-tool layer, the
host-harness workflow state machine, quality gates, and the citation/export chain
inherited from OpenDraft.

## Structure

```
engine/
├── agent_tools/            # The 9 guardrailed tools (registry, envelope contract)
├── harness/
│   ├── workflow.py         # Host-harness state machine (init/next/finish)
│   ├── section_task.py     # Section-writing + fix task prompt builders
│   ├── review_task.py      # Global review prompt builder
│   ├── paper_map.py        # AGENTS.md paper-map generator
│   ├── acceptance.py       # Offline finish gate (word floors, citations, claims)
│   └── eval_suite.py       # Offline eval metrics + gold-fixture gates
├── opendraft/              # CLI entry points
│   ├── cli.py              # Dispatcher (setup/tool/workflow/eval/tldr/…)
│   ├── tool_cli.py         # `opendraft tool` — machine JSON-envelope contract
│   ├── workflow_cli.py     # `opendraft workflow init|next|finish`
│   ├── eval_cli.py         # `opendraft eval`
│   └── commands.py / ui.py # Human-facing content commands + console chrome
├── utils/
│   ├── llm_runtime.py      # Model setup + retrying agent LLM-call loop
│   ├── citation_research.py  # Scout: citation research orchestration
│   ├── api_citations/      # Citation APIs (Crossref, OpenAlex, Semantic Scholar, …)
│   ├── citation_*.py       # Citation management, database & compiler
│   ├── factcheck_verifier.py  # Web-grounded claim verification
│   ├── export_professional.py # PDF/DOCX export
│   ├── pdf_engines/        # Pandoc, WeasyPrint engines
│   └── quality_gate.py     # The 100-point scoring core (pure functions)
├── phases/                 # Compile phase + DraftContext (checkpoint schema)
├── prompts/                # Legacy pipeline prompts (used by revise/abstract)
└── config.py               # Model settings, API keys, rate limits
```

## Usage

See the repo-root README — everything goes through the `opendraft` CLI. The engine
has no standalone entry point by design: the workflow is driven from your harness.

## Environment Variables

Optional (see repo README "API keys" — the core writing loop needs none):

```bash
SERPER_API_KEY=...          # Web-search fallback in citation research
GOOGLE_API_KEY=...          # Gemini-grounded search (verify_claims, backfill)
OPENAI_API_KEY=...          # The LLM pass inside revise_section
PROXY_LIST=...              # Optional: research rate-limit bypass
```

## Dependencies

```bash
pip install -r requirements.txt
```
