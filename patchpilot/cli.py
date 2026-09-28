"""
PatchPilot Command Line Interface (CLI).
Provides developer and CI commands:
- recover: Run bounded autonomous recovery on a repository
- demo: Run the canonical live recovery demonstration
- benchmark: Execute empirical benchmark scenarios
"""

import os
import sys
import argparse
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


def cmd_recover(args: argparse.Namespace) -> int:
    """Executes authentic recovery on a specified repository."""
    from patchpilot.ci.github_runner import run_ci_recovery

    repo_dir = os.path.abspath(args.repo)
    print(f"[PatchPilot CLI] Starting recovery on repository: {repo_dir}")
    if args.package:
        print(f"[PatchPilot CLI] Targeted upgrade package: {args.package}")

    rc = run_ci_recovery(
        repo_dir=repo_dir,
        package_name=args.package,
        output_report_path=args.report_out,
        telemetry_log_path=args.telemetry_out,
        retry_budget=args.retry_budget,
    )
    return rc


def cmd_demo(args: argparse.Namespace) -> int:
    """Executes the canonical recovery demo."""
    if args.replay:
        from patchpilot.demo.replay import replay_seeded_demo
        res = replay_seeded_demo(target_dir=args.target_dir, run_id=args.run_id)
    else:
        from patchpilot.demo.canonical import run_canonical_demo
        res = run_canonical_demo(target_dir=args.target_dir, run_id=args.run_id)

    return 0 if res.get("status") == "verified_green" else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Executes benchmark scenarios."""
    from patchpilot.benchmarks.run_suite import (
        run_all_live_benchmarks,
        load_all_benchmark_results,
        display_benchmark_matrix,
        display_competitor_comparison,
    )
    from rich.console import Console
    console = Console()

    if args.run_all:
        success = run_all_live_benchmarks()
        results = load_all_benchmark_results()
        display_benchmark_matrix(results, console)
        display_competitor_comparison(console)
        return 0 if success else 1
    else:
        results = load_all_benchmark_results()
        display_benchmark_matrix(results, console)
        display_competitor_comparison(console)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchpilot",
        description="PatchPilot: Autonomous Breaking-Change Dependency Upgrade Recovery Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: recover
    p_recover = subparsers.add_parser("recover", help="Recover breaking dependency changes in a repository")
    p_recover.add_argument("--repo", "-r", default=".", help="Path to repository to recover")
    p_recover.add_argument("--package", "-p", default=None, help="Explicit target dependency package name")
    p_recover.add_argument("--retry-budget", type=int, default=3, help="Max repair iterations per failure file")
    p_recover.add_argument("--report-out", default="patchpilot_report.md", help="Markdown summary report output path")
    p_recover.add_argument("--telemetry-out", default="patchpilot_telemetry.jsonl", help="Telemetry log output path")
    p_recover.set_defaults(func=cmd_recover)

    # Command: demo
    p_demo = subparsers.add_parser("demo", help="Run the canonical recovery demo")
    p_demo.add_argument("--replay", action="store_true", help="Run replay walkthrough instead of live execution")
    p_demo.add_argument("--target-dir", default="runs", help="Output directory for run artifacts")
    p_demo.add_argument("--run-id", default="canonical_live_demo", help="Run identifier")
    p_demo.set_defaults(func=cmd_demo)

    # Command: benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run empirical benchmark suite")
    p_bench.add_argument("--run-all", action="store_true", help="Execute all 5 benchmark scenarios live")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
