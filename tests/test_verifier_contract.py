"""
Enforceable Verification Contract Tests.
Proves that VerificationContract functions as a strict acceptance boundary:
- Real typecheck gate execution via mypy
- Rejection of candidate patches that pass pytest but fail mypy type-checking
- Acceptance only when all required tests and typecheck gates succeed
"""

import sys
import pytest
from patchpilot.types import VerificationContract, FailureRecord
from patchpilot.verifier import ContractVerificationEngine
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.failures import FailureNormalizer


def test_verification_contract_enforces_real_mypy_typecheck(tmp_path):
    """
    Candidate passes pytest, but introduces a genuine typing error.
    The VerificationContract specifies mypy as the typecheck_command.
    The verifier must reject the candidate as FAILED.
    """
    repo = tmp_path / "typecheck_repo"
    repo.mkdir()

    # Code passes pytest runtime assertions, but has static typing defect:
    # returns int 123 for function annotated to return str
    (repo / "typed_module.py").write_text(
        "def get_user_id() -> str:\n"
        "    return 123  # type: ignore[return-value] -> removed to trigger error\n",
        encoding="utf-8"
    )
    (repo / "test_module.py").write_text(
        "from typed_module import get_user_id\n"
        "def test_runtime():\n"
        "    assert get_user_id() == 123\n",
        encoding="utf-8"
    )

    contract = VerificationContract(
        required_tests=["test_module.py"],
        typecheck_command=[sys.executable, "-m", "mypy", "typed_module.py", "--no-error-summary"],
        allowed_file_scope=["typed_module.py"],
        timeout_seconds=20,
    )

    verifier = ContractVerificationEngine()
    sandbox = LocalSubprocessDriver()
    analyzer = FailureNormalizer()

    eval_result = verifier.verify_candidate(
        candidate_id="cand_type_error",
        repo_dir=str(repo),
        contract=contract,
        baseline_failures=[],
        sandbox=sandbox,
        failure_analyzer=analyzer,
    )

    # Pytest passed (tests_passed == 1), but typecheck failed
    assert eval_result.tests_passed == 1
    assert eval_result.typecheck_passed is False
    assert eval_result.passed is False
    assert eval_result.exit_code != 0
    assert "Incompatible return value type" in eval_result.raw_output or "typed_module.py:2" in eval_result.raw_output


def test_verification_contract_passes_when_both_test_and_mypy_succeed(tmp_path):
    """
    Candidate passes both pytest runtime assertions and static typechecking via mypy.
    The verifier must accept the candidate as PASSED.
    """
    repo = tmp_path / "clean_repo"
    repo.mkdir()

    (repo / "typed_module.py").write_text(
        "def get_user_name() -> str:\n"
        "    return 'valid_string'\n",
        encoding="utf-8"
    )
    (repo / "test_module.py").write_text(
        "from typed_module import get_user_name\n"
        "def test_runtime():\n"
        "    assert get_user_name() == 'valid_string'\n",
        encoding="utf-8"
    )

    contract = VerificationContract(
        required_tests=["test_module.py"],
        typecheck_command=[sys.executable, "-m", "mypy", "typed_module.py", "--no-error-summary"],
        allowed_file_scope=["typed_module.py"],
        timeout_seconds=20,
    )

    verifier = ContractVerificationEngine()
    sandbox = LocalSubprocessDriver()
    analyzer = FailureNormalizer()

    eval_result = verifier.verify_candidate(
        candidate_id="cand_clean",
        repo_dir=str(repo),
        contract=contract,
        baseline_failures=[],
        sandbox=sandbox,
        failure_analyzer=analyzer,
    )

    assert eval_result.passed is True
    assert eval_result.exit_code == 0
    assert eval_result.tests_passed == 1
    assert eval_result.typecheck_passed is True
