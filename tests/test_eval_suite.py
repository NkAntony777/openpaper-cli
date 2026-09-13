#!/usr/bin/env python3
"""M3 finish-gate + M4 eval suite: forbidden_claims matcher, CONTRADICTED handling,
gold-fixture CI gates, and two-run lessons injection."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from agent_tools.common import write_checkpoint
from harness.acceptance import (
    match_forbidden_claims,
    run_finish_acceptance,
)
from harness.eval_suite import (
    check_thresholds,
    evaluate_gold_set,
    evaluate_root,
)
from harness.paper_map import seed_approved_lessons, write_paper_map
from harness.section_task import build_section_prompt

REPO = Path(__file__).parent.parent
GOLD_DIR = REPO / "tests" / "eval_gold"


def _intro(root: Path, text: str) -> None:
    drafts = root / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "01_introduction.md").write_text(text, encoding="utf-8")


def _ledger(root: Path, section: str, entries) -> None:
    d = root / "drafts" / ".ledger"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{section}.claims.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8"
    )


# -------------------------------------------------------- forbidden matcher


def test_match_forbidden_keyword_overlap():
    text = "There is a causal relationship between proximity and friendship in the wild."
    hits = match_forbidden_claims(text, ["causal relationship between proximity and friendship"])
    assert len(hits) == 1
    assert hits[0]["overlap"] >= 0.6


def test_match_forbidden_does_not_fire_on_stopwords_alone():
    text = "We show that this is the case in the data."
    hits = match_forbidden_claims(text, ["we show that proximity causes friendship"])
    assert hits == []


def test_match_forbidden_single_keyword_substring():
    assert match_forbidden_claims("pre-trained BERT encoder", ["BERT"])
    assert not match_forbidden_claims("pre-trained encoder", ["BERT"])


# -------------------------------------------------------- finish acceptance


def test_finish_acceptance_clean(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "T",
            "research_brief": {
                "forbidden_claims": ["causal relationship between proximity and friendship"]
            },
        },
    )
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "bibliography.json").write_text(
        json.dumps({"citations": [{"id": "cite_001"}]}), encoding="utf-8"
    )
    _intro(tmp_path, "DPR encodes queries independently {cite_001}.")
    _ledger(
        tmp_path,
        "introduction",
        [
            {
                "id": "CL-INTRODUCTION-1",
                "claim": "DPR encodes queries independently",
                "verdict": {"verdict": "SUPPORTED"},
            }
        ],
    )

    gate = run_finish_acceptance(tmp_path)
    assert gate.passed is True
    assert gate.claims_clean is True
    assert gate.forbidden_hits == []
    assert gate.citation_rate == 1.0


def test_finish_acceptance_rejects_unresolved_contradicted(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    _intro(tmp_path, "The model reaches 99% accuracy.")
    _ledger(
        tmp_path,
        "introduction",
        [
            {
                "id": "CL-INTRODUCTION-1",
                "claim": "The model reaches 99% accuracy",
                "verdict": {
                    "verdict": "CONTRADICTED",
                    "wrong_part": "99%",
                    "correct_value": "72%",
                },
            }
        ],
    )

    gate = run_finish_acceptance(tmp_path)
    assert gate.passed is False
    assert gate.claims_clean is False
    assert gate.gaps and "CONTRADICTED" in gate.gaps[0]


def test_finish_acceptance_accepts_resolved_contradicted(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    _intro(tmp_path, "The model reaches 72% accuracy.")
    _ledger(
        tmp_path,
        "introduction",
        [
            {
                "id": "CL-INTRODUCTION-1",
                "claim": "The model reaches 99% accuracy",
                "verdict": {
                    "verdict": "CONTRADICTED",
                    "wrong_part": "99%",
                    "correct_value": "72%",
                },
                "resolution": {
                    "status": "revised",
                    "note": "find_replace",
                    "resolved_at": "t",
                },
            }
        ],
    )

    gate = run_finish_acceptance(tmp_path)
    assert gate.claims_clean is True
    assert gate.passed is True


def test_finish_acceptance_rejects_forbidden_and_unknown_cite(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "T",
            "research_brief": {
                "forbidden_claims": ["causal relationship between proximity and friendship"]
            },
        },
    )
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "bibliography.json").write_text(
        json.dumps({"citations": [{"id": "cite_001"}]}), encoding="utf-8"
    )
    _intro(
        tmp_path,
        ("There is a causal relationship between proximity and friendship {cite_999}."),
    )

    gate = run_finish_acceptance(tmp_path)
    assert gate.passed is False
    assert len(gate.forbidden_hits) == 1
    assert "cite_999" in gate.unknown_citations
    assert (tmp_path / "qa_forbidden_claims.md").exists()


# -------------------------------------------------------- eval suite (CI gold)


def test_eval_gold_set_gates():
    summary = evaluate_gold_set(GOLD_DIR)
    assert summary["n"] == 2, summary
    by_id = {r["id"]: r for r in summary["results"]}
    assert by_id["clean_mini"]["ok"] is True, by_id["clean_mini"]
    assert by_id["dirty_mini"]["ok"] is True, by_id["dirty_mini"]
    assert summary["ok"] is True

    clean = by_id["clean_mini"]["metrics"]
    assert clean["factcheck_clean"] is True
    assert clean["citation_rate"] == 1.0
    assert clean["passed"] is True

    dirty = by_id["dirty_mini"]["metrics"]
    assert dirty["factcheck_clean"] is False
    assert dirty["forbidden_hits"] >= 1
    assert dirty["citation_rate"] < 1.0
    assert dirty["passed"] is False
    assert dirty["fix_rounds"] == 3
    assert dirty["cite_missing"] >= 1


def test_evaluate_root_token_cost_from_spent_marker(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T"})
    (tmp_path / "run_journal.jsonl").write_text(
        json.dumps({"type": "prompt", "summary": "session=section-results spent=0.42"}) + "\n",
        encoding="utf-8",
    )
    metrics = evaluate_root(tmp_path)
    assert metrics.token_cost == pytest.approx(0.42)


def test_check_thresholds_reports_each_miss():
    from harness.eval_suite import EvalMetrics

    m = EvalMetrics(
        quality_score=10,
        factcheck_clean=False,
        citation_rate=0.5,
        token_cost=0,
        fix_rounds=4,
        forbidden_hits=2,
        cite_missing=1,
        passed=False,
    )
    fails = check_thresholds(
        m,
        {
            "min_quality": 50,
            "require_factcheck_clean": True,
            "min_citation_rate": 1.0,
            "max_forbidden_hits": 0,
            "expect_passed": True,
        },
    )
    assert len(fails) >= 4


# -------------------------------------------------------- two-run lessons


def test_approved_lessons_inject_into_paper_map(tmp_path):
    templates = tmp_path / "templates" / "lessons"
    templates.mkdir(parents=True)
    (templates / "short_methodology.md").write_text(
        "section methodology: aim for >=90% of the word target in the first write",
        encoding="utf-8",
    )

    root = tmp_path / "paper"
    root.mkdir()
    write_checkpoint(root, {"topic": "Second paper", "word_targets": {}})
    copied = seed_approved_lessons(root, templates_dir=templates)
    assert copied == 1
    # existing approved files are not overwritten on a second seed
    assert seed_approved_lessons(root, templates_dir=templates) == 0

    write_paper_map(root)
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Lessons learned" in text
    assert "short_methodology" in text
    assert "90%" in text


def test_section_prompt_lists_forbidden_claims(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "T",
            "academic_level": "master",
            "citation_style": "apa",
            "language": "en",
            "word_targets": {"introduction": 100},
            "research_brief": {"forbidden_claims": ["no causal claims about proximity"]},
        },
    )
    prompt = build_section_prompt(tmp_path, "introduction")
    assert "FORBIDDEN claims" in prompt
    assert "no causal claims about proximity" in prompt
    assert "manage_claims" in prompt


def test_paper_map_forbidden_and_open_claims(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "T",
            "word_targets": {},
            "research_brief": {"forbidden_claims": ["do not claim causality"]},
        },
    )
    _ledger(
        tmp_path,
        "results",
        [
            {
                "id": "CL-RESULTS-1",
                "claim": "Accuracy is 99%",
                "verdict": {"verdict": "CONTRADICTED", "wrong_part": "99%"},
            }
        ],
    )
    write_paper_map(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "FORBIDDEN claims" in text
    assert "do not claim causality" in text
    assert "## Claims ledger" in text
    assert "OPEN CL-RESULTS-1" in text


def test_cli_harness_eval_envelope(tmp_path, capsys):
    import shutil

    from opendraft.cli import run_eval_command

    root = tmp_path / "clean"
    shutil.copytree(GOLD_DIR / "clean_mini", root)
    rc = run_eval_command(["--root", str(root)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["data"]["factcheck_clean"] is True
    assert payload["data"]["passed"] is True


def test_cli_harness_eval_dirty_exits_one(tmp_path, capsys):
    import shutil

    from opendraft.cli import run_eval_command

    root = tmp_path / "dirty"
    shutil.copytree(GOLD_DIR / "dirty_mini", root)
    rc = run_eval_command(["--root", str(root)])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["data"]["passed"] is False
