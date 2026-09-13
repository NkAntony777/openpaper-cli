#!/usr/bin/env python3
"""
ABOUTME: `opendraft eval` — offline eval-suite metrics for a paper directory
ABOUTME: (quality score, claims cleanliness, citation authenticity). Machine
ABOUTME: contract like the other commands: one JSON envelope line on stdout;
ABOUTME: exit codes 0 passed / 1 failed / 2 usage.
"""

import argparse
import json
import sys
from pathlib import Path


def _emit(payload, code):
    line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    except (AttributeError, OSError):
        print(json.dumps(payload, ensure_ascii=False))
    return code


def run_eval_command(argv):
    parser = argparse.ArgumentParser(
        prog="opendraft eval",
        description="Offline eval-suite metrics for a paper directory (quality, claims, cites).",
    )
    parser.add_argument("--root", type=Path, required=True, help="Paper output directory")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from harness.eval_suite import evaluate_root

        metrics = evaluate_root(args.root)
    except Exception as e:  # noqa: BLE001 — machine contract: never traceback
        return _emit({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)

    print(
        f"[eval] quality={metrics.quality_score} clean={metrics.factcheck_clean} "
        f"cites={metrics.citation_rate:.2f} passed={metrics.passed}",
        file=sys.stderr,
        flush=True,
    )
    return _emit({"ok": metrics.passed, "data": metrics.to_dict()}, 0 if metrics.passed else 1)
