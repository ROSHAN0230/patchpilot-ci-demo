"""
GitHub Action Runner for PatchPilot.
Automates autonomous recovery on dependency upgrade Pull Requests in GitHub Actions CI.
"""

import os
import sys
import json
import argparse
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from patchpilot.types import UpgradeSpec, DependencyDelta, VerificationContract, UpgradeStatus
from patchpilot.intelligence.manifest import ManifestAnalyzer
from patchpilot.engine.evidence import TavilyEvidenceEngine
from patchpilot.engine.repair import NemotronRepairEngine
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.verifier import ContractVerificationEngine
from patchpilot.failures import FailureNormalizer
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.controller import BoundedRecoveryController


def run_ci_recovery(
    repo_dir: str,
    package_name: Optional[str] = None,
    output_report_path: str = "patchpilot_pr_report.md",
    telemetry_log_path: str = "patchpilot_telemetry.jsonl",
    retry_budget: int = 3,
) -> int:
    """
    Entrypoint for GitHub Action CI step.
    Detects upgrade, coordinates autonomous recovery, and generates PR comment artifact.
    """
    if repo_dir == "." and not os.path.isfile("pyproject.toml") and os.path.isfile(os.path.join("demo_app", "pyproject.toml")):
        repo_dir = "demo_app"

    manifest_analyzer = ManifestAnalyzer(default_trigger="github_action")
    target_package = package_name if (package_name and package_name.strip()) else None
    spec = manifest_analyzer.detect_upgrade(repo_dir, package_hint=target_package)

    if not spec:
        print("[PatchPilot CI] No dependency upgrade detected in manifests. Exiting successfully.")
        return 0

    print(f"[PatchPilot CI] Detected upgrade: {spec.package_name} ({spec.old_version} -> {spec.new_version})")

    # Discover test files
    tests_dir = os.path.join(repo_dir, "tests")
    test_suite = ["tests"] if os.path.isdir(tests_dir) else ["."]

    # Discover candidate files from manifest analyzer or AST analyzer
    analysis = manifest_analyzer.detect_delta(repo_dir)
    delta = spec.to_delta()

    from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
    ast_analyzer = AstRepositoryAnalyzer()
    repo_analysis = ast_analyzer.analyze_repository(repo_dir, spec.package_name)

    affected_files = sorted(list(repo_analysis.directly_affected_files.union(repo_analysis.transitively_affected_files)))
    if not affected_files:
        # Fallback to all non-test python files
        affected_files = [
            f for f in repo_analysis.modules.keys() if not repo_analysis.modules[f].is_test
        ]

    contract = VerificationContract(
        required_tests=test_suite,
        allowed_file_scope=affected_files,
        retry_budget=retry_budget,
        migration_assertions={"dependency": spec.package_name},
    )

    nebius_key = os.environ.get("NEBIUS_API_KEY", "")
    tavily_key = os.environ.get("TAVILY_API_KEY", "")

    recorder = JsonlEventLogger(log_path=telemetry_log_path)
    controller = BoundedRecoveryController(
        evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
        repair_engine=NemotronRepairEngine(api_key=nebius_key),
        patch_manager=ScopeEnforcedPatchManager(),
        sandbox=LocalSubprocessDriver(),
        verifier=ContractVerificationEngine(),
        failure_analyzer=FailureNormalizer(),
        recorder=recorder,
    )

    metrics = controller.execute_recovery(
        repo_dir=repo_dir,
        contract=contract,
        delta=delta,
        run_id=f"gh_pr_{spec.package_name}",
    )

    # Generate PR report markdown
    report_md = recorder.generate_report(metrics)
    with open(output_report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"[PatchPilot CI] Recovery finished with status: {metrics.final_status.value.upper()}")
    print(f"[PatchPilot CI] Report generated at: {output_report_path}")

    # Set GitHub Actions step outputs if running in GH Actions
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output and os.path.isfile(gh_output):
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"status={metrics.final_status.value}\n")
            f.write(f"attempts={metrics.attempts}\n")
            f.write(f"rollbacks={metrics.rollback_count}\n")
            f.write(f"runtime_seconds={metrics.runtime_seconds}\n")
            f.write(f"cost_usd={metrics.cost_usd}\n")
            f.write(f"report_path={output_report_path}\n")

    return 0 if metrics.final_status == UpgradeStatus.VERIFIED_GREEN else 1


def main():
    parser = argparse.ArgumentParser(description="PatchPilot GitHub Action PR Runner")
    parser.add_argument("--repo-dir", default=".", help="Root of repository under test")
    parser.add_argument("--package", default=None, help="Explicit package name if targeted")
    parser.add_argument("--report-out", default="patchpilot_pr_report.md", help="Output PR markdown file")
    parser.add_argument("--telemetry-out", default="patchpilot_telemetry.jsonl", help="Output telemetry file")
    parser.add_argument("--retry-budget", type=int, default=3, help="Max repair iterations per file")
    args = parser.parse_args()

    rc = run_ci_recovery(
        repo_dir=args.repo_dir,
        package_name=args.package,
        output_report_path=args.report_out,
        telemetry_log_path=args.telemetry_out,
        retry_budget=args.retry_budget,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
