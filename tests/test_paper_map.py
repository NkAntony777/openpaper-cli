#!/usr/bin/env python3
"""Offline tests for the surviving harness-layer pieces: the AGENTS.md paper map
(harness/paper_map.py) and the task prompt builders (section_task / review_task).
The pi driver and its tests live in the openpaper repo (driver mode); this repo is
CLI mode."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from agent_tools.common import (
    FULL_LEDGER_KEY,
    SECTION_FILES,
    update_section_status,
    write_checkpoint,
)
from harness.paper_map import write_paper_map
from harness.review_task import build_review_prompt
from harness.section_task import build_section_prompt

# ---------------------------------------------------------------------- paper map


def test_paper_map_empty_dir(tmp_path):
    out = write_paper_map(tmp_path)
    assert out == tmp_path / "AGENTS.md"
    text = out.read_text(encoding="utf-8")
    assert "(topic unknown" in text
    assert "(no outline yet)" in text
    assert "Citations in database: 0" in text
    for section in SECTION_FILES:
        assert section in text
    assert "pending" in text


def test_paper_map_full_fixture(tmp_path):
    write_checkpoint(
        tmp_path,
        {
            "topic": "AI in education",
            "academic_level": "master",
            "citation_style": "apa",
            "language": "en",
            "completed_phase": "structure",
            "word_targets": {"literature_review": "2000-2500", "methodology": 1500},
        },
    )
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "00_formatted_outline.md").write_text(
        "# Outline\n1. Intro\n2. Lit", "utf-8"
    )
    (tmp_path / "drafts" / "02_1_literature_review.md").write_text("some words here", "utf-8")
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "bibliography.json").write_text(
        json.dumps(
            {
                "citations": [
                    {"id": "cite_001", "year": 2019},
                    {"id": "cite_002", "year": 2021},
                ],
            }
        ),
        "utf-8",
    )

    write_paper_map(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "AI in education" in text
    assert "2000-2500" in text  # raw word-target spec shown
    assert "| 1500 |" in text
    assert "Citations in database: 2" in text
    assert "2019-2021" in text
    assert "| literature_review |" in text and "written" in text
    assert "| methodology |" in text and "pending" in text
    assert "# Outline" in text  # outline content embedded


# --------------------------------------------------------------- section prompt


def _fixture_root(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    write_checkpoint(
        root,
        {
            "topic": "AI in education",
            "academic_level": "master",
            "citation_style": "apa",
            "language": "en",
            "word_targets": {"literature_review": "2000-2500"},
        },
    )
    (root / "drafts").mkdir()
    (root / "drafts" / "00_formatted_outline.md").write_text("# Outline", "utf-8")
    (root / "research").mkdir()
    (root / "research" / "papers").mkdir()
    (root / "research" / "combined_research.md").write_text("notes", "utf-8")
    (root / "research" / "bibliography.json").write_text('{"citations": []}', "utf-8")
    return root


def test_build_section_prompt(tmp_path):
    root = _fixture_root(tmp_path)
    prompt = build_section_prompt(root, "literature_review")

    assert "literature_review" in prompt
    assert "AI in education" in prompt
    assert "2500" in prompt  # parsed max of the "2000-2500" target
    assert "drafts/02_1_literature_review.md" in prompt
    for tool in (
        "read_artifact",
        "write_section",
        "score_draft",
        "search_literature",
        "verify_claims",
        "revise_section",
        "manage_claims",
        "write_outline",
    ):
        assert tool in prompt
    assert "AGENTS.md" in prompt
    assert "cite_XXX" in prompt


def test_build_section_prompt_unknown_section(tmp_path):
    root = _fixture_root(tmp_path)
    with pytest.raises(ValueError):
        build_section_prompt(root, "not_a_section")


# --------------------------------------------------------------- review task (M2)


def _ledger_root(tmp_path):
    """Fixture root with a checkpoint, two summary-ledger files and a status ledger."""
    root = tmp_path / "out"
    root.mkdir()
    write_checkpoint(
        root,
        {
            "topic": "AI in education",
            "academic_level": "master",
            "citation_style": "apa",
            "language": "en",
            "word_targets": {},
        },
    )
    (root / "drafts" / ".ledger").mkdir(parents=True)
    (root / "drafts" / ".ledger" / "introduction.summary.md").write_text(
        "Intro promises a comparative study.", "utf-8"
    )
    (root / "drafts" / ".ledger" / "literature_review.summary.md").write_text(
        "Lit review covers A and B.", "utf-8"
    )
    update_section_status(
        root,
        "introduction",
        status="written",
        passed=True,
        open_issues=[],
        updated_at="2026-01-01T00:00:00",
    )
    update_section_status(
        root,
        FULL_LEDGER_KEY,
        last_total=62,
        last_passed=False,
        open_issues=["structure issue somewhere"],
        updated_at="2026-01-01T00:00:00",
    )
    return root


def test_build_review_prompt_with_ledgers(tmp_path):

    root = _ledger_root(tmp_path)
    prompt = build_review_prompt(root)

    assert "GLOBAL cross-section review" in prompt
    assert "AGENTS.md" in prompt
    assert "section_status.json" in prompt
    assert "introduction.summary.md" in prompt
    assert "literature_review.summary.md" in prompt
    # status digest is inlined
    assert "introduction: written, score pass" in prompt
    assert "full draft: 62/100 (fail)" in prompt
    # the five review dimensions
    for kw in (
        "Terminology",
        "Narrative",
        "redundancy",
        "Citation consistency",
        "Outline conformance",
    ):
        assert kw in prompt
    # strict output format contract
    assert "# Global Issues" in prompt
    assert "## GI-1 [high|medium|low] scope: global|<section name>" in prompt
    assert "Issue:" in prompt
    assert "Suggested fix:" in prompt
    assert "No cross-section issues found." in prompt


def test_build_review_prompt_empty_dir(tmp_path):

    prompt = build_review_prompt(tmp_path / "does_not_exist")
    assert "# Global Issues" in prompt
    assert "(status ledger is empty or missing)" in prompt
    assert "No section summaries found" in prompt


# ---------------------------------------------------------- paper map with ledgers


def test_paper_map_with_status_and_summary_ledgers(tmp_path):
    root = _ledger_root(tmp_path)
    (root / "drafts" / "01_introduction.md").write_text("intro words here", "utf-8")

    write_paper_map(root)
    text = (root / "AGENTS.md").read_text(encoding="utf-8")

    # extended Sections table with score/issues columns
    assert "| section | file | target words | words | status | score | issues |" in text
    assert "| introduction | drafts/01_introduction.md | ? | 3 | written | ✓ | 0 |" in text
    # open issues block with the full-draft score
    assert "## Open issues" in text
    assert "Full draft: 62/100 (fail)" in text
    # summary block
    assert "## Section summaries" in text
    assert "- introduction: Intro promises a comparative study." in text
    assert "- literature_review: Lit review covers A and B." in text


def test_paper_map_without_ledger_keeps_legacy_table(tmp_path):
    write_checkpoint(tmp_path, {"topic": "T", "word_targets": {}})
    write_paper_map(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "| section | file | target words | words | status |" in text
    assert "score" not in text.split("## Writing discipline")[0].split("| section |")[1][:200]
    assert "## Open issues" not in text
