import os
import json
import pytest

from patchpilot.observability.server import determine_run_type
from patchpilot.observability.artifacts import RunArtifactBundle, ArtifactBundleExporter
from patchpilot.types import UpgradeSpec, VerificationContract


def test_determine_run_type_live_engine_run():
    prov = {
        "execution_mode": "live_controller",
        "backend_identity": "local_subprocess_isolated",
        "model_call_count": 2,
    }
    assert determine_run_type("canonical_live_demo", prov) == "LIVE ENGINE RUN"
    assert determine_run_type("custom_run_123", prov) == "LIVE ENGINE RUN"


def test_determine_run_type_replay_seeded():
    prov = {
        "execution_mode": "seeded_replay",
        "backend_identity": "local_subprocess_isolated",
    }
    assert determine_run_type("replay_seeded_demo", prov) == "REPLAY / SEEDED"
    assert determine_run_type("replay_demo_1", None) == "REPLAY / SEEDED"


def test_determine_run_type_github_and_benchmark():
    assert determine_run_type("gh_pr_sqlalchemy", None) == "GITHUB CI RUN"
    assert determine_run_type("bm_scenario_3_adversarial", None) == "BENCHMARK RESULT"


def test_provenance_json_bundle_export(tmp_path):
    spec = UpgradeSpec(
        package_name="test-pkg",
        old_version="1.0.0",
        new_version="2.0.0",
        manifest_path="pyproject.toml",
    )
    contract = VerificationContract(required_tests=["test_a.py"])
    prov = {
        "execution_mode": "live_controller",
        "backend_identity": "local_subprocess_isolated",
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "model_call_count": 2,
        "tavily_call_count": 1,
        "rollback_count": 1,
    }
    bundle = RunArtifactBundle(
        run_id="test_prov_run",
        upgrade_spec=spec,
        verification_contract=contract,
        verification_result={"status": "verified_green"},
        provenance=prov,
    )
    out_dir = ArtifactBundleExporter.export(bundle, base_output_dir=str(tmp_path))
    prov_file = os.path.join(out_dir, "provenance.json")
    assert os.path.isfile(prov_file)

    with open(prov_file, "r", encoding="utf-8") as f:
        loaded_prov = json.load(f)
    assert loaded_prov["execution_mode"] == "live_controller"
    assert loaded_prov["model_call_count"] == 2
    assert loaded_prov["rollback_count"] == 1

    loaded_bundle = ArtifactBundleExporter.load(out_dir)
    assert loaded_bundle.get("provenance") is not None
    assert loaded_bundle["provenance"]["execution_mode"] == "live_controller"
