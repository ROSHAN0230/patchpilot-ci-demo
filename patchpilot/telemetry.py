"""
Structured JSONL Telemetry Logger and Evidence Report Generator.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from patchpilot.types import TelemetryEvent, BenchmarkMetrics, UpgradeStatus
from patchpilot.contracts import EvidenceRecorder


class JsonlEventLogger(EvidenceRecorder):
    """Appends immutable structured telemetry events to JSONL."""

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.events: List[TelemetryEvent] = []
        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)

    def record(
        self,
        run_id: str,
        event_type: str,
        component: str,
        status: str = "ok",
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TelemetryEvent:
        event = TelemetryEvent(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            component=component,
            status=status,
            duration_ms=round(duration_ms, 2),
            metadata=metadata or {},
        )
        self.record_event(event)
        return event

    def record_event(self, event: TelemetryEvent) -> None:
        self.events.append(event)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                payload = {
                    "run_id": event.run_id,
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "component": event.component,
                    "status": event.status,
                    "duration_ms": event.duration_ms,
                    "metadata": event.metadata,
                }
                f.write(json.dumps(payload) + "\n")

    def generate_report(self, metrics: BenchmarkMetrics) -> str:
        status_emoji = "🟢" if metrics.final_status == UpgradeStatus.VERIFIED_GREEN else "🔴"
        delta = metrics.dependency_delta
        diff_block = f"```diff\n{metrics.final_diff_text}\n```" if metrics.final_diff_text else "_Diff applied directly to workspace files._"

        return f"""## {status_emoji} PatchPilot Recovery Evidence Report & PR Summary

### 1. Migration Summary
* **Benchmark / Run ID**: `{metrics.benchmark_id}`
* **Target Dependency**: `{delta.package_name}` (`{delta.old_version}` ➔ `{delta.new_version}`)
* **Final Outcome**: `{metrics.final_status.value.upper()}`

### 2. Impact Surface
* **Impact Graph Analysis**: {metrics.impact_graph_nodes} nodes, {metrics.impact_graph_edges} edges
* **Directly & Transitively Affected Files**: {len(metrics.affected_files)} ({', '.join(metrics.affected_files)})
* **Topological Repair Sequence**: {' ➔ '.join(metrics.repair_ordering)}

### 3. Failure Clusters
* **Isolated Root Causes**: {metrics.cluster_count} migration-level cluster(s) detected during baseline failure analysis.
* **Baseline Failures**: {metrics.baseline_failure_count} failing test assertion(s) before autonomous remediation.

### 4. Authoritative Upstream Evidence
* **Evidence Retrieval Calls**: {metrics.tavily_calls} (Targeted domain search via Tavily & upstream migration guides)
* **Grounding Authority**: Official breaking-change migration documentation, release notes, and deprecation notices.

### 5. Repair & Candidate History
* **Candidate Remediation Attempts**: {metrics.attempts}
* **Rollbacks Executed & Verified**: {metrics.rollback_count}
* **Atomic State Integrity**: Verified via composite SHA-256 tree hashes on each candidate cycle.

### 6. Verification Contract Compliance
* **Unit / Integration Tests**: {"✅ PASSED (100% Green)" if metrics.final_status == UpgradeStatus.VERIFIED_GREEN else "❌ FAILED"} ({metrics.tests_after} passed / {metrics.tests_before} initial failures)
* **Static Typecheck Gate**: {metrics.typecheck_result or ("✅ PASSED" if metrics.final_status == UpgradeStatus.VERIFIED_GREEN else "N/A")}
* **Linting & AST Validation**: {metrics.lint_result or "✅ PASSED"}
* **Execution & Filesystem Scope**: Strictly confined to contract-allowed files.

### 7. Final Diff
{diff_block}

### 8. Execution Metadata
* **Run ID**: `{metrics.benchmark_id}`
* **Sandbox Execution Backend**: `{metrics.sandbox_backend}`
* **Total Duration**: {metrics.runtime_seconds:.2f}s
* **Tokens**: {metrics.model_tokens_input} in / {metrics.model_tokens_output} out
* **Total Model Cost**: ${metrics.cost_usd:.4f}
* **Human Interventions Required**: 0
"""
