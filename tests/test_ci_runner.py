"""
Unit Tests for GitHub Action CI Integration.
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from patchpilot.ci.github_runner import run_ci_recovery
from patchpilot.types import BenchmarkMetrics, UpgradeStatus, DependencyDelta


def test_ci_recovery_no_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty repo with no manifest
        rc = run_ci_recovery(repo_dir=tmpdir)
        assert rc == 0


def test_ci_recovery_full_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create manifest
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pydantic>=2.6.4"]\n')

        os.makedirs(os.path.join(tmpdir, "tests"), exist_ok=True)
        with open(os.path.join(tmpdir, "models.py"), "w") as f:
            f.write("from pydantic import BaseModel\nclass User(BaseModel): id: int\n")
        with open(os.path.join(tmpdir, "tests", "test_models.py"), "w") as f:
            f.write("from models import User\ndef test_u(): assert User(id=1).id == 1\n")

        report_file = os.path.join(tmpdir, "test_report.md")
        gh_output_file = os.path.join(tmpdir, "gh_output.txt")
        open(gh_output_file, "w").close()

        mock_metrics = BenchmarkMetrics(
            benchmark_id="gh_pr_pydantic",
            repository="demo",
            dependency_delta=DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True),
            baseline_status="passed",
            baseline_failure_count=0,
            affected_files=["models.py"],
            candidate_count=0,
            attempts=0,
            rollback_count=0,
            final_status=UpgradeStatus.VERIFIED_GREEN,
            tests_before=0,
            tests_after=1,
            runtime_seconds=1.2,
            model_tokens_input=0,
            model_tokens_output=0,
            tavily_calls=0,
            cost_usd=0.0,
            impact_graph_nodes=5,
            impact_graph_edges=4,
            cluster_count=0,
            repair_ordering=["models.py"],
            verification_contract_result="VERIFIED_GREEN",
        )

        with patch("patchpilot.controller.BoundedRecoveryController.execute_recovery", return_value=mock_metrics):
            with patch.dict(os.environ, {"GITHUB_OUTPUT": gh_output_file}):
                rc = run_ci_recovery(
                    repo_dir=tmpdir,
                    output_report_path=report_file,
                    telemetry_log_path=os.path.join(tmpdir, "events.jsonl"),
                )

        assert rc == 0
        assert os.path.isfile(report_file)
        with open(report_file, "r") as f:
            content = f.read()
        assert "VERIFIED_GREEN" in content or "Verified" in content

        with open(gh_output_file, "r") as f:
            gh_out_content = f.read()
        assert "status=verified_green" in gh_out_content
        assert "cost_usd=0.0" in gh_out_content
