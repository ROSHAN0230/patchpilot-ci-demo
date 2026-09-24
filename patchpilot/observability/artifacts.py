"""
Run Artifact Bundle Model and Exporter for PatchPilot.
Standardizes persistent, inspectable, secret-free artifact bundles per recovery case.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

from patchpilot.types import (
    UpgradeSpec,
    VerificationContract,
    CandidatePatch,
    CandidateEvaluation,
    BenchmarkMetrics,
    TelemetryEvent,
    UpgradeStatus,
)
from patchpilot.intelligence.graph import ImpactGraph
from patchpilot.intelligence.clusterer import FailureCluster
from patchpilot.intelligence.risk_map import MigrationRiskMap
from patchpilot.engine.evidence import EvidencePack


@dataclass
class CandidateSummary:
    candidate_id: str
    iteration: int
    hypothesis: str
    target_files: List[str]
    passed: bool
    status: str
    exit_code: int
    tests_passed: int
    tests_failed: int
    rollback_performed: bool
    duration_ms: float
    typecheck_passed: Optional[bool] = None
    lint_passed: Optional[bool] = None
    unified_diff: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class RunArtifactBundle:
    run_id: str
    upgrade_spec: UpgradeSpec
    impact_graph: Optional[ImpactGraph] = None
    failure_clusters: List[FailureCluster] = field(default_factory=list)
    risk_map: Optional[MigrationRiskMap] = None
    evidence_pack: Optional[EvidencePack] = None
    verification_contract: Optional[VerificationContract] = None
    candidates: List[CandidateSummary] = field(default_factory=list)
    recovery_history: List[Dict[str, Any]] = field(default_factory=list)
    telemetry_events: List[TelemetryEvent] = field(default_factory=list)
    final_diff: str = ""
    verification_result: Dict[str, Any] = field(default_factory=dict)
    root_hash: str = ""
    backend_identity: str = "local_subprocess_isolated"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArtifactBundleExporter:
    """Exports structured, immutable artifact bundles to a stable filesystem directory."""

    @staticmethod
    def export(bundle: RunArtifactBundle, base_output_dir: str = "runs") -> str:
        run_dir = os.path.join(base_output_dir, bundle.run_id)
        os.makedirs(run_dir, exist_ok=True)

        # 1. upgrade_spec.json
        with open(os.path.join(run_dir, "upgrade_spec.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(bundle.upgrade_spec), f, indent=2, default=str)

        # 2. impact_graph.json
        graph_data: Dict[str, Any] = {"nodes": [], "edges": [], "causal_paths": {}}
        if bundle.impact_graph:
            graph_data["nodes"] = [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type),
                    "file_path": n.file_path,
                    "metadata": getattr(n, "metadata", {}),
                }
                for n in bundle.impact_graph.nodes.values()
            ]
            graph_data["edges"] = [
                {
                    "source": getattr(e, "source", getattr(e, "source_id", "")),
                    "target": getattr(e, "target", getattr(e, "target_id", "")),
                    "type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
                    "explanation": getattr(e, "explanation", getattr(e, "rationale", "")),
                    "metadata": getattr(e, "metadata", {}),
                }
                for e in bundle.impact_graph.edges
            ]
            # Build machine-readable causal explanations
            causal = {}
            for nid, node in bundle.impact_graph.nodes.items():
                if getattr(node, "file_path", None) and hasattr(bundle.impact_graph, "explain_node_impact"):
                    try:
                        causal[node.file_path] = bundle.impact_graph.explain_node_impact(nid)
                    except Exception:
                        pass
            graph_data["causal_paths"] = causal

        with open(os.path.join(run_dir, "impact_graph.json"), "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2, default=str)

        # 3. failure_clusters.json
        clusters_data = []
        for c in bundle.failure_clusters:
            clusters_data.append({
                "cluster_id": getattr(c, "cluster_id", "c1"),
                "category": getattr(c, "failure_category", "unknown"),
                "representative_message": getattr(c, "representative_message", ""),
                "affected_files": getattr(c, "affected_files", []),
                "affected_tests": getattr(c, "affected_tests", []),
                "symbols": getattr(c, "symbols", []),
                "failure_count": len(getattr(c, "failures", [])),
                "evidence_references": getattr(c, "evidence_references", []),
            })
        with open(os.path.join(run_dir, "failure_clusters.json"), "w", encoding="utf-8") as f:
            json.dump(clusters_data, f, indent=2, default=str)

        # 4. risk_map.json
        risk_data: Dict[str, Any] = {}
        if bundle.risk_map:
            risk_data = {
                "uncertainty_score": getattr(bundle.risk_map, "uncertainty_score", 0.0),
                "package_name": getattr(bundle.risk_map, "package_name", ""),
                "upgrade_type": getattr(bundle.risk_map, "upgrade_type", "major"),
                "file_risks": [asdict(fr) if hasattr(fr, "__dataclass_fields__") else dict(fr) for fr in getattr(bundle.risk_map, "file_risks", [])],
                "untested_files": getattr(bundle.risk_map, "untested_files", []),
                "rationale": getattr(bundle.risk_map, "rationale", ""),
            }
        with open(os.path.join(run_dir, "risk_map.json"), "w", encoding="utf-8") as f:
            json.dump(risk_data, f, indent=2, default=str)

        # 5. evidence_pack.json
        evidence_data: List[Dict[str, Any]] = []
        if bundle.evidence_pack and hasattr(bundle.evidence_pack, "items"):
            for it in bundle.evidence_pack.items:
                evidence_data.append({
                    "evidence_id": getattr(it, "evidence_id", ""),
                    "cluster_id": getattr(it, "cluster_id", ""),
                    "query": getattr(it, "query", ""),
                    "url": getattr(it, "url", ""),
                    "title": getattr(it, "title", ""),
                    "domain": it.url.split("/")[2] if "://" in getattr(it, "url", "") else "official_docs",
                    "retrieved_timestamp": getattr(it, "retrieved_timestamp", ""),
                    "relevant_content": getattr(it, "relevant_content", "")[:1000],
                    "source_authority": getattr(it, "source_authority", "official_docs"),
                })
        with open(os.path.join(run_dir, "evidence_pack.json"), "w", encoding="utf-8") as f:
            json.dump(evidence_data, f, indent=2, default=str)

        # 6. verification_contract.json
        contract_data: Dict[str, Any] = {}
        if bundle.verification_contract:
            contract_data = {
                "required_tests": getattr(bundle.verification_contract, "required_tests", []),
                "allowed_file_scope": getattr(bundle.verification_contract, "allowed_file_scope", []),
                "timeout_seconds": getattr(bundle.verification_contract, "timeout_seconds", 30),
                "retry_budget": getattr(bundle.verification_contract, "retry_budget", 3),
                "migration_assertions": getattr(bundle.verification_contract, "migration_assertions", {}),
            }
        with open(os.path.join(run_dir, "verification_contract.json"), "w", encoding="utf-8") as f:
            json.dump(contract_data, f, indent=2, default=str)

        # 7. candidates.json
        candidates_data = [asdict(c) if hasattr(c, "__dataclass_fields__") else dict(c) for c in bundle.candidates]
        with open(os.path.join(run_dir, "candidates.json"), "w", encoding="utf-8") as f:
            json.dump(candidates_data, f, indent=2, default=str)

        # 8. recovery_history.json
        with open(os.path.join(run_dir, "recovery_history.json"), "w", encoding="utf-8") as f:
            json.dump(bundle.recovery_history, f, indent=2, default=str)

        # 9. telemetry.jsonl
        telemetry_file = os.path.join(run_dir, "telemetry.jsonl")
        with open(telemetry_file, "w", encoding="utf-8") as f:
            for ev in bundle.telemetry_events:
                ev_d = ev.to_dict() if hasattr(ev, "to_dict") else asdict(ev)
                f.write(json.dumps(ev_d, default=str) + "\n")

        # 10. final_diff.patch
        diff_file = os.path.join(run_dir, "final_diff.patch")
        with open(diff_file, "w", encoding="utf-8") as f:
            f.write(bundle.final_diff or "# No diff applied.\n")

        # 11. verification_result.json
        with open(os.path.join(run_dir, "verification_result.json"), "w", encoding="utf-8") as f:
            json.dump(bundle.verification_result, f, indent=2, default=str)

        # 12. audit_manifest.json (root seal with cryptographic hash)
        root_hash = bundle.root_hash
        if not root_hash and bundle.telemetry_events:
            root_hash = bundle.telemetry_events[-1].event_hash

        manifest_data = {
            "run_id": bundle.run_id,
            "target_package": bundle.upgrade_spec.package_name,
            "old_version": bundle.upgrade_spec.old_version,
            "new_version": bundle.upgrade_spec.new_version,
            "upgrade_type": getattr(bundle.upgrade_spec, "upgrade_type", "major"),
            "backend_identity": str(bundle.backend_identity),
            "root_hash": root_hash,
            "event_count": len(bundle.telemetry_events),
            "timestamp": bundle.created_at,
            "verification_seal": bundle.verification_result.get("seal", "UNVERIFIED"),
            "final_status": bundle.verification_result.get("status", "unknown"),
        }
        with open(os.path.join(run_dir, "audit_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, default=str)

        return run_dir

    @staticmethod
    def load(run_dir: str) -> Dict[str, Any]:
        """Loads all artifacts from a run directory into a unified dictionary."""
        data: Dict[str, Any] = {"run_dir": run_dir}
        for name in [
            "upgrade_spec.json",
            "impact_graph.json",
            "failure_clusters.json",
            "risk_map.json",
            "evidence_pack.json",
            "verification_contract.json",
            "candidates.json",
            "recovery_history.json",
            "verification_result.json",
            "audit_manifest.json",
        ]:
            p = os.path.join(run_dir, name)
            key = name.replace(".json", "")
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data[key] = json.load(f)
            else:
                data[key] = None

        diff_p = os.path.join(run_dir, "final_diff.patch")
        data["final_diff"] = ""
        if os.path.isfile(diff_p):
            with open(diff_p, "r", encoding="utf-8") as f:
                data["final_diff"] = f.read()

        telem_p = os.path.join(run_dir, "telemetry.jsonl")
        events = []
        if os.path.isfile(telem_p):
            with open(telem_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        data["telemetry_events"] = events

        return data
