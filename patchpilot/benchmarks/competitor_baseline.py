"""
Neutral Competitor Baseline Experiment.
Compares the behavior of a general-purpose unconstrained coding agent baseline
against PatchPilot's specialized upgrade recovery pipeline on the exact same broken dependency upgrade repository.
"""

import os
import sys
import time
import shutil
import tempfile
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from patchpilot.types import DependencyDelta, VerificationContract, UpgradeStatus
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.failures import FailureNormalizer
from patchpilot.engine.repair import NemotronRepairEngine
from patchpilot.engine.evidence import TavilyEvidenceEngine
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.verifier import ContractVerificationEngine
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.controller import BoundedRecoveryController


@dataclass
class BaselineComparisonRecord:
    system_name: str
    target_dependency: str
    initial_failures: int
    final_failures: int
    verification_passed: bool
    iterations_used: int
    files_modified: List[str]
    rollbacks_executed: int
    runtime_seconds: float
    cost_usd: float
    human_interventions: int
    behavior_notes: str


class GeneralAgentBaselineRunner:
    """
    Simulates a standard unconstrained coding agent workflow:
    - Receives a single prompt with test failure output and files.
    - Generates full file replacements without impact graph, without topological sequencing,
      without upstream migration doc retrieval, and without atomic rollback safety.
    """

    def __init__(self, repair_engine: NemotronRepairEngine, sandbox: LocalSubprocessDriver, verifier: ContractVerificationEngine, analyzer: FailureNormalizer):
        self.repair_engine = repair_engine
        self.sandbox = sandbox
        self.verifier = verifier
        self.analyzer = analyzer

    def run_baseline(self, repo_dir: str, contract: VerificationContract, delta: DependencyDelta) -> BaselineComparisonRecord:
        t0 = time.time()

        # Step 1: Run initial test suite to obtain failure log
        cmd = [sys.executable, "-m", "pytest"] + contract.required_tests + ["-v"]
        rc, out, _ = self.sandbox.run_command(cmd, cwd=repo_dir, timeout_seconds=contract.timeout_seconds)
        initial_failures = self.analyzer.parse_test_output("gen_base_init", out, delta.package_name)
        init_fail_count = len(initial_failures)

        if rc == 0 and init_fail_count == 0:
            return BaselineComparisonRecord(
                system_name="General-Purpose Agent (Single Prompt)",
                target_dependency=delta.package_name,
                initial_failures=0,
                final_failures=0,
                verification_passed=True,
                iterations_used=0,
                files_modified=[],
                rollbacks_executed=0,
                runtime_seconds=round(time.time() - t0, 2),
                cost_usd=0.0,
                human_interventions=0,
                behavior_notes="Repository tests passed without modifications.",
            )

        # Step 2: Unconstrained repair attempt without topological order or upstream evidence
        files_modified = []
        total_cost = 0.0

        for fpath in contract.allowed_file_scope:
            full_path = os.path.join(repo_dir, fpath)
            if not os.path.isfile(full_path):
                continue

            with open(full_path, "r", encoding="utf-8") as f:
                code_before = f.read()

            # Generic prompt without upstream docs_context
            fixed_code, meta = self.repair_engine.generate_candidate(
                delta=delta,
                target_file=fpath,
                current_code=code_before,
                failures=initial_failures,
                docs_context="",  # General agent operates purely on parametric knowledge
                negative_feedback=None,
                iteration=1,
            )
            total_cost += meta.get("cost_usd", 0.0)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)
            files_modified.append(fpath)

        # Step 3: Single evaluation without retry or rollback
        eval_result = self.verifier.verify_candidate(
            candidate_id="gen_agent_final",
            repo_dir=repo_dir,
            contract=contract,
            baseline_failures=initial_failures,
            sandbox=self.sandbox,
            failure_analyzer=self.analyzer,
        )

        elapsed = round(time.time() - t0, 2)
        behavior = (
            "One-shot unconstrained generation without impact graph or rollback. "
            f"Resulted in {'clean pass' if eval_result.passed else 'unresolved or regression failures'}."
        )

        return BaselineComparisonRecord(
            system_name="General-Purpose Agent (Unconstrained Baseline)",
            target_dependency=delta.package_name,
            initial_failures=init_fail_count,
            final_failures=eval_result.tests_failed,
            verification_passed=eval_result.passed,
            iterations_used=1,
            files_modified=files_modified,
            rollbacks_executed=0,  # General agent lacks rollback
            runtime_seconds=elapsed,
            cost_usd=round(total_cost, 6),
            human_interventions=0,
            behavior_notes=behavior,
        )


