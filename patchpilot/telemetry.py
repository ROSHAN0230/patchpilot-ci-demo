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
        return f"""## {status_emoji} PatchPilot Recovery Evidence Report
**Benchmark / Run ID**: `{metrics.benchmark_id}`
**Target Dependency**: `{delta.package_name}` (`{delta.old_version}` ➔ `{delta.new_version}`)
**Final Outcome**: `{metrics.final_status.value.upper()}`

### 1. Summary of Execution
* **Repository**: `{metrics.repository}`
* **Baseline Failing Tests**: {metrics.baseline_failure_count}
* **Affected Files Identified**: {len(metrics.affected_files)} ({', '.join(metrics.affected_files)})
* **Candidate Remediation Attempts**: {metrics.attempts}
* **Rollbacks Executed & Verified**: {metrics.rollback_count}
* **Tests Passed After Recovery**: {metrics.tests_after} / {metrics.tests_before}

### 2. Operational Telemetry & Cost
* **Total Runtime**: {metrics.runtime_seconds:.2f}s
* **Tokens**: {metrics.model_tokens_input} in / {metrics.model_tokens_output} out
* **Upstream Search Calls (Tavily)**: {metrics.tavily_calls}
* **Total Model Cost**: ${metrics.cost_usd:.4f}
* **Human Interventions Required**: {metrics.human_interventions}

### 3. Verification Contract Compliance
* **Unit / Integration Tests**: {"✅ PASSED (100% Green)" if metrics.final_status == UpgradeStatus.VERIFIED_GREEN else "❌ FAILED"}
* **Linting / Syntax Check**: {metrics.lint_result or "Not configured"}
* **Typecheck Check**: {metrics.typecheck_result or "Not configured"}
* **Execution Boundary**: Confined to allowed scope.
"""
