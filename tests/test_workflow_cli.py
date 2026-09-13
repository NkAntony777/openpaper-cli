#!/usr/bin/env python3
"""Offline tests for the host-harness workflow state machine (engine/harness/workflow.py
+ `opendraft workflow` CLI). Everything is disk-truth driven: no pi, no LLM, no network."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from agent_tools.common import update_section_status
from harness.review_task import NO_ISSUES_TEXT
from harness.workflow import (
    DEFAULT_MIN_FULL_SCORE,
    parse_global_issues,
    plan_sections,
    workflow_finish,
    workflow_init,
    workflow_next,
)

POC = Path(__file__).parent / "fixtures" / "poc_output"


@pytest.fixture
def poc_root(tmp_path):
    """Copy the PoC fixture (bibliography + outline + checkpoint) into a tmp dir."""
    import shutil

    dest = tmp_path / "paper"
    shutil.copytree(POC, dest)
    return dest


def _pass_all_sections(root, sections):
    for s in sections:
        update_section_status(root, s, status="written", passed=True)


# ----------------------------------------------------------------------- init


def test_init_empty_dir_with_topic(tmp_path):
    root = tmp_path / "paper"
    out = workflow_init(root, topic="Retrieval-augmented generation")
    assert (root / "AGENTS.md").exists()
    assert (root / "checkpoint.json").exists()
    ckpt = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    assert ckpt["topic"] == "Retrieval-augmented generation"
    assert "literature_review" in ckpt["word_targets"]
    assert out["checkpoint"] == "created"
    assert "outline" in out["inventory"]["missing"]
    # appendices has no default target -> not in the plan
    assert "appendices" not in plan_sections(root)


def test_init_idempotent_and_keeps_existing_checkpoint(poc_root):
    before = (poc_root / "checkpoint.json").read_text(encoding="utf-8")
    out = workflow_init(poc_root, topic="nonsense-override")
    assert out["checkpoint"] == "present"
    assert (poc_root / "checkpoint.json").read_text(encoding="utf-8") == before
    assert (poc_root / "AGENTS.md").exists()


def test_next_uninitialized_dir(tmp_path):
    out = workflow_next(tmp_path)
    assert out["phase"] == "uninitialized"
    assert "workflow init" in out["prompt"]


# ---------------------------------------------------------------------- sections


def test_next_first_task_is_first_pending_section(poc_root):
    out = workflow_next(poc_root)
    assert out["phase"] == "sections"
    assert out["section"] == plan_sections(poc_root)[0]
    # CLI adapter header present and actionable
    assert "opendraft tool" in out["prompt"]
    assert "--args-file" in out["prompt"]


def test_next_skips_done_sections(poc_root):
    planned = plan_sections(poc_root)
    _pass_all_sections(poc_root, planned[:2])
    out = workflow_next(poc_root)
    assert out["phase"] == "sections"
    assert out["section"] == planned[2]


def test_next_review_after_all_sections(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    out = workflow_next(poc_root)
    assert out["phase"] == "review"
    assert "global_issues.md" in out["prompt"]


# ------------------------------------------------------------------------ fixes


def test_next_dispatches_fix_task_and_counts_rounds(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    (poc_root / "global_issues.md").write_text(
        "# Global Issues\n\n"
        "## GI-1 [high] scope: methodology\n"
        "Issue: methodology section claims X without a source\n"
        "Suggested fix: add a citation in methodology\n",
        encoding="utf-8",
    )
    # the fix target must itself be in a failing state to keep receiving rounds
    update_section_status(poc_root, "methodology", passed=False)
    out = workflow_next(poc_root, max_fix_rounds=2)
    assert out["phase"] == "fixes"
    assert out["section"] == "methodology"
    assert out["fix_round"] == 1
    # the round was persisted — with a budget of 2 the next call escalates to round 2
    out2 = workflow_next(poc_root, max_fix_rounds=2)
    assert out2["phase"] == "fixes"
    assert out2["fix_round"] == 2
    # with the default budget of 1 the next call falls through to a rework dispatch
    # (the section still does not pass on disk, so it must not be silently dropped)
    out3 = workflow_next(poc_root)
    assert out3["phase"] == "sections"
    assert out3["section"] == "methodology"
    assert out3.get("rework") is True


def test_next_fix_budget_exhausted_falls_back_to_rework(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    (poc_root / "global_issues.md").write_text(
        "# Global Issues\n\n"
        "## GI-1 [high] scope: methodology\n"
        "Issue: unsupported claim\n"
        "Suggested fix: cite a source in methodology\n",
        encoding="utf-8",
    )
    update_section_status(poc_root, "methodology", passed=False)
    workflow_next(poc_root)  # fix round 1 (default budget)
    out = workflow_next(poc_root)  # budget spent, section failing -> rework task
    assert out["phase"] == "sections"
    assert out["section"] == "methodology"
    assert "REWORK" in out["prompt"]


def test_next_done_section_confirmed_by_rescore_skipped(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    (poc_root / "global_issues.md").write_text(
        "# Global Issues\n\n"
        "## GI-1 [high] scope: methodology\n"
        "Issue: unsupported claim\n"
        "Suggested fix: cite a source in methodology\n",
        encoding="utf-8",
    )
    # dispatch the fix (round 1), then simulate the section re-passing on disk
    workflow_next(poc_root)
    update_section_status(poc_root, "methodology", passed=True, fix_rounds=1)
    out = workflow_next(poc_root)
    assert out["phase"] in ("finish", "done")


# ----------------------------------------------------------------------- finish


def test_finish_reports_disk_truth_gaps(poc_root):
    _pass_all_sections(poc_root, plan_sections(poc_root))
    (poc_root / "global_issues.md").write_text(
        "# Global Issues\n\nNo cross-section issues found.\n", encoding="utf-8"
    )
    out = workflow_next(poc_root)
    # ledger says passed but files are missing on disk -> gate must catch it
    assert out["phase"] == "finish"
    assert out["passed"] is False
    assert any("missing on disk" in g for g in out["gaps"])


def test_workflow_finish_min_score(poc_root):
    out = workflow_finish(poc_root, min_full_score=0)
    assert out["min_full_score"] == 0
    # sections are missing on disk -> not passed regardless of the score floor
    assert out["passed"] is False
    assert out["missing_sections"]


def test_default_min_score_is_75():
    assert DEFAULT_MIN_FULL_SCORE == 75


# ------------------------------------------------------------------- CLI wiring


def test_cli_workflow_dispatch(tmp_path, capsys):
    from opendraft.cli import run_workflow_command

    rc = run_workflow_command(["init", "--root", str(tmp_path / "paper"), "--topic", "T"])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and out["ok"] is True
    assert (tmp_path / "paper" / "AGENTS.md").exists()


def test_cli_next_finish_exit_codes(tmp_path, capsys):
    from opendraft.cli import run_workflow_command

    root = tmp_path / "paper"
    run_workflow_command(["init", "--root", str(root), "--topic", "T"])
    capsys.readouterr()

    rc = run_workflow_command(["next", "--root", str(root)])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and payload["data"]["phase"] == "sections"

    # drive to a failing finish gate: exit code 1 with ok=false
    _pass_all_sections(root, plan_sections(root))
    (root / "global_issues.md").write_text(
        "# Global Issues\n\nNo cross-section issues found.\n", encoding="utf-8"
    )
    rc = run_workflow_command(["next", "--root", str(root)])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 1 and payload["ok"] is False
    assert payload["data"]["phase"] == "finish"


def test_cli_bad_subcommand_usage(capsys):
    from opendraft.cli import run_workflow_command

    with pytest.raises(SystemExit) as exc:
        run_workflow_command(["bogus"])
    assert exc.value.code == 2


# --------------------------------------------------- global-issue parsing contract


def test_parse_global_issues_contract():
    text = (
        "# Global Issues\n\n"
        "## GI-1 [high] scope: methodology\nIssue: lacks detail.\nSuggested fix: add it.\n\n"
        "## GI-2 [low] scope: global\nIssue: drift.\n\n"
        "## GI-3 [medium] scope: introduction\nSuggested fix: strengthen.\n"
    )
    issues = parse_global_issues(text)
    assert [i["id"] for i in issues] == ["GI-1", "GI-2", "GI-3"]
    assert issues[0] == {
        "id": "GI-1",
        "severity": "high",
        "scope": "methodology",
        "issue": "lacks detail.",
        "fix": "add it.",
    }
    assert issues[1]["fix"] == ""  # missing Suggested fix tolerated
    assert issues[2]["issue"] == ""  # missing Issue line tolerated


def test_parse_global_issues_no_issues_text():
    assert parse_global_issues(NO_ISSUES_TEXT) == []
    assert parse_global_issues("") == []


def test_parse_global_issues_noise_and_defaults():
    text = (
        "random noise\n"
        "## GI-9 scope: results\nIssue: x\nSuggested fix: y\n"  # no severity bracket
        "## gi-10 [HIGH] scope: discussion\nIssue: z\nSuggested fix: w\n"
        "## GI-11 [medium]\nIssue: orphan scope\nSuggested fix: q\n"  # no scope -> global
    )
    issues = parse_global_issues(text)
    assert issues[0]["severity"] == "medium" and issues[0]["scope"] == "results"
    assert issues[1]["id"] == "gi-10" and issues[1]["severity"] == "high"
    assert issues[2]["scope"] == "global"