def run_neutral_comparison(fixture_name: str = "sqlalchemy_pristine") -> Dict[str, Any]:
    """
    Executes both the General Agent Baseline and PatchPilot on identical copies
    of the broken dependency fixture, returning structured comparative metrics.
    """
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", fixture_name)
    nebius_key = os.environ.get("NEBIUS_API_KEY", "")
    tavily_key = os.environ.get("TAVILY_API_KEY", "")

    # Workspace 1 for General Agent
    ws_general = tempfile.mkdtemp(prefix="pp_comp_general_")
    shutil.copytree(fixtures_dir, ws_general, dirs_exist_ok=True)

    # Workspace 2 for PatchPilot
    ws_patchpilot = tempfile.mkdtemp(prefix="pp_comp_patchpilot_")
    shutil.copytree(fixtures_dir, ws_patchpilot, dirs_exist_ok=True)

    delta = DependencyDelta("sqlalchemy", "1.4.52", "2.0.54", "pyproject.toml", is_major_bump=True)
    contract = VerificationContract(
        required_tests=["tests/test_user_repository.py"],
        allowed_file_scope=["models.py", "repository.py"],
        retry_budget=3,
        timeout_seconds=20,
    )

    try:
        # Run General Agent Baseline
        repair_engine = NemotronRepairEngine(api_key=nebius_key)
        sandbox = LocalSubprocessDriver()
        verifier = ContractVerificationEngine()
        analyzer = FailureNormalizer()

        gen_runner = GeneralAgentBaselineRunner(repair_engine, sandbox, verifier, analyzer)
        gen_result = gen_runner.run_baseline(ws_general, contract, delta)

        # Run PatchPilot Pipeline
        logger = JsonlEventLogger()
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=sandbox,
            verifier=verifier,
            failure_analyzer=analyzer,
            recorder=logger,
        )

        pp_metrics = controller.execute_recovery(
            repo_dir=ws_patchpilot,
            contract=contract,
            delta=delta,
            run_id="comp_patchpilot",
        )

        pp_result = BaselineComparisonRecord(
            system_name="PatchPilot (Autonomous Upgrade Recovery)",
            target_dependency=delta.package_name,
            initial_failures=pp_metrics.baseline_failure_count,
            final_failures=pp_metrics.tests_before - pp_metrics.tests_after if pp_metrics.final_status != UpgradeStatus.VERIFIED_GREEN else 0,
            verification_passed=(pp_metrics.final_status == UpgradeStatus.VERIFIED_GREEN),
            iterations_used=pp_metrics.attempts,
            files_modified=pp_metrics.affected_files,
            rollbacks_executed=pp_metrics.rollback_count,
            runtime_seconds=pp_metrics.runtime_seconds,
            cost_usd=pp_metrics.cost_usd,
            human_interventions=0,
            behavior_notes=(
                f"Impact graph ordered ({' -> '.join(pp_metrics.repair_ordering)}), "
                f"retrieved upstream evidence, executed bounded repairs with rollback safety."
            ),
        )

        return {
            "target_repository": fixture_name,
            "dependency": delta.package_name,
            "version_jump": f"{delta.old_version} -> {delta.new_version}",
            "general_baseline": asdict(gen_result),
            "patchpilot": asdict(pp_result),
        }

    finally:
        shutil.rmtree(ws_general, ignore_errors=True)
        shutil.rmtree(ws_patchpilot, ignore_errors=True)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    print("Running Neutral Competitor Baseline Experiment...")
    res = run_neutral_comparison("sqlalchemy_pristine")
    import json
    print(json.dumps(res, indent=2))
