"""
PatchPilot Replay & Seeded Demonstration.
Provides deterministic artifact playback and educational demonstration of the recovery lifecycle.
Explicitly labeled as REPLAY / SEEDED DEMO without claiming live API execution.
"""

import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text

from patchpilot.types import (
    UpgradeSpec,
    VerificationContract,
    TelemetryEvent,
    NodeType,
    EdgeType,
)
from patchpilot.intelligence.graph import ImpactGraph, ImpactNode
from patchpilot.engine.evidence import EvidencePack, EvidenceItem
from patchpilot.observability.artifacts import (
    RunArtifactBundle,
    ArtifactBundleExporter,
    CandidateSummary,
)
from patchpilot.observability.audit import AuditLedgerVerifier
from patchpilot.state import SnapshotManager

console = Console()


def run_replay_demo(target_dir: Optional[str] = "runs", run_id: str = "replay_seeded_demo") -> Dict[str, Any]:
    console.print(Panel(
        Text(
            "PATCHPILOT // REPLAY & SEEDED DEMONSTRATION\n"
            "Pre-Seeded Walkthrough of Autonomous Breaking-Change Recovery State Machine",
            style="bold yellow",
            justify="center",
        ),
        border_style="yellow",
    ))

    temp_dir = tempfile.mkdtemp(prefix="pp_replay_demo_")
    repo_path = os.path.abspath(temp_dir)

    try:
        model_file = os.path.join(repo_path, "service_model.py")
        test_file = os.path.join(repo_path, "test_service.py")
        toml_file = os.path.join(repo_path, "pyproject.toml")

        initial_code = (
            "from pydantic import BaseModel, validator\n\n"
            "class UserModel(BaseModel):\n"
            "    user_id: int\n"
            "    username: str\n\n"
            "    @validator('user_id')\n"
            "    def validate_user_id(cls, v):\n"
            "        if v <= 0:\n"
            "            raise ValueError('user_id must be positive')\n"
            "        return v\n"
        )
        with open(model_file, "w", encoding="utf-8") as f:
            f.write(initial_code)

        test_code = (
            "import pytest\nfrom service_model import UserModel\n\n"
            "def test_valid_user():\n"
            "    u = UserModel(user_id=42, username='alice')\n"
            "    assert u.user_id == 42\n\n"
            "def test_invalid_user():\n"
            "    with pytest.raises(Exception):\n"
            "        UserModel(user_id=-1, username='bad')\n"
        )
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)

        with open(toml_file, "w", encoding="utf-8") as f:
            f.write('[project]\nname = "demo-service"\nversion = "0.1.0"\ndependencies = ["pydantic>=2.0.0"]\n')

        console.print("\n[bold yellow][STAGE 1/6: REPLAY RED][/bold yellow] Replaying Baseline Failure: [cyan]pydantic 1.10.14 -> 2.6.4[/cyan]")
        time.sleep(0.2)
        console.print("  [dim red]&cross; BASELINE FAILED[/dim red] (Replay)")

        console.print("\n[bold yellow][STAGE 2/6: REPLAY INVESTIGATE][/bold yellow] AST Impact Graph & Upstream Guidance...")
        tree = Tree("[bold cyan]Repository Impact Graph (Replay)[/bold cyan]")
        pkg_branch = tree.add("[magenta]Package: pydantic (2.6.4)[/magenta]")
        mod_branch = pkg_branch.add("[blue]Module: service_model.py[/blue] (Direct Import: `@validator`)")
        mod_branch.add("[green]Test: test_service.py[/green] (Validates `UserModel`)")
        console.print(tree)

        console.print("\n[bold yellow][STAGE 3/6: REPLAY TRY (ATTEMPT 1)][/bold yellow] Replaying Faulty Candidate...")
        snapshot_mgr = SnapshotManager(repo_path)
        snap1 = snapshot_mgr.create_snapshot("snap1", ["service_model.py"])

        bad_code = (
            "from pydantic import BaseModel, field_validator\n\n"
            "class UserModel(BaseModel):\n"
            "    user_id: int\n"
            "    username: str\n\n"
            "    @field_validator('non_existent_field')\n"
            "    @classmethod\n"
            "    def validate_user_id(cls, v):\n"
            "        if v <= 0:\n"
            "            raise ValueError('user_id must be positive')\n"
            "        return v\n"
        )
        with open(model_file, "w", encoding="utf-8") as f:
            f.write(bad_code)

        console.print("\n[bold yellow][STAGE 4/6: REPLAY FAIL & ROLLBACK][/bold yellow] Triggering Atomic Snapshot Rollback...")
        restored_ok = snapshot_mgr.restore_snapshot(snap1)
        post_snap = snapshot_mgr.create_snapshot("post_rollback", ["service_model.py"])
        match = (snap1.composite_tree_hash == post_snap.composite_tree_hash)
        console.print(f"  [green]&check; Atomic Rollback Successful![/green] Pre-patch hash == Restored hash: [bold cyan]{match}[/bold cyan]")

        console.print("\n[bold yellow][STAGE 5/6: REPLAY RECOVER][/bold yellow] Applying Remediated Candidate 2...")
        good_code = (
            "from pydantic import BaseModel, field_validator\n\n"
            "class UserModel(BaseModel):\n"
            "    user_id: int\n"
            "    username: str\n\n"
            "    @field_validator('user_id')\n"
            "    @classmethod\n"
            "    def validate_user_id(cls, v):\n"
            "        if v <= 0:\n"
            "            raise ValueError('user_id must be positive')\n"
            "        return v\n"
        )
        with open(model_file, "w", encoding="utf-8") as f:
            f.write(good_code)

        spec = UpgradeSpec("pydantic", "1.10.14", "2.6.4", "pyproject.toml", upgrade_type="major")
        contract = VerificationContract(
            required_tests=["test_service.py"],
            allowed_file_scope=["service_model.py", "pyproject.toml"],
            timeout_seconds=20,
            retry_budget=2,
        )

        graph = ImpactGraph(spec=spec)
        graph.add_node(ImpactNode("pkg:pydantic", "pydantic", NodeType.PACKAGE))
        graph.add_node(ImpactNode("mod:service_model", "service_model.py", NodeType.MODULE, file_path="service_model.py"))
        graph.add_node(ImpactNode("test:service", "test_service.py", NodeType.TEST, file_path="test_service.py"))
        graph.add_edge("pkg:pydantic", "mod:service_model", EdgeType.IMPORTS, "Imports deprecated validator")
        graph.add_edge("mod:service_model", "test:service", EdgeType.TESTS_MODULE, "Validates UserModel")

        ev = EvidenceItem(
            evidence_id="ev_replay_pydantic",
            cluster_id="cluster_validator",
            query="pydantic v2 validator migration",
            url="https://docs.pydantic.dev/latest/migration/#changes-to-validators",
            title="Pydantic V2 Migration Guide: Validators (Replay)",
            retrieved_timestamp=datetime.now(timezone.utc).isoformat(),
            relevant_content="@validator is replaced with @field_validator in V2 with classmethod.",
            source_authority="replay_cache",
        )
        pack = EvidencePack(spec=spec, items=[ev], cluster_evidence_map={"cluster_validator": [ev]}, status="REPLAY_CACHED")

        c1 = CandidateSummary(
            candidate_id=f"{run_id}_cand_1_faulty",
            iteration=1,
            hypothesis="Replay: Faulty patch with non-existent field",
            target_files=["service_model.py"],
            passed=False,
            status="rejected_rollback",
            exit_code=1,
            tests_passed=0,
            tests_failed=2,
            rollback_performed=True,
            duration_ms=450.0,
            unified_diff="--- a/service_model.py\n+++ b/service_model.py\n@@ -6,1 +6,2 @@\n-@validator('user_id')\n+@field_validator('non_existent_field')\n",
            evidence_ids=["ev_replay_pydantic"],
        )
        c2 = CandidateSummary(
            candidate_id=f"{run_id}_cand_2_valid",
            iteration=2,
            hypothesis="Replay: Remediated patch with @field_validator('user_id') and @classmethod",
            target_files=["service_model.py"],
            passed=True,
            status="verified",
            exit_code=0,
            tests_passed=2,
            tests_failed=0,
            rollback_performed=False,
            duration_ms=520.0,
            unified_diff="--- a/service_model.py\n+++ b/service_model.py\n@@ -6,2 +6,3 @@\n-@validator('user_id')\n+@field_validator('user_id')\n+@classmethod\n",
            evidence_ids=["ev_replay_pydantic"],
        )

        events_raw = [
            ("UPGRADE_DETECTED", "controller", "ok", 0.0, {"package": "pydantic", "from": "1.10.14", "to": "2.6.4"}),
            ("BASELINE_STARTED", "sandbox", "running", 0.0, {}),
            ("BASELINE_FAILED", "sandbox", "failed", 720.0, {"exit_code": 1}),
            ("IMPACT_GRAPH_BUILT", "repo_analyzer", "ok", 15.0, {"nodes": 3, "edges": 2}),
            ("EVIDENCE_RETRIEVED", "evidence", "ok", 380.0, {"citations": 1}),
            ("PATCH_APPLIED", "patch_manager", "ok", 2.0, {"candidate_id": c1.candidate_id}),
            ("VERIFICATION_FAILED", "verifier", "failed", 450.0, {"candidate_id": c1.candidate_id, "exit_code": 1}),
            ("ROLLBACK_TRIGGERED", "state_manager", "ok", 8.0, {"candidate_id": c1.candidate_id, "match": match}),
            ("PATCH_APPLIED", "patch_manager", "ok", 3.0, {"candidate_id": c2.candidate_id}),
            ("VERIFICATION_PASSED", "verifier", "ok", 520.0, {"candidate_id": c2.candidate_id, "tests_passed": 2}),
            ("FINAL_VERIFICATION_PASSED", "verifier", "ok", 610.0, {"tests_passed": 2}),
            ("RECOVERY_COMPLETED", "controller", "ok", 0.0, {"status": "verified_green", "rollbacks": 1}),
        ]

        telemetry_events: List[TelemetryEvent] = []
        prev_hash = "0" * 64
        for idx, (etype, comp, st, dur, meta) in enumerate(events_raw, start=1):
            ev = TelemetryEvent(
                run_id=run_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=etype,
                component=comp,
                status=st,
                duration_ms=dur,
                metadata=meta,
                sequence_number=idx,
                event_id=f"ev_{run_id}_{idx:04d}",
                backend_identity="local_subprocess_isolated",
                previous_hash=prev_hash,
            )
            ev.event_hash = ev.compute_hash(prev_hash)
            prev_hash = ev.event_hash
            telemetry_events.append(ev)

        bundle = RunArtifactBundle(
            run_id=run_id,
            upgrade_spec=spec,
            impact_graph=graph,
            failure_clusters=[],
            risk_map=None,
            evidence_pack=pack,
            verification_contract=contract,
            candidates=[c1, c2],
            recovery_history=[e.to_dict() for e in telemetry_events],
            telemetry_events=telemetry_events,
            final_diff="--- a/service_model.py\n+++ b/service_model.py\n@@ -1,3 +1,4 @@\n-@validator('user_id')\n+@field_validator('user_id')\n+@classmethod\n",
            verification_result={
                "status": "verified_green",
                "seal": "VERIFIED_GREEN",
                "tests_passed": 2,
                "tests_failed": 0,
                "typecheck_passed": True,
                "lint_passed": True,
                "scope_confinement": True,
                "rollbacks_executed": 1,
                "duration_seconds": 3.8,
                "run_type": "REPLAY_SEEDED_DEMO",
            },
            root_hash=prev_hash,
            backend_identity="local_subprocess_isolated",
            provenance={
                "execution_mode": "replay_seeded",
                "backend_identity": "local_subprocess_isolated",
                "model_id": "nvidia/nemotron-3-super-120b-a12b",
                "model_call_count": 0,
                "tavily_call_count": 0,
                "candidate_count": 2,
                "rollback_count": 1,
                "live_api_status": {"tavily": "REPLAY_CACHED", "nebius": "REPLAY_CACHED"},
            },
        )

        out_dir = ArtifactBundleExporter.export(bundle, base_output_dir=target_dir)
        audit_res = AuditLedgerVerifier.verify_run_bundle(out_dir)

        console.print(Panel(
            f"[bold yellow]REPLAY DEMONSTRATION COMPLETE[/bold yellow]\n"
            f"Run Bundle: [cyan]{out_dir}[/cyan]\n"
            f"Chained Events: [bold]{len(telemetry_events)}[/bold]\n"
            f"Root Hash: [cyan]{prev_hash}[/cyan]\n"
            f"Status: REPLAY / SEEDED DEMO (No live API calls made)",
            border_style="yellow",
        ))

        return {
            "status": "verified_green",
            "run_id": run_id,
            "bundle_dir": out_dir,
            "root_hash": prev_hash,
            "audit_verified": audit_res.get("verified", False),
            "rollbacks": 1,
            "attempts": 2,
            "mode": "replay",
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


replay_seeded_demo = run_replay_demo
