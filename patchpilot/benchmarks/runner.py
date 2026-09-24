"""
PatchPilot Live Benchmark Runner.
Executes real empirical benchmarks on live models (Nemotron-3 Super 120B on Nebius + Tavily).
"""

import os
import sys
import shutil
import tempfile
import argparse
from dotenv import load_dotenv

# Load root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from patchpilot.types import DependencyDelta, VerificationContract, UpgradeStatus
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.failures import FailureNormalizer
from patchpilot.engine.evidence import TavilyEvidenceEngine
from patchpilot.engine.repair import NemotronRepairEngine
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.verifier import ContractVerificationEngine
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.controller import BoundedRecoveryController
from patchpilot.benchmarks.harness import BenchmarkHarness
from patchpilot.state import compute_file_sha256


class AdversarialRepairEngine(NemotronRepairEngine):
    """
    Subclass that forces a naive mistake on Candidate 1 (stripping mode='before'),
    demonstrating the mandatory FAIL -> ROLLBACK -> RETRY -> PASS loop.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempt_turn = 0

    def generate_candidate(self, delta, target_file, current_code, failures, docs_context, negative_feedback=None, iteration=1):
        self.attempt_turn += 1
        clean_code, meta = super().generate_candidate(
            delta, target_file, current_code, failures, docs_context, negative_feedback, iteration
        )

        if iteration == 1 and not negative_feedback:
            # Adversarially strip mode='before' to simulate naive codemod trap
            print("[ADVERSARIAL HARNESS] Injecting naive syntax mistake: stripping mode='before' on Candidate 1...")
            clean_code = clean_code.replace("mode='before'", "").replace('mode="before"', "")
            import re
            clean_code = re.sub(r",\s*mode=[\"']before[\"']", "", clean_code)

        return clean_code, meta


def setup_workspace(fixture_name: str) -> str:
    """Copies pristine fixture files into a temporary workspace for isolated benchmark execution."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", fixture_name)
    temp_dir = tempfile.mkdtemp(prefix=f"pp_bench_{fixture_name}_")
    for item in os.listdir(fixtures_dir):
        s = os.path.join(fixtures_dir, item)
        d = os.path.join(temp_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    return temp_dir


def run_single_file_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  SCENARIO 1: PYDANTIC SINGLE-FILE MIGRATION BENCHMARK")
    print("=" * 70)
    workspace = setup_workspace("single")
    try:
        delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)
        contract = VerificationContract(
            required_tests=["test_models.py"],
            allowed_file_scope=["models.py"],
            retry_budget=3,
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(log_path=os.path.join(harness.results_dir, "scenario_single_telemetry.jsonl"))
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
        )

        metrics = harness.run_benchmark(
            benchmark_id="bm_scenario_1_single",
            repo_dir=workspace,
            contract=contract,
            delta=delta,
            controller=controller,
        )
        assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
        print(f"[SUCCESS] Scenario 1 PASSED 100% GREEN (Runtime: {metrics.runtime_seconds:.1f}s, Cost: ${metrics.cost_usd:.4f})")
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_multifile_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  SCENARIO 2: PYDANTIC COUPLED MULTI-FILE BENCHMARK")
    print("=" * 70)
    workspace = setup_workspace("multifile")
    try:
        delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)
        contract = VerificationContract(
            required_tests=["tests/test_suite.py"],
            allowed_file_scope=["core/config.py", "core/schemas.py", "services/user_service.py"],
            retry_budget=3,
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(log_path=os.path.join(harness.results_dir, "scenario_multifile_telemetry.jsonl"))
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
        )

        metrics = harness.run_benchmark(
            benchmark_id="bm_scenario_2_multifile",
            repo_dir=workspace,
            contract=contract,
            delta=delta,
            controller=controller,
        )
        assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
        print(f"[SUCCESS] Scenario 2 PASSED 100% GREEN across 3 files (Runtime: {metrics.runtime_seconds:.1f}s, Cost: ${metrics.cost_usd:.4f})")
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_adversarial_rollback_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  SCENARIO 3: ADVERSARIAL TRAP -> FAIL -> ROLLBACK -> RETRY -> PASS")
    print("=" * 70)
    workspace = setup_workspace("adversarial")
    try:
        target_file = os.path.join(workspace, "service_model.py")
        hash_before = compute_file_sha256(target_file)
        print(f"[INITIAL BASELINE] Pristine SHA-256: {hash_before}")

        delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)
        contract = VerificationContract(
            required_tests=["test_service.py"],
            allowed_file_scope=["service_model.py"],
            retry_budget=3,
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(log_path=os.path.join(harness.results_dir, "scenario_adversarial_telemetry.jsonl"))
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=AdversarialRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
        )

        metrics = harness.run_benchmark(
            benchmark_id="bm_scenario_3_adversarial",
            repo_dir=workspace,
            contract=contract,
            delta=delta,
            controller=controller,
        )

        assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
        assert metrics.attempts >= 2, "Adversarial benchmark must perform at least 2 attempts (initial fail + retry)"
        assert metrics.rollback_count >= 1, "Adversarial benchmark must perform at least 1 verified rollback"

        print(f"[SUCCESS] Scenario 3 PROVEN: Candidate 1 Failed -> Rolled Back -> Candidate 2 Passed Green!")
        print(f"          Attempts: {metrics.attempts} | Rollbacks: {metrics.rollback_count} | Cost: ${metrics.cost_usd:.4f}")
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_sqlalchemy_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  SCENARIO 4: SQLALCHEMY 1.4 -> 2.0 GENERALIZATION BENCHMARK")
    print("=" * 70)
    workspace = setup_workspace("sqlalchemy")
    try:
        delta = DependencyDelta("sqlalchemy", "1.4.49", "2.0.28", "pyproject.toml", True)
        contract = VerificationContract(
            required_tests=["tests/test_repository.py"],
            allowed_file_scope=["models.py", "repository.py"],
            retry_budget=3,
            migration_assertions={"dependency": "sqlalchemy"},
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(log_path=os.path.join(harness.results_dir, "scenario_sqlalchemy_telemetry.jsonl"))
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
        )

        metrics = harness.run_benchmark(
            benchmark_id="bm_scenario_4_sqlalchemy",
            repo_dir=workspace,
            contract=contract,
            delta=delta,
            controller=controller,
        )
        assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
        print(f"[SUCCESS] Scenario 4 PASSED 100% GREEN for SQLAlchemy 2.0 (Runtime: {metrics.runtime_seconds:.1f}s, Cost: ${metrics.cost_usd:.4f})")
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_pristine_sqlalchemy_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  SCENARIO 5: PRISTINE SQLALCHEMY 1.4 -> 2.x MIGRATION BENCHMARK")
    print("  (Baseline committed to Git, zero pre-migrated 2.0 application code)")
    print("=" * 70)
    workspace = setup_workspace("sqlalchemy_pristine")
    try:
        delta = DependencyDelta("sqlalchemy", "1.4.52", "2.0.54", "pyproject.toml", is_major_bump=True)
        contract = VerificationContract(
            required_tests=["tests/test_user_repository.py"],
            allowed_file_scope=["models.py", "repository.py"],
            retry_budget=3,
            migration_assertions={"dependency": "sqlalchemy"},
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(log_path=os.path.join(harness.results_dir, "scenario_sqlalchemy_pristine_telemetry.jsonl"))
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
        )

        metrics = harness.run_benchmark(
            benchmark_id="bm_scenario_5_sqlalchemy_pristine",
            repo_dir=workspace,
            contract=contract,
            delta=delta,
            controller=controller,
        )
        assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
        print(f"[SUCCESS] Scenario 5 PASSED 100% GREEN for Pristine SQLAlchemy 1.4 -> 2.0!")
        print(f"          Runtime: {metrics.runtime_seconds:.1f}s | Cost: ${metrics.cost_usd:.4f} | Rollbacks: {metrics.rollback_count}")
        return True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_competitor_baseline_benchmark(harness: BenchmarkHarness) -> bool:
    print("\n" + "=" * 70)
    print("  COMPETITOR BASELINE: GENERAL CODING AGENT VS PATCHPILOT")
    print("=" * 70)
    from patchpilot.benchmarks.competitor_baseline import run_neutral_comparison
    comparison = run_neutral_comparison("sqlalchemy_pristine")
    gen = comparison["general_baseline"]
    pp = comparison["patchpilot"]
    print("[COMPETITOR BASELINE COMPARISON RESULTS]")
    print(f"  Target Repository : {comparison['target_repository']}")
    print(f"  Dependency        : {comparison['dependency']} ({comparison['version_jump']})")
    print(f"  General Agent     : Initial={gen['initial_failures']}, Final={gen['final_failures']}, Passed={gen['verification_passed']}, Cost=${gen['cost_usd']:.4f}")
    print(f"  PatchPilot        : Initial={pp['initial_failures']}, Final={pp['final_failures']}, Passed={pp['verification_passed']}, Cost=${pp['cost_usd']:.4f}")
    return pp['verification_passed']


