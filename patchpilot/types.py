"""
PatchPilot Core Domain Types and Data Models.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class UpgradeStatus(str, Enum):
    IDLE = "idle"
    DETECTED = "detected"
    BASELINE_STARTED = "baseline_started"
    BASELINE_PASSED = "baseline_passed"
    BASELINE_FAILED = "baseline_failed"
    ANALYZING = "analyzing"
    RESEARCHING = "researching"
    PLANNING = "planning"
    PATCHING = "patching"
    VERIFYING = "verifying"
    VERIFICATION_FAILED = "verification_failed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    RETRY_STARTED = "retry_started"
    VERIFIED_GREEN = "verified_green"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ABORTED = "aborted"


@dataclass
class DependencyDelta:
    package_name: str
    old_version: str
    new_version: str
    manifest_path: str
    is_major_bump: bool = False


@dataclass
class UpgradeSpec:
    """Canonical representation of an upgrade recovery case."""
    package_name: str
    old_version: str
    new_version: str
    package_manager: str = "pip"
    manifest_path: str = "pyproject.toml"
    lockfile_path: Optional[str] = None
    is_direct: bool = True
    changed_dependencies: Dict[str, Any] = field(default_factory=dict)
    version_range: str = ""
    upgrade_type: str = "major"
    repo_revision: Optional[str] = None
    trigger_source: str = "cli"

    def to_delta(self) -> DependencyDelta:
        return DependencyDelta(
            package_name=self.package_name,
            old_version=self.old_version,
            new_version=self.new_version,
            manifest_path=self.manifest_path,
            is_major_bump=(self.upgrade_type == "major"),
        )

    @classmethod
    def from_delta(cls, delta: DependencyDelta, trigger_source: str = "cli") -> "UpgradeSpec":
        return cls(
            package_name=delta.package_name,
            old_version=delta.old_version,
            new_version=delta.new_version,
            manifest_path=delta.manifest_path,
            upgrade_type="major" if delta.is_major_bump else "minor",
            trigger_source=trigger_source,
        )


class NodeType(str, Enum):
    PACKAGE = "package"
    MODULE = "module"
    SYMBOL = "symbol"
    TEST = "test"
    FAILURE = "failure"


class EdgeType(str, Enum):
    UPGRADE_TARGET = "upgrade_target"
    IMPORTS = "imports"
    TYPE_CHECKING_IMPORTS = "type_checking_imports"
    DEFINES_SYMBOL = "defines_symbol"
    CALLS_SYMBOL = "calls_symbol"
    TESTS_MODULE = "tests_module"
    FAILS_AT = "fails_at"
    DEPENDS_ON = "depends_on"
    TRANSITIVELY_IMPACTS = "transitively_impacts"


@dataclass
class ImpactNode:
    id: str
    name: str
    node_type: NodeType
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImpactEdge:
    source: str
    target: str
    edge_type: EdgeType
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceItem:
    evidence_id: str
    cluster_id: str
    query: str
    url: str
    title: str
    retrieved_timestamp: str
    relevant_content: str
    source_authority: str = "official_docs"


@dataclass
class EvidencePack:
    spec: UpgradeSpec
    items: List[EvidenceItem] = field(default_factory=list)
    cluster_evidence_map: Dict[str, List[EvidenceItem]] = field(default_factory=dict)


@dataclass
class FailureCluster:
    cluster_id: str
    dependency: str
    failure_category: str
    exception_classes: List[str]
    symbols: List[str]
    affected_files: List[str]
    member_failures: List["FailureRecord"]
    representative_failure: "FailureRecord"
    graph_context: Dict[str, Any] = field(default_factory=dict)
    evidence_references: List[str] = field(default_factory=list)


@dataclass
class MigrationRiskMap:
    spec: UpgradeSpec
    known_breaking_changes: List[str] = field(default_factory=list)
    affected_modules: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    affected_tests: List[str] = field(default_factory=list)
    semantic_risk_regions: List[Dict[str, Any]] = field(default_factory=list)
    uncertainty_score: float = 0.0
    evidence_references: List[str] = field(default_factory=list)



@dataclass
class FailureRecord:
    run_id: str
    test_name: str
    file: str
    line: Optional[int]
    symbol: Optional[str]
    exception_type: str
    message: str
    stack_trace: str
    dependency: str
    category: str
    related_files: List[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        """Deterministic fingerprint for comparing failures across iterations."""
        clean_file = self.file.replace("\\", "/").strip()
        clean_name = self.test_name.strip()
        clean_exc = self.exception_type.strip()
        return f"{clean_file}::{clean_name}::{clean_exc}"


@dataclass
class FailureComparison:
    resolved_failures: List[FailureRecord]
    new_regressions: List[FailureRecord]
    persistent_failures: List[FailureRecord]
    has_regressions: bool
    is_fully_resolved: bool


@dataclass
class VerificationContract:
    required_tests: List[str]
    optional_tests: List[str] = field(default_factory=list)
    lint_command: Optional[str] = None
    typecheck_command: Optional[str] = None
    migration_assertions: Dict[str, Any] = field(default_factory=dict)
    allowed_file_scope: List[str] = field(default_factory=list)
    timeout_seconds: int = 30
    retry_budget: int = 3


@dataclass
class UpstreamCitation:
    url: str
    title: str
    snippet: str
    domain: str
    relevance_score: float = 1.0


@dataclass
class CandidatePatch:
    candidate_id: str
    iteration: int
    hypothesis: str
    target_files: List[str]
    code_replacements: Dict[str, str]  # filepath -> full replacement or patch
    unified_diff: Optional[str] = None
    upstream_citations: List[UpstreamCitation] = field(default_factory=list)


@dataclass
class CandidateEvaluation:
    candidate_id: str
    passed: bool
    exit_code: int
    tests_passed: int
    tests_failed: int
    regressions: List[FailureRecord] = field(default_factory=list)
    failure_records: List[FailureRecord] = field(default_factory=list)
    raw_output: str = ""
    snapshot_hash_pre: str = ""
    snapshot_hash_post: str = ""
    rollback_performed: bool = False
    duration_ms: float = 0.0
    typecheck_passed: Optional[bool] = None
    lint_passed: Optional[bool] = None


@dataclass
class TelemetryEvent:
    run_id: str
    timestamp: str
    event_type: str
    component: str
    status: str
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkMetrics:
    benchmark_id: str
    repository: str
    dependency_delta: DependencyDelta
    baseline_status: str
    baseline_failure_count: int
    affected_files: List[str]
    candidate_count: int
    attempts: int
    rollback_count: int
    final_status: UpgradeStatus
    tests_before: int
    tests_after: int
    lint_result: Optional[str] = None
    typecheck_result: Optional[str] = None
    runtime_seconds: float = 0.0
    model_tokens_input: int = 0
    model_tokens_output: int = 0
    tavily_calls: int = 0
    cost_usd: float = 0.0
    final_diff_size: int = 0
    human_interventions: int = 0
    impact_graph_nodes: int = 0
    impact_graph_edges: int = 0
    cluster_count: int = 0
    repair_ordering: List[str] = field(default_factory=list)
    verification_contract_result: Optional[str] = None
    candidate_hypotheses: List[str] = field(default_factory=list)
    affected_file_precision: Optional[float] = None
    final_diff_text: Optional[str] = None
    sandbox_backend: str = "local_subprocess_isolated"

