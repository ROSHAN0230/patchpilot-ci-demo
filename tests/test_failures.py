"""
Test Suite for Failure Normalization and Regression Comparison.
"""

from patchpilot.failures import FailureNormalizer
from patchpilot.types import FailureRecord


def test_failure_parsing():
    normalizer = FailureNormalizer()
    sample_pytest_output = """
============================= test session starts =============================
FAILED tests/test_service.py::test_event_metadata - pydantic.errors.PydanticUserError: `validator` is deprecated
FAILED tests/test_service.py::test_config - ModuleNotFoundError: No module named 'pydantic.BaseSettings'
======================== 2 failed, 1 passed in 0.12s =========================
"""
    records = normalizer.parse_test_output("run1", sample_pytest_output, "pydantic")
    assert len(records) == 2

    r1 = records[0]
    assert r1.file == "tests/test_service.py"
    assert r1.test_name == "test_event_metadata"
    assert r1.category == "validator_deprecation"

    r2 = records[1]
    assert r2.test_name == "test_config"
    assert r2.category == "missing_settings_package"


def test_failure_comparison_and_regression_detection():
    normalizer = FailureNormalizer()

    f1 = FailureRecord(
        run_id="run1",
        test_name="test_validator",
        file="tests/test_svc.py",
        line=10,
        symbol="validator",
        exception_type="PydanticUserError",
        message="validator is deprecated",
        stack_trace="",
        dependency="pydantic",
        category="validator_deprecation",
    )

    baseline = [f1]

    # Scenario A: Resolved
    comp_a = normalizer.compare_failures(baseline, [])
    assert comp_a.is_fully_resolved is True
    assert comp_a.has_regressions is False
    assert len(comp_a.resolved_failures) == 1

    # Scenario B: New regression introduced
    f_reg = FailureRecord(
        run_id="run1",
        test_name="test_serialization",
        file="tests/test_svc.py",
        line=25,
        symbol="model_dump",
        exception_type="AttributeError",
        message="object has no attribute 'dict'",
        stack_trace="",
        dependency="pydantic",
        category="model_dump_migration",
    )

    comp_b = normalizer.compare_failures(baseline, [f_reg])
    assert comp_b.is_fully_resolved is False
    assert comp_b.has_regressions is True
    assert len(comp_b.new_regressions) == 1
    assert comp_b.new_regressions[0].test_name == "test_serialization"
