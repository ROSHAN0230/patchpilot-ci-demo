"""
PatchPilot Core Interfaces and Abstract Contracts.
Establishes clean modular boundaries across the recovery pipeline.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Tuple
from patchpilot.types import (
    DependencyDelta,
    FailureRecord,
    FailureComparison,
    VerificationContract,
    CandidatePatch,
    CandidateEvaluation,
    TelemetryEvent,
    BenchmarkMetrics,
    UpgradeStatus,
)


class UpgradeDetector(ABC):
    """Detects dependency version upgrades from manifests or git diffs."""

    @abstractmethod
    def detect_delta(self, repo_dir: str) -> Optional[DependencyDelta]:
        """Inspect manifests (pyproject.toml, requirements.txt) and return version delta."""
        pass


class RepositoryAnalyzer(ABC):
    """Analyzes AST, import relationships, and file dependencies."""

    @abstractmethod
    def get_affected_files(self, repo_dir: str, delta: DependencyDelta) -> List[str]:
        """Return files that import or use the upgraded package."""
        pass

    @abstractmethod
    def get_import_hierarchy(self, repo_dir: str, files: List[str]) -> List[str]:
        """Return topological ordering of files from base models to leaf callers."""
        pass


class FailureAnalyzer(ABC):
    """Normalizes raw test output into structured FailureRecords and compares across turns."""

    @abstractmethod
    def parse_test_output(self, run_id: str, test_output: str, dependency: str) -> List[FailureRecord]:
        """Extract structured failure records from pytest/test runner output."""
        pass

    @abstractmethod
    def compare_failures(
        self, baseline: List[FailureRecord], current: List[FailureRecord]
    ) -> FailureComparison:
        """Identify resolved failures, persistent failures, and newly introduced regressions."""
        pass


class EvidenceEngine(ABC):
    """Retrieves authoritative upstream migration documentation."""

    @abstractmethod
    def search_migration_docs(
        self, delta: DependencyDelta, failures: List[FailureRecord]
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Search upstream official documentation and return synthesis text + citations."""
        pass


class RepairEngine(ABC):
    """Synthesizes candidate migration patches using language models."""

    @abstractmethod
    def generate_candidate(
        self,
        delta: DependencyDelta,
        target_file: str,
        current_code: str,
        failures: List[FailureRecord],
        docs_context: str,
        negative_feedback: Optional[str] = None,
        iteration: int = 1,
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate candidate code for target_file and return (clean_code, telemetry_meta)."""
        pass


class PatchManager(ABC):
    """Manages applying candidate code with scope restriction and format validation."""

    @abstractmethod
    def apply_candidate(
        self, repo_dir: str, candidate: CandidatePatch, allowed_scope: List[str]
    ) -> bool:
        """Apply patch to target files, verifying all changes remain within allowed scope."""
        pass


class SandboxDriver(ABC):
    """Unified interface for executing commands and verifying repository state in isolation."""

    @abstractmethod
    def run_command(
        self, cmd: List[str], cwd: str, timeout_seconds: int = 30
    ) -> Tuple[int, str, float]:
        """Execute command in sandbox, returning (exit_code, output, duration_ms)."""
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """Return unambiguous backend identifier (e.g. 'local_subprocess_isolated', 'nebius_contree_microvm')."""
        pass


class VerificationEngine(ABC):
    """Evaluates candidate patches against an explicit VerificationContract."""

    @abstractmethod
    def verify_candidate(
        self,
        candidate_id: str,
        repo_dir: str,
        contract: VerificationContract,
        baseline_failures: List[FailureRecord],
        sandbox: SandboxDriver,
        failure_analyzer: FailureAnalyzer,
    ) -> CandidateEvaluation:
        """Run contract commands (pytest, lint, typecheck) and evaluate regression state."""
        pass


class RecoveryController(ABC):
    """Coordinates the autonomous recovery loop with strict state transitions."""

    @abstractmethod
    def execute_recovery(
        self,
        repo_dir: str,
        contract: VerificationContract,
        delta: DependencyDelta,
    ) -> BenchmarkMetrics:
        """Run bounded autonomous repair loop and return comprehensive run metrics."""
        pass


class EvidenceRecorder(ABC):
    """Logs structured telemetry events and compiles final human-reviewable reports."""

    @abstractmethod
    def record_event(self, event: TelemetryEvent) -> None:
        """Append immutable structured event to telemetry storage."""
        pass

    @abstractmethod
    def generate_report(self, metrics: BenchmarkMetrics) -> str:
        """Generate verified Markdown Pull Request evidence report."""
        pass
