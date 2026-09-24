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

    def execute_recovery(
        self,
        repo_dir: str,
        contract: VerificationContract,
        delta: DependencyDelta,
        run_id: str = "run_auto",
    ) -> BenchmarkMetrics:
        t_start = time.time()
        snapshot_mgr = SnapshotManager(repo_dir)

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
        self.recorder.record_event(
            self._make_event(run_id, "UPGRADE_DETECTED", "controller", "ok", 0.0, {
                "package": delta.package_name,
                "from": delta.old_version,
                "to": delta.new_version,
            })
        )

        # -------------------------------------------------------------
        # STATE: BASELINE
        # -------------------------------------------------------------
        self.recorder.record_event(self._make_event(run_id, "BASELINE_STARTED", "sandbox", "running", 0.0))
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
            self.recorder.record_event(self._make_event(run_id, "BASELINE_PASSED", "sandbox", "ok", t_base_dur))
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

        self.recorder.record_event(
            self._make_event(run_id, "BASELINE_FAILED", "sandbox", "failed", t_base_dur, {
                "failure_count": len(baseline_failures),
                "exit_code": baseline_rc,
            })
        )

        # -------------------------------------------------------------
        # STATE: REPOSITORY INTELLIGENCE & IMPACT GRAPH
        # -------------------------------------------------------------
        self.recorder.record_event(self._make_event(run_id, "INTELLIGENCE_STARTED", "repo_analyzer", "running", 0.0))
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

        self.recorder.record_event(
            self._make_event(run_id, "INTELLIGENCE_COMPLETED", "repo_analyzer", "ok", 0.0, {
                "graph_nodes": len(impact_graph.nodes),
                "graph_edges": len(impact_graph.edges),
                "cluster_count": len(failure_clusters),
                "repair_ordering": target_files,
                "order_rationale": order_rationale,
                "uncertainty_score": risk_map.uncertainty_score,
            })
        )

        initial_snapshot = snapshot_mgr.create_snapshot("baseline_pristine", target_files)

        # -------------------------------------------------------------
        # STATE: RESEARCHING (UPSTREAM EVIDENCE PACK)
        # -------------------------------------------------------------
        self.recorder.record_event(self._make_event(run_id, "RESEARCH_STARTED", "evidence", "running", 0.0))
        docs_context = ""
        citations = []
        if hasattr(self.evidence_engine, "assemble_evidence_pack"):
            pack = self.evidence_engine.assemble_evidence_pack(spec, failure_clusters)
            tavily_calls += max(len(failure_clusters), 1)
            docs_context = "\n\n".join([f"Source [{it.title}] ({it.url}):\n{it.relevant_content}" for it in pack.items[:4]])
            citations = [{"title": it.title, "url": it.url, "snippet": it.relevant_content[:200]} for it in pack.items]

        if not docs_context:
            docs_context, citations = self.evidence_engine.search_migration_docs(delta, baseline_failures)
            tavily_calls += 1

        self.recorder.record_event(
            self._make_event(run_id, "RESEARCH_COMPLETED", "evidence", "ok", 0.0, {
                "citations_count": len(citations),
            })
        )

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

                self.recorder.record_event(
                    self._make_event(run_id, "PATCH_SYNTHESIS_STARTED", "repair_engine", "running", 0.0, {
                        "target_file": target_rel,
                        "iteration": iteration,
                    })
                )

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
                self.recorder.record_event(
                    self._make_event(run_id, "PATCH_APPLIED", "patch_manager", "ok", 0.0, {
                        "candidate_id": candidate_id,
                    })
                )

                # STATE: VERIFYING
                self.recorder.record_event(
                    self._make_event(run_id, "VERIFICATION_STARTED", "verifier", "running", 0.0, {
                        "candidate_id": candidate_id,
                    })
                )

                eval_result = self.verifier.verify_candidate(
                    candidate_id=candidate_id,
                    repo_dir=repo_dir,
                    contract=contract,
                    baseline_failures=baseline_failures,
                    sandbox=self.sandbox,
                    failure_analyzer=self.failure_analyzer,
                )

                # Check progress on target_rel:
                # Intermediate files in a multi-file DAG are considered resolved if no errors point to them.
                # The final file (or single file) must pass all required tests.
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

                if has_progress:
                    self.recorder.record_event(
                        self._make_event(run_id, "VERIFICATION_PASSED", "verifier", "ok", eval_result.duration_ms, {
                            "candidate_id": candidate_id,
                            "tests_passed": eval_result.tests_passed,
                            "target_file_resolved": target_rel,
                        })
                    )
                    file_resolved = True
                    negative_feedback = None
                    # Update current_failures to newly revealed failures for next files in DAG
                    if eval_result.failure_records:
                        current_failures = eval_result.failure_records
                    break  # File successfully resolved; advance to next target file

                # VERIFICATION FAILED ON TARGET FILE -> ATOMIC ROLLBACK
                self.recorder.record_event(
                    self._make_event(run_id, "VERIFICATION_FAILED", "verifier", "failed", eval_result.duration_ms, {
                        "candidate_id": candidate_id,
                        "tests_failed": eval_result.tests_failed,
                        "regressions": len(eval_result.regressions),
                        "target_failures": len(failures_in_target),
                    })
                )

                # STATE: ROLLBACK
                self.recorder.record_event(
                    self._make_event(run_id, "ROLLBACK_STARTED", "state_manager", "running", 0.0, {
                        "snapshot_id": pre_candidate_snapshot.snapshot_id,
                    })
                )

                t_rb_0 = time.time()
                snapshot_mgr.restore_snapshot(pre_candidate_snapshot)
                t_rb_dur = (time.time() - t_rb_0) * 1000
                rollback_count += 1

                self.recorder.record_event(
                    self._make_event(run_id, "ROLLBACK_COMPLETED", "state_manager", "ok", t_rb_dur, {
                        "verified_hash": pre_candidate_snapshot.composite_tree_hash,
                    })
                )

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
                self.recorder.record_event(
                    self._make_event(run_id, "BUDGET_EXHAUSTED", "controller", "exhausted", 0.0, {
                        "unresolved_file": target_rel,
                        "attempts": attempts,
                    })
                )
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
        )

    def _make_event(self, run_id: str, event_type: str, comp: str, status: str, dur: float, meta: Optional[Dict] = None):
        from patchpilot.types import TelemetryEvent
        from datetime import datetime, timezone
        return TelemetryEvent(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            component=comp,
            status=status,
            duration_ms=round(dur, 2),
            metadata=meta or {},
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
    ) -> BenchmarkMetrics:
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
            final_diff_size=0,
            human_interventions=0,
            impact_graph_nodes=graph_nodes,
            impact_graph_edges=graph_edges,
            cluster_count=cluster_count,
            repair_ordering=repair_ordering or target_files,
            verification_contract_result="VERIFIED_GREEN" if status == UpgradeStatus.VERIFIED_GREEN else str(status.value),
        )