def main():
    parser = argparse.ArgumentParser(description="PatchPilot Benchmark Runner")
    parser.add_argument("--scenario", choices=["single", "multifile", "adversarial", "sqlalchemy", "sqlalchemy_pristine", "baseline_compare", "all"], default="all")
    parser.add_argument("--results-dir", default=os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks", "results"))
    args = parser.parse_args()

    harness = BenchmarkHarness(results_dir=args.results_dir)

    success = True
    if args.scenario in ["single", "all"]:
        s1 = run_single_file_benchmark(harness)
        success = success and s1

    if args.scenario in ["multifile", "all"]:
        s2 = run_multifile_benchmark(harness)
        success = success and s2

    if args.scenario in ["adversarial", "all"]:
        s3 = run_adversarial_rollback_benchmark(harness)
        success = success and s3

    if args.scenario in ["sqlalchemy", "all"]:
        s4 = run_sqlalchemy_benchmark(harness)
        success = success and s4

    if args.scenario in ["sqlalchemy_pristine", "all"]:
        s5 = run_pristine_sqlalchemy_benchmark(harness)
        success = success and s5

    if args.scenario in ["baseline_compare", "all"]:
        s6 = run_competitor_baseline_benchmark(harness)
        success = success and s6

    print("\n" + "=" * 70)
    print(f"  BENCHMARK SUITE COMPLETE -> ALL PASSING: {success}")
    print("=" * 70)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
