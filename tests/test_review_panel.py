#!/usr/bin/env python3
"""Offline tests for the blind review panel (engine/harness/review_panel.py) and
its integration into the workflow state machine. All disk-driven, no LLM/network."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from harness.review_panel import (
    ADJUDICATION_REL,
    REVIEWS_DIR_REL,
    SEAT_FOCUS,
    SEAT_ORDER,
    build_panel_dispatch_prompt,
    build_synthesis_prompt,
    seat_card,
)
from harness.workflow import (
    FIX_REPORT_REL,
    _fix_report_digest,
    plan_sections,
    workflow_next,
)

from tests.test_workflow_cli import _pass_all_sections

# ------------------------------------------------------------------- seat cards


def test_panel_has_four_fixed_seats():
    assert SEAT_ORDER == ["methodology", "domain", "coherence", "devils_advocate"]
    assert all(focus.strip() for focus in SEAT_FOCUS.values())


def test_seat_cards_carry_the_iron_rules(poc_root):
    for seat in SEAT_ORDER:
        card = seat_card(poc_root, seat)
        # blind: commits own findings without reading peers
        assert "do not read other seats" in card.lower()
        # read-only: the only write is the seat's own report
        assert "READ-ONLY".lower() in card.lower() or "read-only" in card.lower()
        assert f"{REVIEWS_DIR_REL}/{seat}.md" in card
        # specific findings contract (no generic feedback)
        assert "severity" in card and "Suggested fix" in card
        # provenance honesty (borrowed from the reviewer skill)
        assert "not a claim of independent error processes" in card
        # seat angle present
        assert SEAT_FOCUS[seat].split(".")[0] in card


def test_seat_card_unknown_seat(poc_root):
    with pytest.raises(KeyError):
        seat_card(poc_root, "eic")


def test_devils_advocate_card_has_critical_convention(poc_root):
    card = seat_card(poc_root, "devils_advocate")
    assert "CRITICAL" in card
    assert "counter-argument" in card


# ------------------------------------------------------------ dispatch/synthesis


def test_dispatch_prompt_spawns_subagents_and_declares_fallback(poc_root):
    prompt = build_panel_dispatch_prompt(poc_root)
    assert "subagent" in prompt
    # one card per seat, verbatim
    for seat in SEAT_ORDER:
        assert f"seat: {seat}" in prompt
    # degraded-mode provenance disclosure
    assert "single-context panel (degraded)" in prompt
    assert "opendraft workflow next" in prompt


def test_dispatch_prompt_resumes_only_missing_seats(poc_root):
    d = poc_root / REVIEWS_DIR_REL
    d.mkdir()
    (d / "methodology.md").write_text("# Review — methodology\n", encoding="utf-8")
    prompt = build_panel_dispatch_prompt(poc_root)
    assert "1/4" in prompt
    assert "methodology" in prompt.split("SEAT CARDS")[0]  # resume state line
    # the reported seat's card is not re-dispatched
    cards = prompt.split("SEAT CARDS")[1]
    assert "seat: methodology" not in cards
    assert "seat: domain" in cards


def test_synthesis_prompt_iron_rules(poc_root):
    for seat in SEAT_ORDER:
        (poc_root / REVIEWS_DIR_REL).mkdir(exist_ok=True)
        (poc_root / REVIEWS_DIR_REL / f"{seat}.md").write_text(
            f"# Review — {seat}\n", encoding="utf-8"
        )
    prompt = build_synthesis_prompt(poc_root)
    assert "TRACEABLE" in prompt and "(methodology)" in prompt
    assert "NO FABRICATION" in prompt and ADJUDICATION_REL in prompt
    assert "[da-critical]" in prompt
    assert "global_issues.md" in prompt


# ------------------------------------------------------- state machine integration


def test_review_phase_is_panel_first(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    out = workflow_next(poc_root)
    assert out["phase"] == "review"
    assert out["stage"] == "panel"
    assert out["seats_missing"] == SEAT_ORDER
    assert "subagent" in out["prompt"].lower()


def test_review_phase_partial_reports_still_panel(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    d = poc_root / REVIEWS_DIR_REL
    d.mkdir()
    (d / "coherence.md").write_text("x", encoding="utf-8")
    out = workflow_next(poc_root)
    assert out["stage"] == "panel"
    assert out["seats_reported"] == ["coherence"]
    assert "coherence" not in out["seats_missing"]


def test_review_phase_synthesize_when_all_seats_report(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    d = poc_root / REVIEWS_DIR_REL
    d.mkdir()
    for seat in SEAT_ORDER:
        (d / f"{seat}.md").write_text(f"# Review — {seat}\n", encoding="utf-8")
    out = workflow_next(poc_root)
    assert out["stage"] == "synthesize"
    assert "TRACEABLE" in out["prompt"]


# ------------------------------------------------------------------- fix report


def test_fix_report_digest_counts_verdicts(poc_root):
    (poc_root / FIX_REPORT_REL).write_text(
        "| GI-1 | FIXED | methodology | file line 12 |\n"
        "| GI-2 | NOT FIXED | results | needs new data |\n"
        "| GI-3 | ADJUDICATED (da-critical) | — | see reviews/adjudication.md |\n",
        encoding="utf-8",
    )
    digest = _fix_report_digest(poc_root)
    assert digest["verdicts"] == {"FIXED": 1, "NOT FIXED": 1, "ADJUDICATED": 1}
    assert digest["issues_traced"] == 3


def test_fix_report_digest_absent(poc_root):
    assert _fix_report_digest(poc_root) is None


def test_finish_result_carries_fix_report(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    (poc_root / "global_issues.md").write_text(
        "# Global Issues\n\nNo cross-section issues found.\n", encoding="utf-8"
    )
    (poc_root / FIX_REPORT_REL).write_text(
        "| GI-1 | FIXED | methodology | ok |\n", encoding="utf-8"
    )
    out = workflow_next(poc_root)
    assert out["phase"] == "finish"
    assert out["fix_report"]["verdicts"]["FIXED"] == 1


def test_fix_prompt_requires_traceability_row(poc_root):
    from harness.section_task import build_fix_prompt

    prompt = build_fix_prompt(poc_root, "methodology", [{"id": "GI-1", "issue": "x"}])
    assert FIX_REPORT_REL in prompt
    assert "ADJUDICATED" in prompt  # da-critical findings cannot be silently dropped
