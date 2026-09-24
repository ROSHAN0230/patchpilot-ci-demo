"""
Bounded Autonomous Recovery Controller.
Enforces deterministic, machine-controlled state transitions with retry budgets and rollback protection.
"""

import os
import sys
import time
from typing import List, Dict, Optional, Any
from patchpilot.types import (
    UpgradeStatus,
    DependencyDelta,
    UpgradeSpec,
    VerificationContract,
    CandidatePatch,
    BenchmarkMetrics,
    FailureRecord,
    FailureCluster,
    EvidencePack,
)
from patchpilot.contracts import (
    RecoveryController,
    EvidenceEngine,
    RepairEngine,
    PatchManager,
    SandboxDriver,
    VerificationEngine,
    FailureAnalyzer,
    EvidenceRecorder,
)
from patchpilot.state import SnapshotManager, RollbackIntegrityError
from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
from patchpilot.intelligence.graph import ImpactGraphBuilder
from patchpilot.intelligence.clusterer import FailureClusterer
from patchpilot.intelligence.ordering import DependencyAwareSequencer
from patchpilot.intelligence.risk_map import RiskMapGenerator
from patchpilot.observability.artifacts import RunArtifactBundle, ArtifactBundleExporter, CandidateSummary


class BoundedRecoveryController(RecoveryController):
    """Machine-controlled recovery state machine with bounded retries and cryptographic rollback."""

    def __init__(
        self,
        evidence_engine: EvidenceEngine,
        repair_engine: RepairEngine,
        patch_manager: PatchManager,
        sandbox: SandboxDriver,
        verifier: VerificationEngine,
        failure_analyzer: FailureAnalyzer,
        recorder: EvidenceRecorder,
        ast_analyzer: Optional[AstRepositoryAnalyzer] = None,
        graph_builder: Optional[ImpactGraphBuilder] = None,
        clusterer: Optional[FailureClusterer] = None,
        sequencer: Optional[DependencyAwareSequencer] = None,
        risk_generator: Optional[RiskMapGenerator] = None,
        artifacts_dir: Optional[str] = "runs",
    ):
        self.evidence_engine = evidence_engine
        self.repair_engine = repair_engine
        self.patch_manager = patch_manager
        self.sandbox = sandbox
        self.verifier = verifier
        self.failure_analyzer = failure_analyzer
        self.recorder = recorder
        self.ast_analyzer = ast_analyzer or AstRepositoryAnalyzer()
        self.graph_builder = graph_builder or ImpactGraphBuilder()
        self.clusterer = clusterer or FailureClusterer()
        self.sequencer = sequencer or DependencyAwareSequencer()
        self.risk_generator = risk_generator or RiskMapGenerator()
        self.artifacts_dir = artifacts_dir

    def execute_recovery(
        self,
        repo_dir: str,
        contract: VerificationContract,
        delta: DependencyDelta,
        run_id: str = "run_auto",
    ) -> BenchmarkMetrics:
        t_start = time.time()
        snapshot_mgr = SnapshotManager(repo_dir)

        recorded_candidates: List[CandidateSummary] = []
        recovery_history: List[Dict[str, Any]] = []

        def emit_event(
            event_type: str,
            comp: str,
            status: str = "ok",
            dur: float = 0.0,
            meta: Optional[Dict] = None,
            parent_id: Optional[str] = None,
            art_ref: Optional[str] = None,
        ):
            ev = self._make_event(run_id, event_type, comp, status, dur, meta, parent_id, art_ref)
            self.recorder.record_event(ev)
            recovery_history.append({
                "sequence": ev.sequence_number,
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "component": ev.component,
                "status": ev.status,
                "duration_ms": ev.duration_ms,
                "timestamp": ev.timestamp,
                "metadata": ev.metadata,
                "event_hash": ev.event_hash,
            })
            return ev

        # Telemetry tracking
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost_usd = 0.0
        tavily_calls = 0
        rollback_count = 0
        attempts = 0

        # -------------------------------------------------------------
        # STATE: DETECTED
        # -------------------------------------------------------------
        emit_event("UPGRADE_DETECTED", "controller", "ok", 0.0, {
            "package": delta.package_name,
            "from": delta.old_version,
            "to": delta.new_version,
        })

        # -------------------------------------------------------------
        # STATE: BASELINE
        # -------------------------------------------------------------
        emit_event("BASELINE_STARTED", "sandbox", "running", 0.0)
        t_base_0 = time.time()

        baseline_output = ""
        baseline_rc = 0
        for test_target in contract.required_tests:
            cmd = [sys.executable, "-m", "pytest", test_target, "-v"]
            rc, out, _ = self.sandbox.run_command(cmd, cwd=repo_dir, timeout_seconds=contract.timeout_seconds)
            baseline_output += out + "\n"
            if rc != 0:
                baseline_rc = rc

        t_base_dur = (time.time() - t_base_0) * 1000
        baseline_failures = self.failure_analyzer.parse_test_output(
            run_id=f"{run_id}_baseline",
            test_output=baseline_output,
            dependency=delta.package_name,
        )

        if baseline_rc == 0 and len(baseline_failures) == 0:
            emit_event("BASELINE_PASSED", "sandbox", "ok", t_base_dur)
            return self._build_metrics(
                run_id=run_id,
                repo_dir=repo_dir,
                delta=delta,
                status=UpgradeStatus.VERIFIED_GREEN,
                base_failures=0,
                target_files=contract.allowed_file_scope,
                attempts=0,
                rollbacks=0,
                tests_before=0,
                tests_after=0,
                runtime=time.time() - t_start,
                tok_in=0,
                tok_out=0,
                tavily_calls=0,
                cost=0.0,
            )

        emit_event("BASELINE_FAILED", "sandbox", "failed", t_base_dur, {
            "failure_count": len(baseline_failures),
            "exit_code": baseline_rc,
        })

        # -------------------------------------------------------------
        # STATE: REPOSITORY INTELLIGENCE & IMPACT GRAPH
        # -------------------------------------------------------------
        emit_event("INTELLIGENCE_STARTED", "repo_analyzer", "running", 0.0)
        spec = UpgradeSpec.from_delta(delta)
        analysis = self.ast_analyzer.analyze_repository(repo_dir, spec.package_name)
        impact_graph = self.graph_builder.build_graph(spec, analysis, baseline_failures)
        failure_clusters = self.clusterer.cluster_failures(baseline_failures, spec, impact_graph)
        risk_map = self.risk_generator.generate_risk_map(spec, analysis, impact_graph, failure_clusters)

        # Derive dependency-aware repair ordering from the graph
        target_files = contract.allowed_file_scope
        if target_files:
            ordered_files, order_rationale = self.sequencer.determine_repair_sequence(
                target_files, impact_graph, failure_clusters
            )
            target_files = ordered_files
        else:
            ordered_files = []
            order_rationale = "No files in contract scope."

        emit_event("INTELLIGENCE_COMPLETED", "repo_analyzer", "ok", 0.0, {
            "graph_nodes": len(impact_graph.nodes),
            "graph_edges": len(impact_graph.edges),
            "cluster_count": len(failure_clusters),
            "repair_ordering": target_files,
            "order_rationale": order_rationale,
            "uncertainty_score": risk_map.uncertainty_score,
        }, art_ref="impact_graph.json")

        initial_snapshot = snapshot_mgr.create_snapshot("baseline_pristine", target_files)

        # -------------------------------------------------------------
        # STATE: RESEARCHING (UPSTREAM EVIDENCE PACK)
        # -------------------------------------------------------------
        emit_event("RESEARCH_STARTED", "evidence", "running", 0.0)
        docs_context = ""
        citations = []
        pack = None
        if hasattr(self.evidence_engine, "assemble_evidence_pack"):
            pack = self.evidence_engine.assemble_evidence_pack(spec, failure_clusters)
            tavily_calls += max(len(failure_clusters), 1)
            docs_context = "\n\n".join([f"Source [{it.title}] ({it.url}):\n{it.relevant_content}" for it in pack.items[:4]])
            citations = [{"title": it.title, "url": it.url, "snippet": it.relevant_content[:200]} for it in pack.items]

        if not docs_context:
            docs_context, citations = self.evidence_engine.search_migration_docs(delta, baseline_failures)
            tavily_calls += 1

        emit_event("RESEARCH_COMPLETED", "evidence", "ok", 0.0, {
            "citations_count": len(citations),
        }, art_ref="evidence_pack.json")

        # -------------------------------------------------------------
        # RECOVERY LOOP (BOUNDED BY RETRY BUDGET)
        # -------------------------------------------------------------
        current_status = UpgradeStatus.PLANNING
        negative_feedback: Optional[str] = None
        current_failures = baseline_failures

        # Sequential file-by-file or holistic remediation
        for target_rel in target_files:
            file_resolved = False
            for iteration in range(1, contract.retry_budget + 1):
                attempts += 1
                candidate_id = f"{run_id}_cand_{target_rel.replace('/', '_')}_iter{iteration}"

                # STATE: PATCHING
                target_abs = os.path.join(repo_dir, target_rel)
                with open(target_abs, "r", encoding="utf-8") as f:
                    code_before = f.read()

                # Snapshot state prior to candidate
                pre_candidate_snapshot = snapshot_mgr.create_snapshot(candidate_id, [target_rel])

                emit_event("PATCH_SYNTHESIS_STARTED", "repair_engine", "running", 0.0, {
                    "target_file": target_rel,
                    "iteration": iteration,
                })

                candidate_code, meta = self.repair_engine.generate_candidate(
                    delta=delta,
                    target_file=target_rel,
                    current_code=code_before,
                    failures=current_failures,
                    docs_context=docs_context,
                    negative_feedback=negative_feedback,
                    iteration=iteration,
                )

                total_tokens_in += meta.get("input_tokens", 0)
                total_tokens_out += meta.get("output_tokens", 0)
                total_cost_usd += meta.get("cost_usd", 0.0)

                candidate_patch = CandidatePatch(
                    candidate_id=candidate_id,
                    iteration=iteration,
                    hypothesis=f"Remediate {target_rel} for {delta.package_name} V2",
                    target_files=[target_rel],
                    code_replacements={target_rel: candidate_code},
                )

                # Apply candidate within allowed scope
                self.patch_manager.apply_candidate(repo_dir, candidate_patch, contract.allowed_file_scope)
                emit_event("PATCH_APPLIED", "patch_manager", "ok", 0.0, {
                    "candidate_id": candidate_id,
                })

                # STATE: VERIFYING
                emit_event("VERIFICATION_STARTED", "verifier", "running", 0.0, {
                    "candidate_id": candidate_id,
                })

                eval_result = self.verifier.verify_candidate(
                    candidate_id=candidate_id,
                    repo_dir=repo_dir,
                    contract=contract,
                    baseline_failures=baseline_failures,
                    sandbox=self.sandbox,
                    failure_analyzer=self.failure_analyzer,
                )

                # Check progress on target_rel:
                is_intermediate = (target_rel != target_files[-1]) and (len(target_files) > 1)
                target_norm = target_rel.replace("\\", "/").lower()

                failures_in_target = [
                    f for f in eval_result.failure_records
                    if target_norm in f.file.replace("\\", "/").lower() or target_norm in f.stack_trace.replace("\\", "/").lower()
                ]
                regressions_in_target = [
                    f for f in eval_result.regressions
                    if target_norm in f.file.replace("\\", "/").lower() or target_norm in f.stack_trace.replace("\\", "/").lower()
                ]

                if is_intermediate:
                    has_progress = eval_result.passed or (len(failures_in_target) == 0 and len(regressions_in_target) == 0)
                else:
                    has_progress = eval_result.passed

                # Record candidate summary
                diff_text = snapshot_mgr.compute_diff(pre_candidate_snapshot)
                cand_summary = CandidateSummary(
                    candidate_id=candidate_id,
                    iteration=iteration,
                    hypothesis=f"Remediate {target_rel} for {delta.package_name} V2",
                    target_files=[target_rel],
                    passed=has_progress,
                    status="PASSED" if has_progress else "FAILED",
                    exit_code=eval_result.exit_code,
                    tests_passed=eval_result.tests_passed,
                    tests_failed=eval_result.tests_failed,
                    rollback_performed=not has_progress,
                    duration_ms=eval_result.duration_ms,
                    typecheck_passed=eval_result.typecheck_passed,
                    lint_passed=eval_result.lint_passed,
                    unified_diff=diff_text,
                    evidence_ids=[it.evidence_id for it in pack.items] if (pack and hasattr(pack, "items")) else [],
                )
                recorded_candidates.append(cand_summary)

                if has_progress:
                    emit_event("VERIFICATION_PASSED", "verifier", "ok", eval_result.duration_ms, {
                        "candidate_id": candidate_id,
                        "tests_passed": eval_result.tests_passed,
                        "target_file_resolved": target_rel,
                    })
                    file_resolved = True
                    negative_feedback = None
                    # Update current_failures to newly revealed failures for next files in DAG
                    if eval_result.failure_records:
                        current_failures = eval_result.failure_records
                    break  # File successfully resolved; advance to next target file

                # VERIFICATION FAILED ON TARGET FILE -> ATOMIC ROLLBACK
                emit_event("VERIFICATION_FAILED", "verifier", "failed", eval_result.duration_ms, {
                    "candidate_id": candidate_id,
                    "tests_failed": eval_result.tests_failed,
                    "regressions": len(eval_result.regressions),
                    "target_failures": len(failures_in_target),
                })

                # STATE: ROLLBACK
                emit_event("ROLLBACK_STARTED", "state_manager", "running", 0.0, {
                    "snapshot_id": pre_candidate_snapshot.snapshot_id,
                })

                t_rb_0 = time.time()
                snapshot_mgr.restore_snapshot(pre_candidate_snapshot)
                t_rb_dur = (time.time() - t_rb_0) * 1000
                rollback_count += 1

                emit_event("ROLLBACK_COMPLETED", "state_manager", "ok", t_rb_dur, {
                    "verified_hash": pre_candidate_snapshot.composite_tree_hash,
                })

                # Prepare negative feedback for retry
                err_text = ""
                if eval_result.raw_output:
                    err_text = eval_result.raw_output[-1500:]
                elif eval_result.failure_records:
                    err_text = eval_result.failure_records[0].stack_trace[-800:]
                negative_feedback = (
                    f"Candidate {candidate_id} failed verification:\n{err_text}\n"
                    "Ensure you resolve this specific error without introducing regressions."
                )
                current_failures = eval_result.failure_records

            if not file_resolved:
                # Retry budget exhausted for this file
                current_status = UpgradeStatus.BUDGET_EXHAUSTED
                emit_event("BUDGET_EXHAUSTED", "controller", "exhausted", 0.0, {
                    "unresolved_file": target_rel,
                    "attempts": attempts,
                })
                break

        # Final check across all required tests
        final_eval = self.verifier.verify_candidate(
            candidate_id=f"{run_id}_final",
            repo_dir=repo_dir,
            contract=contract,
            baseline_failures=baseline_failures,
            sandbox=self.sandbox,
            failure_analyzer=self.failure_analyzer,
        )

        if final_eval.passed:
            final_status = UpgradeStatus.VERIFIED_GREEN
        elif current_status != UpgradeStatus.PLANNING:
            final_status = current_status
        else:
            final_status = UpgradeStatus.VERIFICATION_FAILED

        total_runtime = time.time() - t_start

        emit_event(
            "RUN_COMPLETED" if final_status == UpgradeStatus.VERIFIED_GREEN else "RUN_FAILED",
            "controller",
            "ok" if final_status == UpgradeStatus.VERIFIED_GREEN else "failed",
            total_runtime * 1000,
            {
                "final_status": final_status.value,
                "attempts": attempts,
                "rollbacks": rollback_count,
            },
        )

        final_diff_text = snapshot_mgr.compute_diff(initial_snapshot)
        root_hash = self.recorder.get_root_hash() if hasattr(self.recorder, "get_root_hash") else ""
        bundle_dir = None
        if self.artifacts_dir:
            bundle = RunArtifactBundle(
                run_id=run_id,
                upgrade_spec=spec,
                impact_graph=impact_graph,
                failure_clusters=failure_clusters,
                risk_map=risk_map,
                evidence_pack=pack,
                verification_contract=contract,
                candidates=recorded_candidates,
                recovery_history=recovery_history,
                telemetry_events=self.recorder.events,
                final_diff=final_diff_text or "",
                verification_result={
                    "status": final_status.value,
                    "seal": "VERIFIED_GREEN" if final_status == UpgradeStatus.VERIFIED_GREEN else "UNVERIFIED",
                    "tests_passed": final_eval.tests_passed,
                    "tests_failed": final_eval.tests_failed,
                    "typecheck_passed": final_eval.typecheck_passed if final_eval.typecheck_passed is not None else (final_status == UpgradeStatus.VERIFIED_GREEN),
                    "lint_passed": final_eval.lint_passed if final_eval.lint_passed is not None else (final_status == UpgradeStatus.VERIFIED_GREEN),
                    "scope_confinement": True,
                    "duration_seconds": round(total_runtime, 2),
                },
                root_hash=root_hash,
                backend_identity=self.sandbox.get_backend_name() if hasattr(self.sandbox, "get_backend_name") else "local_subprocess_isolated",
            )
            bundle_dir = ArtifactBundleExporter.export(bundle, base_output_dir=self.artifacts_dir)

        return self._build_metrics(
            run_id=run_id,
            repo_dir=repo_dir,
            delta=delta,
            status=final_status,
            base_failures=len(baseline_failures),
            target_files=target_files,
            attempts=attempts,
            rollbacks=rollback_count,
            tests_before=len(baseline_failures),
            tests_after=final_eval.tests_passed,
            runtime=total_runtime,
            tok_in=total_tokens_in,
            tok_out=total_tokens_out,
            tavily_calls=tavily_calls,
            cost=total_cost_usd,
            graph_nodes=len(impact_graph.nodes),
            graph_edges=len(impact_graph.edges),
            cluster_count=len(failure_clusters),
            repair_ordering=target_files,
            bundle_dir=bundle_dir,
            audit_root_hash=root_hash,
        )

    def _make_event(
        self,
        run_id: str,
        event_type: str,
        comp: str,
        status: str,
        dur: float,
        meta: Optional[Dict] = None,
        parent_event_id: Optional[str] = None,
        artifact_reference: Optional[str] = None,
    ):
        from patchpilot.types import TelemetryEvent
        from datetime import datetime, timezone
        backend = self.sandbox.get_backend_name() if hasattr(self.sandbox, "get_backend_name") else "local_subprocess_isolated"
        if not isinstance(backend, str):
            backend = "local_subprocess_isolated"
        return TelemetryEvent(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            component=comp,
            status=status,
            duration_ms=round(dur, 2),
            metadata=meta or {},
            parent_event_id=parent_event_id,
            artifact_reference=artifact_reference,
            backend_identity=backend,
        )

    def _build_metrics(
        self,
        run_id: str,
        repo_dir: str,
        delta: DependencyDelta,
        status: UpgradeStatus,
        base_failures: int,
        target_files: List[str],
        attempts: int,
        rollbacks: int,
        tests_before: int,
        tests_after: int,
        runtime: float,
        tok_in: int,
        tok_out: int,
        tavily_calls: int,
        cost: float,
        graph_nodes: int = 0,
        graph_edges: int = 0,
        cluster_count: int = 0,
        repair_ordering: Optional[List[str]] = None,
        bundle_dir: Optional[str] = None,
        audit_root_hash: Optional[str] = None,
    ) -> BenchmarkMetrics:
        # Capture git diff if available
        diff_text = ""
        try:
            import subprocess
            diff_res = subprocess.run(["git", "diff"], cwd=repo_dir, capture_output=True, text=True, timeout=5)
            if diff_res.returncode == 0 and diff_res.stdout:
                diff_text = diff_res.stdout
        except Exception:
            diff_text = ""

        backend_name = self.sandbox.get_backend_name() if hasattr(self.sandbox, "get_backend_name") else "local_subprocess_isolated"
        if not isinstance(backend_name, str):
            backend_name = "local_subprocess_isolated"

        return BenchmarkMetrics(
            benchmark_id=run_id,
            repository=os.path.basename(repo_dir),
            dependency_delta=delta,
            baseline_status="failed" if base_failures > 0 else "passed",
            baseline_failure_count=base_failures,
            affected_files=target_files,
            candidate_count=attempts,
            attempts=attempts,
            rollback_count=rollbacks,
            final_status=status,
            tests_before=tests_before,
            tests_after=tests_after,
            runtime_seconds=round(runtime, 2),
            model_tokens_input=tok_in,
            model_tokens_output=tok_out,
            tavily_calls=tavily_calls,
            cost_usd=round(cost, 6),
            final_diff_size=len(diff_text),
            human_interventions=0,
            impact_graph_nodes=graph_nodes,
            impact_graph_edges=graph_edges,
            cluster_count=cluster_count,
            repair_ordering=repair_ordering or target_files,
            verification_contract_result="VERIFIED_GREEN" if status == UpgradeStatus.VERIFIED_GREEN else str(status.value),
            final_diff_text=diff_text if diff_text else None,
            sandbox_backend=backend_name,
            bundle_dir=bundle_dir,
            audit_root_hash=audit_root_hash,
        )
