"""
Tests for Benchmark Truthfulness.
Verifies that missing benchmark result JSON files cannot masquerade as verified_green.
"""

import os
import tempfile
import pytest
from patchpilot.benchmarks.run_suite import load_all_benchmark_results


def test_missing_benchmark_results_do_not_produce_verified_green():
    with tempfile.TemporaryDirectory() as empty_dir:
        # Load results from an empty directory where no JSON files exist
        results = load_all_benchmark_results(results_dir=empty_dir)
        assert len(results) == 5

        for r in results:
            status = r.get("final_status", "")
            assert status != "verified_green", f"Fabricated verified_green found for {r.get('benchmark_id')}"
            assert status == "MISSING_RESULT"
            assert r.get("runtime_seconds") == 0.0
            assert r.get("cost_usd") == 0.0
            assert "not found" in r.get("error", "").lower()
