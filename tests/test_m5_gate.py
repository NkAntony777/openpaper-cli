#!/usr/bin/env python3
"""M5 hardening tests (audit remediation): finish-gate completeness (presence, word
floor, quality floor, negation-aware forbidden scan), revise invalidating passed,
fix-session re-score closure, session_end cost telemetry, and threshold keys."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from agent_tools.common import (
    read_section_status,
    update_section_status,
    write_checkpoint,
)
from harness.acceptance import match_forbidden_claims, run_finish_acceptance
from harness.eval_suite import EvalMetrics, check_thresholds, evaluate_root


def _intro(root: Path, text: str) -> None:
    drafts = root / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "01_introduction.md").write_text(text, encoding="utf-8")


def _bib(root: Path) -> None:
    (root / "research").mkdir(parents=True, exist_ok=True)
    (root / "research" / "bibliography.json").write_text(
        json.dumps({"citations": [{"id": "cite_001"}]}), encoding="utf-8"
    )


# ---------------------------------------------------------- finish gate: presence


def test_gate_fails_missing_planned_section(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T", "word_targets": {"introduction": 80}})
    # no drafts at all
    gate = run_finish_acceptance(tmp_path)
    assert gate.passed is False
    assert gate.missing_sections == ["introduction"]
    assert any("missing on disk" in g for g in gate.gaps)


def test_gate_fails_below_floor_section(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T", "word_targets": {"introduction": 80}})
    _intro(tmp_path, "too short draft")
    gate = run_finish_acceptance(tmp_path)
    assert gate.passed is False
    assert gate.thin_sections and gate.thin_sections[0]["section"] == "introduction"
    assert gate.thin_sections[0]["words"] == 3


def test_gate_passes_present_floor_met(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T", "word_targets": {"introduction": 20}})
    _bib(tmp_path)
    _intro(
        tmp_path,
        "Dense passage retrieval encodes queries and documents "
        "independently {cite_001}. " + "It scales. " * 8,
    )
    gate = run_finish_acceptance(tmp_path)
    assert gate.missing_sections == []
    assert gate.thin_sections == []


def test_gate_ignores_non_section_target_keys(tmp_path):
    # 'min_citations' is a target knob, not a section — must not be demanded on disk
    write_checkpoint(
        tmp_path,
        {"topic": "T", "word_targets": {"introduction": 20, "min_citations": 1}},
    )
    _intro(tmp_path, "word " * 30)
    gate = run_finish_acceptance(tmp_path)
    assert gate.missing_sections == []


# ------------------------------------------------------- finish gate: quality floor


def test_gate_enforces_min_full_score(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    gate = run_finish_acceptance(tmp_path, min_full_score=75, full_score=62)
    assert gate.passed is False
    assert gate.quality_gap and "62" in gate.quality_gap


def test_gate_quality_floor_needs_score(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    gate = run_finish_acceptance(tmp_path, min_full_score=75, full_score=None)
    assert gate.passed is False
    assert "unavailable" in (gate.quality_gap or "")


def test_gate_no_floor_by_default(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    gate = run_finish_acceptance(tmp_path)
    assert gate.quality_gap is None


# --------------------------------------------- forbidden scan: negation exemption


def test_forbidden_negated_sentence_exempt(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "T",
            "research_brief": {
                "forbidden_claims": ["causal relationship between proximity and friendship"]
            },
        },
    )
    _intro(
        tmp_path,
        (
            "We do not claim a causal relationship between proximity and friendship.\n"
            "Our design is purely correlational."
        ),
    )
    gate = run_finish_acceptance(tmp_path)
    assert gate.forbidden_hits == []
    assert gate.passed is True


def test_forbidden_positive_sentence_still_fires():
    hits = match_forbidden_claims(
        "This paper asserts a causal relationship between proximity and friendship.",
        ["causal relationship between proximity and friendship"],
    )
    assert len(hits) == 1


# ------------------------------------------------------- revise invalidates passed


def test_revise_invalidates_section_passed(tmp_path, monkeypatch):
    import agent_tools.revise as revise_mod
    from agent_tools import registry

    # hermetic: a unique find_replace must never touch the LLM path
    def _no_llm(*a, **kw):
        raise AssertionError("LLM revise must not be called for a unique find_replace")

    monkeypatch.setattr(revise_mod, "_llm_revise", _no_llm)

    write_checkpoint(tmp_path, {"topic": "T", "word_targets": {"introduction": 20}})
    _intro(
        tmp_path,
        "Original introduction text that is long enough to survive "
        "any floor checks easily, with a different second clause here.",
    )
    update_section_status(
        tmp_path, "introduction", status="written", passed=True, updated_at="2026-01-01"
    )
    spec = registry.get_tool("revise_section")
    r = spec.func(
        {
            "section": "introduction",
            "instructions": "update the opening wording",
            "find_replace": [
                {"find": "Original introduction", "replace": "Revised introduction"},
            ],
        },
        tmp_path,
    )
    assert r.get("ok"), r
    entry = read_section_status(tmp_path)["sections"]["introduction"]
    assert entry["passed"] is False


# --------------------------------------------------- cost telemetry (eval)


def test_eval_reads_real_spent_marker(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    (tmp_path / "run_journal.jsonl").write_text(
        json.dumps(
            {
                "type": "session_end",
                "summary": "session=section-results reason=settled spent=0.42",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    metrics = evaluate_root(tmp_path)
    assert metrics.token_cost == pytest.approx(0.42)


def test_max_token_cost_threshold():
    m = EvalMetrics(
        quality_score=None,
        factcheck_clean=True,
        citation_rate=1.0,
        token_cost=0.9,
        fix_rounds=0,
        forbidden_hits=0,
        cite_missing=0,
        passed=True,
    )
    fails = check_thresholds(m, {"max_token_cost": 0.5})
    assert any("token_cost" in f for f in fails)
    assert check_thresholds(m, {"max_token_cost": 1.0}) == []


# -------------------------------------------------- manage_claims resolve evidence


def test_manage_claims_resolve_requires_section_file(tmp_path):
    from agent_tools import registry

    spec = registry.get_tool("manage_claims")
    spec.func(
        {
            "action": "record",
            "section": "introduction",
            "claims": [{"claim": "P equals NP"}],
        },
        tmp_path,
    )

    r = spec.func(
        {
            "action": "resolve",
            "section": "introduction",
            "claims": [{"claim": "P equals NP", "status": "deleted"}],
        },
        tmp_path,
    )

    assert r["ok"] is False
    assert r["is_retryable"] is True
    assert "not found" in r["error"]
