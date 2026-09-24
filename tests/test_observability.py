"""
Tests for PatchPilot Observability Server, API endpoints, Cryptographic Audit Ledger,
and CLI Dashboard (Milestone 4).
"""

import os
import json
import pytest
import subprocess
import sys
from fastapi.testclient import TestClient

from patchpilot.observability.server import app
from patchpilot.observability.audit import AuditLedgerVerifier
from patchpilot.observability.artifacts import ArtifactBundleExporter
from patchpilot.observability.seed_runs import seed_all_runs


@pytest.fixture(scope="module", autouse=True)
def ensure_seeded_runs():
    seed_all_runs("runs")


@pytest.fixture
def client():
    return TestClient(app)


def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "patchpilot-observability"


def test_api_list_runs(client):
    res = client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()
    assert len(runs) >= 3
    run_ids = [r["run_id"] for r in runs]
    assert "gh_pr_sqlalchemy" in run_ids
    assert "bm_scenario_5_sqlalchemy_pristine" in run_ids
    assert "bm_scenario_3_adversarial" in run_ids

    # Every seeded run must have ledger_verified == True
    for r in runs:
        if r["run_id"] in ["gh_pr_sqlalchemy", "bm_scenario_5_sqlalchemy_pristine", "bm_scenario_3_adversarial"]:
            assert r["ledger_verified"] is True
            assert len(r["root_hash"]) == 64


def test_api_get_run_bundle(client):
    res = client.get("/api/runs/gh_pr_sqlalchemy")
    assert res.status_code == 200
    bundle = res.json()
    assert bundle["run_id"] == "gh_pr_sqlalchemy"
    assert bundle["upgrade_spec"]["package_name"] == "sqlalchemy"
    assert bundle["upgrade_spec"]["new_version"] == "2.0.54"
    assert len(bundle["candidates"]) >= 1
    assert bundle["candidates"][0]["passed"] is True
    assert "DeclarativeBase" in bundle["final_diff"]
    assert bundle["audit_verification"]["verified"] is True


def test_api_audit_verification_endpoint(client):
    res = client.get("/api/runs/bm_scenario_3_adversarial/audit")
    assert res.status_code == 200
    audit = res.json()
    assert audit["verified"] is True
    assert audit["root_hash_match"] is True
    assert audit["events_checked"] >= 10
    assert len(audit["computed_root_hash"]) == 64


def test_api_diff_endpoint(client):
    res = client.get("/api/runs/bm_scenario_5_sqlalchemy_pristine/diff")
    assert res.status_code == 200
    diff_data = res.json()
    assert diff_data["run_id"] == "bm_scenario_5_sqlalchemy_pristine"
    assert diff_data["total_lines"] > 0
    types = {line["type"] for line in diff_data["parsed_lines"]}
    assert "addition" in types
    assert "deletion" in types


def test_api_benchmarks_and_competitor_matrix(client):
    res = client.get("/api/benchmarks")
    assert res.status_code == 200
    bm = res.json()
    assert "benchmark_scenarios" in bm
    assert "competitor_comparison" in bm
    assert len(bm["competitor_comparison"]) >= 4
    dim_names = [d["dimension"] for d in bm["competitor_comparison"]]
    assert any("Accuracy" in name for name in dim_names)
    assert any("Rollback" in name for name in dim_names)


def test_api_github_proof(client):
    res = client.get("/api/github_proof")
    assert res.status_code == 200
    proof = res.json()
    assert proof["repository"] == "ROSHAN0230/patchpilot-ci-demo"
    assert proof["pull_request_number"] == 1
    assert proof["workflow_conclusion"] == "success"
    assert "83d9fc4a4805c87a5e88ee7ff96cf5d2cf57ea78" in proof["bot_commit_sha"]


def test_dashboard_ui_html(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "PATCHPILOT" in html
    assert "Autonomous Breaking-Change Recovery" in html
    assert "Dependency Impact Graph" in html
    assert "Candidate Lifecycle & Rollback" in html
    assert "CRYPTOGRAPHIC AUDIT SEAL" in html


def test_audit_ledger_tamper_detection(tmp_path):
    # Create valid run directory
    test_run_dir = tmp_path / "tamper_test_run"
    test_run_dir.mkdir()
    
    # Write valid chained events
    telemetry_file = test_run_dir / "telemetry.jsonl"
    from patchpilot.types import TelemetryEvent
    ev1 = TelemetryEvent("t1", "2026-09-24T00:00:00Z", "START", "ctrl", "ok", 0.0, sequence_number=1, event_id="ev_1", previous_hash="0"*64)
    ev1.event_hash = ev1.compute_hash("0"*64)
    ev2 = TelemetryEvent("t1", "2026-09-24T00:00:01Z", "FAIL", "sandbox", "failed", 10.0, sequence_number=2, event_id="ev_2", previous_hash=ev1.event_hash)
    ev2.event_hash = ev2.compute_hash(ev1.event_hash)

    with open(telemetry_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(ev1.to_dict()) + "\n")
        f.write(json.dumps(ev2.to_dict()) + "\n")

    manifest_file = test_run_dir / "audit_manifest.json"
    manifest_data = {
        "run_id": "tamper_test_run",
        "root_hash": ev2.event_hash,
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # 1. Verify clean run passes
    clean_audit = AuditLedgerVerifier.verify_run_bundle(str(test_run_dir))
    assert clean_audit["verified"] is True
    assert clean_audit["root_hash_match"] is True

    # 2. Tamper: modify event 1 payload after hash computation
    ev1_tampered = ev1.to_dict()
    ev1_tampered["status"] = "tampered_status"
    with open(telemetry_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(ev1_tampered) + "\n")
        f.write(json.dumps(ev2.to_dict()) + "\n")

    tampered_audit = AuditLedgerVerifier.verify_run_bundle(str(test_run_dir))
    assert tampered_audit["verified"] is False
    assert "Hash mismatch at sequence 1" in tampered_audit["error"]


def test_cli_verification():
    cmd = [sys.executable, "-m", "patchpilot.observability.cli", "--verify-all"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0
    assert "runs verified tamper-free" in proc.stdout
