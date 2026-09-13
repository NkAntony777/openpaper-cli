#!/usr/bin/env python3
"""
ABOUTME: `opendraft workflow` — host-harness mode CLI (init / next / finish).
ABOUTME: Machine-facing like tool/harness commands: progress to stderr, exactly
ABOUTME: one JSON envelope line on stdout. Exit codes: 0 ok, 1 failure, 2 usage.
"""

import argparse
import json
import sys
from pathlib import Path


def _emit(payload, code):
    # UTF-8 bytes to stdout regardless of console codepage — machine contract.
    line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    except (AttributeError, OSError):
        print(json.dumps(payload, ensure_ascii=False))
    return code


def _ok(data):
    return _emit({"ok": True, "data": data}, 0)


def _fail(error):
    return _emit({"ok": False, "error": error}, 1)


def run_workflow_command(argv):
    parser = argparse.ArgumentParser(
        prog="opendraft workflow",
        description=(
            "Host-harness mode: drive the paper workflow from YOUR harness "
            "(Claude Code, ZCode, Cursor, ...) via its shell tool. "
            "`next` reads disk state and returns the next task prompt."
        ),
    )
    sub = parser.add_subparsers(dest="workflow_cmd", metavar="<command>")
    p_init = sub.add_parser(
        "init", help="Prepare a paper directory (paper map + optional starter checkpoint)"
    )
    p_init.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Paper output directory (default: cwd)"
    )
    p_init.add_argument(
        "--topic",
        default=None,
        help="Paper topic — writes a starter checkpoint.json with default "
        "word targets when none exists",
    )
    p_init.add_argument("--lang", default="en", help="Paper language (default: en)")
    p_next = sub.add_parser(
        "next", help="Return the next task for the host agent (disk-truth state machine)"
    )
    p_next.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Paper output directory (default: cwd)"
    )
    p_next.add_argument(
        "--max-fix-rounds",
        type=int,
        default=1,
        help="Max fix rounds per section after global review (default 1)",
    )
    p_finish = sub.add_parser("finish", help="Run the finish gate (full score + acceptance)")
    p_finish.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Paper output directory (default: cwd)"
    )
    p_finish.add_argument(
        "--min-score", type=int, default=None, help="Full-paper quality floor (default 75)"
    )

    args = parser.parse_args(argv)
    if args.workflow_cmd not in ("init", "next", "finish"):
        parser.print_help()
        return 2

    sys.path.insert(0, str(Path(__file__).parent.parent))

    try:
        if args.workflow_cmd == "init":
            from harness.workflow import workflow_init

            return _ok(workflow_init(args.root, topic=args.topic, language=args.lang))
        if args.workflow_cmd == "next":
            from harness.workflow import workflow_next

            result = workflow_next(args.root, max_fix_rounds=args.max_fix_rounds)
            # `finish`/`done` results carry a pass/fail verdict; surface it in the
            # exit code so scripted loops can branch without parsing prompts.
            if result.get("phase") in ("finish", "done"):
                return _emit(
                    {"ok": bool(result.get("passed")), "data": result},
                    0 if result.get("passed") else 1,
                )
            return _ok(result)
        # -- finish
        from harness.workflow import workflow_finish

        result = workflow_finish(args.root, min_full_score=args.min_score)
        return _emit(
            {"ok": bool(result.get("passed")), "data": result}, 0 if result.get("passed") else 1
        )
    except Exception as e:  # noqa: BLE001 — machine contract: never traceback
        return _fail(f"{type(e).__name__}: {e}")
