"""
Contract-Based Verification Engine.
Evaluates candidate patches against required test suites and regression criteria.
"""

import os
import sys
import time
from typing import List, Optional
from patchpilot.types import (
    VerificationContract,
    CandidateEvaluation,
    FailureRecord,
)
from patchpilot.contracts import VerificationEngine, SandboxDriver, FailureAnalyzer


class ContractVerificationEngine(VerificationEngine):
    """Executes multi-stage verification gates and evaluates regression boundaries."""

    def verify_candidate(
        self,
        candidate_id: str,
        repo_dir: str,
        contract: VerificationContract,
        baseline_failures: List[FailureRecord],
        sandbox: SandboxDriver,
        failure_analyzer: FailureAnalyzer,
    ) -> CandidateEvaluation:
        t0 = time.time()
        combined_output = ""
        overall_exit_code = 0

        # Stage 1: Run required test suites
        for test_target in contract.required_tests:
            cmd = [sys.executable, "-m", "pytest", test_target, "-v"]
            rc, out, dur = sandbox.run_command(cmd, cwd=repo_dir, timeout_seconds=contract.timeout_seconds)
            combined_output += f"\n--- Test Output ({test_target}) ---\n" + out
            if rc != 0:
                overall_exit_code = rc
                break  # Fail fast on first failing required suite

        tc_passed: Optional[bool] = None
        lint_passed: Optional[bool] = None

        # Stage 1b: Run optional lint command if specified in contract
        if overall_exit_code == 0 and contract.lint_command:
            lint_cmd = contract.lint_command if isinstance(contract.lint_command, list) else contract.lint_command.split()
            rc_lint, out_lint, _ = sandbox.run_command(lint_cmd, cwd=repo_dir, timeout_seconds=contract.timeout_seconds)
            combined_output += f"\n--- Lint Output ---\n" + out_lint
            lint_passed = (rc_lint == 0)
            if rc_lint != 0:
                overall_exit_code = rc_lint

        # Stage 1c: Run optional typecheck command if specified in contract
        if overall_exit_code == 0 and contract.typecheck_command:
            typecheck_cmd = contract.typecheck_command if isinstance(contract.typecheck_command, list) else contract.typecheck_command.split()
            rc_tc, out_tc, _ = sandbox.run_command(typecheck_cmd, cwd=repo_dir, timeout_seconds=contract.timeout_seconds)
            combined_output += f"\n--- Typecheck Output ---\n" + out_tc
            tc_passed = (rc_tc == 0)
            if rc_tc != 0:
                overall_exit_code = rc_tc
        elif contract.typecheck_command and overall_exit_code != 0:
            tc_passed = False

        # Stage 2: Parse current failure records
        current_failures: List[FailureRecord] = []
        dep_name = contract.migration_assertions.get("dependency", "python")
        if overall_exit_code != 0:
            current_failures = failure_analyzer.parse_test_output(
                run_id=candidate_id,
                test_output=combined_output,
                dependency=dep_name,
            )

        # Stage 3: Detect regressions against baseline
        comparison = failure_analyzer.compare_failures(baseline_failures, current_failures)

        # Count passing and failing tests from pytest summary if available
        passed_count = combined_output.count(" PASSED")
        failed_count = len(current_failures)

        is_passed = (overall_exit_code == 0) and (not comparison.has_regressions)

        elapsed_ms = (time.time() - t0) * 1000
        return CandidateEvaluation(
            candidate_id=candidate_id,
            passed=is_passed,
            exit_code=overall_exit_code,
            tests_passed=passed_count,
            tests_failed=failed_count,
            regressions=comparison.new_regressions,
            failure_records=current_failures,
            raw_output=combined_output,
            duration_ms=elapsed_ms,
            typecheck_passed=tc_passed,
            lint_passed=lint_passed,
        )
