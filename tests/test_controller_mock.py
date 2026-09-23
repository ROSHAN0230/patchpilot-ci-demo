"""
Test Suite for BoundedRecoveryController State Transitions and Retry Budgets.
"""

import os
import shutil
import tempfile
import pytest
from typing import List, Dict, Optional, Tuple, Any
from patchpilot.types import (
    DependencyDelta,
    VerificationContract,
    CandidatePatch,
    CandidateEvaluation,
    FailureRecord,
    UpgradeStatus,
)
from patchpilot.contracts import (
    EvidenceEngine,
    RepairEngine,
    PatchManager,
    SandboxDriver,
    VerificationEngine,
    FailureAnalyzer,
)
from patchpilot.failures import FailureNormalizer
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.controller import BoundedRecoveryController


class MockEvidenceEngine(EvidenceEngine):
    def search_migration_docs(self, delta, failures):
        return "Mock migration docs for Pydantic V2", [{"title": "Doc", "url": "https://example.com"}]


class MockRepairEngine(RepairEngine):
    def __init__(self, candidate_sequence: List[str]):
        self.candidate_sequence = candidate_sequence
        self.call_count = 0

    def generate_candidate(self, delta, target_file, current_code, failures, docs_context, negative_feedback=None, iteration=1):
        idx = min(self.call_count, len(self.candidate_sequence) - 1)
        code = self.candidate_sequence[idx]
        self.call_count += 1
        meta = {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0001}
        return code, meta


class MockSandboxDriver(SandboxDriver):
    def __init__(self, exit_codes: List[int]):
        self.exit_codes = exit_codes
        self.call_count = 0

    def get_backend_name(self):
        return "local_subprocess_isolated"

    def run_command(self, cmd, cwd, timeout_seconds=30):
        idx = min(self.call_count, len(self.exit_codes) - 1)
        rc = self.exit_codes[idx]
        self.call_count += 1
        out = "FAILED tests/test_foo.py::test_bar" if rc != 0 else "3 passed in 0.1s"
        return rc, out, 10.0


class MockVerifier(VerificationEngine):
    def __init__(self, pass_sequence: List[bool]):
        self.pass_sequence = pass_sequence
        self.call_count = 0

    def verify_candidate(self, candidate_id, repo_dir, contract, baseline_failures, sandbox, failure_analyzer):
        idx = min(self.call_count, len(self.pass_sequence) - 1)
        is_pass = self.pass_sequence[idx]
        self.call_count += 1
        return CandidateEvaluation(
            candidate_id=candidate_id,
            passed=is_pass,
            exit_code=0 if is_pass else 1,
            tests_passed=3 if is_pass else 1,
            tests_failed=0 if is_pass else 2,
            failure_records=[] if is_pass else [FailureRecord("c", "t", "f", 1, "s", "Err", "msg", "", "pydantic", "cat")],
        )


@pytest.fixture
def temp_repo():
    d = tempfile.mkdtemp(prefix="pp_mock_ctrl_")
    f = os.path.join(d, "model.py")
    with open(f, "w", encoding="utf-8") as fp:
        fp.write("class User:\n    pass\n")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_controller_success_after_one_rollback(temp_repo):
    # Candidate 1 fails, Candidate 2 passes
    repair = MockRepairEngine([
        "class User:\n    # Candidate 1 (will fail)\n    pass\n",
        "class User:\n    # Candidate 2 (will pass)\n    id: int\n",
    ])
    sandbox = MockSandboxDriver([1, 1, 0, 0])  # baseline fails, cand 1 fails, cand 2 passes
    verifier = MockVerifier([False, True, True])  # cand 1 fails, cand 2 passes, final eval passes

    logger = JsonlEventLogger()
    controller = BoundedRecoveryController(
        evidence_engine=MockEvidenceEngine(),
        repair_engine=repair,
        patch_manager=ScopeEnforcedPatchManager(),
        sandbox=sandbox,
        verifier=verifier,
        failure_analyzer=FailureNormalizer(),
        recorder=logger,
    )

    contract = VerificationContract(
        required_tests=["tests/test_model.py"],
        allowed_file_scope=["model.py"],
        retry_budget=3,
    )
    delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)

    metrics = controller.execute_recovery(temp_repo, contract, delta, "mock_test_run")

    assert metrics.final_status == UpgradeStatus.VERIFIED_GREEN
    assert metrics.attempts == 2
    assert metrics.rollback_count == 1

    # Verify event types logged
    event_types = [e.event_type for e in logger.events]
    assert "UPGRADE_DETECTED" in event_types
    assert "BASELINE_FAILED" in event_types
    assert "ROLLBACK_STARTED" in event_types
    assert "ROLLBACK_COMPLETED" in event_types
    assert "VERIFICATION_PASSED" in event_types


def test_controller_retry_budget_exhaustion(temp_repo):
    # All candidates fail
    repair = MockRepairEngine(["class User:\n    # always fails\n    pass\n"])
    sandbox = MockSandboxDriver([1])
    verifier = MockVerifier([False])  # always fails

    logger = JsonlEventLogger()
    controller = BoundedRecoveryController(
        evidence_engine=MockEvidenceEngine(),
        repair_engine=repair,
        patch_manager=ScopeEnforcedPatchManager(),
        sandbox=sandbox,
        verifier=verifier,
        failure_analyzer=FailureNormalizer(),
        recorder=logger,
    )

    contract = VerificationContract(
        required_tests=["tests/test_model.py"],
        allowed_file_scope=["model.py"],
        retry_budget=2,  # Max 2 attempts
    )
    delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)

    metrics = controller.execute_recovery(temp_repo, contract, delta, "mock_exhaust_run")

    assert metrics.final_status == UpgradeStatus.BUDGET_EXHAUSTED
    assert metrics.attempts == 2
    assert metrics.rollback_count == 2
    event_types = [e.event_type for e in logger.events]
    assert "BUDGET_EXHAUSTED" in event_types
