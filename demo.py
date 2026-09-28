#!/usr/bin/env python3
"""
PatchPilot Quickstart & Canonical Live Demo.
Executes the canonical recovery loop:
RED -> INVESTIGATE -> TRY -> FAIL -> RECOVER -> GREEN

By default, executes the live autonomous recovery engine end-to-end.
Pass --replay to inspect the fast deterministic walkthrough.
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="PatchPilot Canonical Recovery Demo",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Run the recorded replay walkthrough instead of live execution",
    )
    parser.add_argument(
        "--target-dir",
        default="runs",
        help="Target directory for output run artifacts",
    )
    parser.add_argument(
        "--run-id",
        default="canonical_live_demo",
        help="Run ID for the generated artifact bundle",
    )
    args = parser.parse_args()

    if args.replay:
        from patchpilot.demo.replay import replay_seeded_demo
        result = replay_seeded_demo(target_dir=args.target_dir, run_id=args.run_id)
    else:
        from patchpilot.demo.canonical import run_canonical_demo
        result = run_canonical_demo(target_dir=args.target_dir, run_id=args.run_id)

    if result.get("status") == "verified_green":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
