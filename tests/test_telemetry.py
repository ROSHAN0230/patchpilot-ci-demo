"""
Test Suite for Telemetry Logging and Markdown Reporting.
"""

import os
import json
import tempfile
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.types import BenchmarkMetrics, UpgradeStatus, DependencyDelta


def test_telemetry_event_logging():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        log_path = f.name

    try:
        logger = JsonlEventLogger(log_path=log_path)
        logger.record(
            run_id="run_test",
            event_type="UPGRADE_DETECTED",
            component="detector",
            status="ok",
            duration_ms=12.5,
            metadata={"package": "pydantic"},
        )
        logger.record(
            run_id="run_test",
            event_type="ROLLBACK_COMPLETED",
            component="state_manager",
            status="ok",
            duration_ms=4.1,
            metadata={"verified": True},
        )

        assert len(logger.events) == 2

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2
        d1 = json.loads(lines[0])
        assert d1["event_type"] == "UPGRADE_DETECTED"
        assert d1["metadata"]["package"] == "pydantic"

        d2 = json.loads(lines[1])
        assert d2["event_type"] == "ROLLBACK_COMPLETED"
    finally:
        if os.path.exists(log_path):
            os.remove(log_path)


def test_report_generation():
    logger = JsonlEventLogger()
    metrics = BenchmarkMetrics(
        benchmark_id="bm_pydantic_v2",
        repository="user-service",
        dependency_delta=DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True),
        baseline_status="failed",
        baseline_failure_count=3,
        affected_files=["core/schemas.py"],
        candidate_count=2,
        attempts=2,
        rollback_count=1,
        final_status=UpgradeStatus.VERIFIED_GREEN,
        tests_before=3,
        tests_after=3,
        runtime_seconds=14.2,
        model_tokens_input=2100,
        model_tokens_output=850,
        tavily_calls=1,
        cost_usd=0.00338,
    )

    report = logger.generate_report(metrics)
    assert "🟢 PatchPilot Recovery Evidence Report" in report
    assert "`pydantic` (`1.10.14` ➔ `2.6.4`)" in report
    assert "**Candidate Remediation Attempts**: 2" in report
    assert "**Rollbacks Executed & Verified**: 1" in report
    assert "$0.0034" in report


def test_audit_ledger_hash_chain_and_tamper_detection():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        log_path = f.name

    try:
        logger = JsonlEventLogger(log_path=log_path)
        e1 = logger.record("run_audit", "UPGRADE_DETECTED", "manifest", "ok", 5.0, {"pkg": "sqlalchemy"})
        e2 = logger.record("run_audit", "BASELINE_FAILED", "sandbox", "failed", 12.0, {"failures": 2})
        e3 = logger.record("run_audit", "ROLLBACK_COMPLETED", "state", "ok", 3.0, {"verified": True})
        e4 = logger.record("run_audit", "VERIFICATION_PASSED", "verifier", "ok", 4.0, {"passed": True})

        # 1. Verify sequence numbers and chaining
        assert e1.sequence_number == 1
        assert e2.sequence_number == 2
        assert e3.sequence_number == 3
        assert e4.sequence_number == 4

        assert e1.previous_hash == "0" * 64
        assert e2.previous_hash == e1.event_hash
        assert e3.previous_hash == e2.event_hash
        assert e4.previous_hash == e3.event_hash

        # 2. Verify root hash
        root_hash = logger.get_root_hash()
        assert root_hash == e4.event_hash
        assert len(root_hash) == 64

        # 3. Verify untampered ledger
        valid, err = logger.verify_hash_chain()
        assert valid is True
        assert err is None

        # 4. Reload from disk and verify
        reloaded = JsonlEventLogger.load_from_jsonl(log_path)
        valid_reloaded, err_reloaded = reloaded.verify_hash_chain()
        assert valid_reloaded is True
        assert err_reloaded is None
        assert reloaded.get_root_hash() == root_hash

        # 5. Tamper detection: mutate an event
        reloaded.events[1].metadata["failures"] = 999  # Tamper with event 2
        valid_tampered, err_tampered = reloaded.verify_hash_chain()
        assert valid_tampered is False
        assert "Hash mismatch at sequence 2" in err_tampered

    finally:
        if os.path.exists(log_path):
            os.remove(log_path)
