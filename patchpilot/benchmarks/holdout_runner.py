"""
PatchPilot Holdout Generalization Benchmark Runner (Milestone 6).
Evaluates the authentic recovery engine on an un-benchmarked holdout library (Click 7 -> 8).
"""

import os
import sys
import shutil
import tempfile
from typing import Dict, Any
from dotenv import load_dotenv

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
from patchpilot.observability.audit import AuditLedgerVerifier


def run_holdout_benchmark(artifacts_dir: str = "runs") -> Dict[str, Any]:
    """
    Executes live recovery on the Click 7 -> 8 holdout fixture.
    """
    fixture_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "fixtures", "holdout_click")
    )
    temp_dir = tempfile.mkdtemp(prefix="pp_holdout_click_")
    repo_path = os.path.abspath(temp_dir)

    for item in os.listdir(fixture_dir):
        s = os.path.join(fixture_dir, item)
        d = os.path.join(repo_path, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)

    try:
        delta = DependencyDelta(
            package_name="click",
            old_version="7.1.2",
            new_version="8.1.7",
            manifest_path="pyproject.toml",
            is_major_bump=True,
        )
        contract = VerificationContract(
            required_tests=["test_formatter.py"],
            allowed_file_scope=["cli_formatter.py"],
            retry_budget=3,
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        logger = JsonlEventLogger(
            log_path=os.path.join(artifacts_dir, "bm_holdout_click_telemetry.jsonl")
        )
        controller = BoundedRecoveryController(
            evidence_engine=TavilyEvidenceEngine(api_key=tavily_key),
            repair_engine=NemotronRepairEngine(api_key=nebius_key),
            patch_manager=ScopeEnforcedPatchManager(),
            sandbox=LocalSubprocessDriver(),
            verifier=ContractVerificationEngine(),
            failure_analyzer=FailureNormalizer(),
            recorder=logger,
            artifacts_dir=artifacts_dir,
        )

        metrics = controller.execute_recovery(
            repo_dir=repo_path,
            contract=contract,
            delta=delta,
            run_id="bm_holdout_click",
        )

        bundle_dir = metrics.bundle_dir or os.path.join(artifacts_dir, "bm_holdout_click")
        audit_res = AuditLedgerVerifier.verify_run_bundle(bundle_dir)

        return {
            "status": metrics.final_status.value,
            "tests_passed": metrics.tests_after,
            "attempts": metrics.attempts,
            "rollbacks": metrics.rollback_count,
            "runtime_seconds": metrics.runtime_seconds,
            "audit_verified": audit_res.get("verified", False),
            "bundle_dir": bundle_dir,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    res = run_holdout_benchmark()
    print("HOLDOUT RESULT:", res)
    if res.get("status") == "verified_green":
        sys.exit(0)
    else:
        sys.exit(1)
