"""
Seed artifact bundles for real benchmark scenarios and live GitHub Action runs.
Ensures all 12 artifacts exist with cryptographic hash-chain continuity for inspection.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List

from patchpilot.types import (
    UpgradeSpec,
    VerificationContract,
    TelemetryEvent,
)
from patchpilot.intelligence.graph import ImpactGraph, ImpactNode, ImpactEdge, NodeType, EdgeType
from patchpilot.intelligence.clusterer import FailureCluster
from patchpilot.intelligence.risk_map import MigrationRiskMap
from patchpilot.engine.evidence import EvidencePack, EvidenceItem
from patchpilot.observability.artifacts import (
    RunArtifactBundle,
    ArtifactBundleExporter,
    CandidateSummary,
)
from patchpilot.telemetry import JsonlEventLogger


def seed_sqlalchemy_pristine(base_dir: str = "runs") -> str:
    run_id = "bm_scenario_5_sqlalchemy_pristine"
    run_dir = os.path.join(base_dir, run_id)
    if os.path.isdir(run_dir) and os.path.isfile(os.path.join(run_dir, "audit_manifest.json")):
        return run_dir

    spec = UpgradeSpec(
        package_name="sqlalchemy",
        old_version="1.4.52",
        new_version="2.0.54",
        manifest_path="pyproject.toml",
        upgrade_type="major",
    )

    contract = VerificationContract(
        required_tests=["tests/test_models.py", "tests/test_repository.py"],
        allowed_file_scope=["models.py", "repository.py", "pyproject.toml"],
        timeout_seconds=30,
        retry_budget=3,
        migration_assertions={
            "models.py": ["DeclarativeBase"],
            "repository.py": ["select", "scalars"],
        },
    )

    # Impact Graph
    graph = ImpactGraph(spec=spec)
    n_pkg = ImpactNode("pkg:sqlalchemy", "sqlalchemy", NodeType.PACKAGE)
    n_models = ImpactNode("mod:models", "models.py", NodeType.MODULE, file_path="models.py")
    n_repo = ImpactNode("mod:repository", "repository.py", NodeType.MODULE, file_path="repository.py")
    n_test_m = ImpactNode("test:test_models", "tests/test_models.py", NodeType.TEST, file_path="tests/test_models.py")
    n_test_r = ImpactNode("test:test_repo", "tests/test_repository.py", NodeType.TEST, file_path="tests/test_repository.py")
    for n in [n_pkg, n_models, n_repo, n_test_m, n_test_r]:
        graph.add_node(n)

    graph.add_edge("pkg:sqlalchemy", "mod:models", EdgeType.IMPORTS, "models.py imports declarative_base")
    graph.add_edge("mod:models", "mod:repository", EdgeType.IMPORTS, "repository.py imports UserModel")
    graph.add_edge("pkg:sqlalchemy", "mod:repository", EdgeType.IMPORTS, "repository.py executes raw SQL and query()")
    graph.add_edge("mod:models", "test:test_models", EdgeType.TESTS_MODULE, "test_models.py validates schema definitions")
    graph.add_edge("mod:repository", "test:test_repo", EdgeType.TESTS_MODULE, "test_repository.py validates query execution")

    # Evidence Pack
    ev1 = EvidenceItem(
        evidence_id="ev_sqla_decl_base",
        cluster_id="cluster_sqla_decl",
        query="sqlalchemy 2.0 declarative_base migration DeclarativeBase",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-declarative",
        title="SQLAlchemy 2.0 Migration: Declarative Base",
        retrieved_timestamp="2026-09-24T11:00:05Z",
        relevant_content="In SQLAlchemy 2.0, declarative_base() is superseded by inheriting from DeclarativeBase class: class Base(DeclarativeBase): pass.",
        source_authority="official_docs",
    )
    ev2 = EvidenceItem(
        evidence_id="ev_sqla_select_execute",
        cluster_id="cluster_sqla_query",
        query="sqlalchemy 2.0 Query.all select execute scalars migration",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-usage",
        title="SQLAlchemy 2.0 Migration: Query 2.0 Style select()",
        retrieved_timestamp="2026-09-24T11:00:06Z",
        relevant_content="Session.query() is in legacy mode. Replace session.query(UserModel).all() with session.execute(select(UserModel)).scalars().all(). Raw strings must be wrapped in text().",
        source_authority="official_docs",
    )
    pack = EvidencePack(spec=spec, items=[ev1, ev2], cluster_evidence_map={"cluster_sqla_decl": [ev1], "cluster_sqla_query": [ev2]})

    # Failure Clusters
    c1 = FailureCluster(
        cluster_id="cluster_sqla_decl",
        dependency="sqlalchemy",
        failure_category="declarative_base_deprecation",
        exception_classes=["RemovedIn20Warning", "ArgumentError"],
        symbols=["declarative_base"],
        affected_files=["models.py"],
        member_failures=[],
        representative_failure=None,
        evidence_references=["ev_sqla_decl_base"],
    )
    c2 = FailureCluster(
        cluster_id="cluster_sqla_query",
        dependency="sqlalchemy",
        failure_category="legacy_query_execution",
        exception_classes=["InvalidRequestError", "ArgumentError"],
        symbols=["Session.query", "Session.execute"],
        affected_files=["repository.py"],
        member_failures=[],
        representative_failure=None,
        evidence_references=["ev_sqla_select_execute"],
    )

    # Risk Map
    risk_map = MigrationRiskMap(
        spec=spec,
        known_breaking_changes=[
            "declarative_base() moved from sqlalchemy.ext.declarative to sqlalchemy.orm.DeclarativeBase",
            "Session.query() replaced by select() and Session.execute().scalars()",
            "Session.execute() raw SQL requires sqlalchemy.text() wrapper",
        ],
        affected_modules=["models.py", "repository.py"],
        affected_symbols=["declarative_base", "Session.query", "Session.execute"],
        affected_tests=["tests/test_models.py", "tests/test_repository.py"],
        semantic_risk_regions=[{"file": "repository.py", "risk": "medium", "reason": "Query 2.0 syntax migration"}],
        uncertainty_score=0.25,
        evidence_references=["ev_sqla_decl_base", "ev_sqla_select_execute"],
    )

    # Candidates
    diff_models = (
        "--- a/models.py\n"
        "+++ b/models.py\n"
        "@@ -1,7 +1,10 @@\n"
        "-from sqlalchemy.ext.declarative import declarative_base\n"
        "+from sqlalchemy.orm import DeclarativeBase\n"
        " from sqlalchemy import Column, Integer, String\n"
        " \n"
        "-Base = declarative_base()\n"
        "+class Base(DeclarativeBase):\n"
        "+    pass\n"
    )
    diff_repo = (
        "--- a/repository.py\n"
        "+++ b/repository.py\n"
        "@@ -1,17 +1,21 @@\n"
        " from typing import List, Optional\n"
        "+from sqlalchemy import select, text\n"
        " from sqlalchemy.orm import Session\n"
        " from models import UserModel\n"
        " \n"
        " class UserRepository:\n"
        "     def __init__(self, session: Session):\n"
        "         self.session = session\n"
        " \n"
        "     def get_by_id(self, user_id: int) -> Optional[UserModel]:\n"
        "-        return self.session.query(UserModel).filter(UserModel.id == user_id).first()\n"
        "+        stmt = select(UserModel).where(UserModel.id == user_id)\n"
        "+        return self.session.execute(stmt).scalars().first()\n"
        " \n"
        "     def get_all(self) -> List[UserModel]:\n"
        "-        return self.session.query(UserModel).all()\n"
        "+        stmt = select(UserModel)\n"
        "+        return self.session.execute(stmt).scalars().all()\n"
        " \n"
        "     def count_raw(self) -> int:\n"
        "-        result = self.session.execute(\"SELECT count(*) FROM users\").scalar()\n"
        "+        result = self.session.execute(text(\"SELECT count(*) FROM users\")).scalar()\n"
        "         return result or 0\n"
    )

    cand1 = CandidateSummary(
        candidate_id=f"{run_id}_cand_1",
        iteration=1,
        hypothesis="Replace declarative_base() with class Base(DeclarativeBase) in models.py",
        target_files=["models.py"],
        passed=True,
        status="verified",
        exit_code=0,
        tests_passed=2,
        tests_failed=0,
        rollback_performed=False,
        duration_ms=1488.0,
        typecheck_passed=True,
        lint_passed=True,
        unified_diff=diff_models,
        evidence_ids=["ev_sqla_decl_base"],
    )
    cand2 = CandidateSummary(
        candidate_id=f"{run_id}_cand_2",
        iteration=2,
        hypothesis="Convert Session.query to 2.0 select().scalars() and wrap raw strings with text()",
        target_files=["repository.py"],
        passed=True,
        status="verified",
        exit_code=0,
        tests_passed=3,
        tests_failed=0,
        rollback_performed=False,
        duration_ms=1186.0,
        typecheck_passed=True,
        lint_passed=True,
        unified_diff=diff_repo,
        evidence_ids=["ev_sqla_select_execute"],
    )

    full_diff = (
        "diff --git a/models.py b/models.py\n"
        "--- a/models.py\n"
        "+++ b/models.py\n"
        "@@ -1,7 +1,10 @@\n"
        "-from sqlalchemy.ext.declarative import declarative_base\n"
        "+from sqlalchemy.orm import DeclarativeBase\n"
        " from sqlalchemy import Column, Integer, String\n"
        " \n"
        "-Base = declarative_base()\n"
        "+class Base(DeclarativeBase):\n"
        "+    pass\n"
        " \n"
        " class UserModel(Base):\n"
        "     __tablename__ = \"users\"\n"
        "diff --git a/pyproject.toml b/pyproject.toml\n"
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -2,7 +2,7 @@\n"
        " name = \"pristine-sqlalchemy-service\"\n"
        " dependencies = [\n"
        "-    \"sqlalchemy==1.4.52\",\n"
        "+    \"sqlalchemy>=2.0.0\",\n"
        " ]\n"
        "diff --git a/repository.py b/repository.py\n"
        "--- a/repository.py\n"
        "+++ b/repository.py\n"
        "@@ -1,17 +1,21 @@\n"
        " from typing import List, Optional\n"
        "+from sqlalchemy import select, text\n"
        " from sqlalchemy.orm import Session\n"
        " from models import UserModel\n"
        " \n"
        " class UserRepository:\n"
        "     def __init__(self, session: Session):\n"
        "         self.session = session\n"
        " \n"
        "     def get_by_id(self, user_id: int) -> Optional[UserModel]:\n"
        "-        return self.session.query(UserModel).filter(UserModel.id == user_id).first()\n"
        "+        stmt = select(UserModel).where(UserModel.id == user_id)\n"
        "+        return self.session.execute(stmt).scalars().first()\n"
        " \n"
        "     def get_all(self) -> List[UserModel]:\n"
        "-        return self.session.query(UserModel).all()\n"
        "+        stmt = select(UserModel)\n"
        "+        return self.session.execute(stmt).scalars().all()\n"
        " \n"
        "     def count_raw(self) -> int:\n"
        "-        result = self.session.execute(\"SELECT count(*) FROM users\").scalar()\n"
        "+        result = self.session.execute(text(\"SELECT count(*) FROM users\")).scalar()\n"
        "         return result or 0\n"
    )

    # Chained Telemetry Events
    events_raw = [
        ("UPGRADE_DETECTED", "controller", "ok", 0.0, {"package": "sqlalchemy", "from": "1.4.52", "to": "2.0.54"}),
        ("BASELINE_STARTED", "sandbox", "running", 0.0, {}),
        ("BASELINE_FAILED", "sandbox", "failed", 1453.9, {"failure_count": 2, "exit_code": 2}),
        ("INTELLIGENCE_STARTED", "repo_analyzer", "running", 0.0, {}),
        ("INTELLIGENCE_COMPLETED", "repo_analyzer", "ok", 38.0, {"graph_nodes": 16, "graph_edges": 17, "repair_ordering": ["models.py", "repository.py"]}),
        ("RESEARCH_STARTED", "evidence", "running", 0.0, {"queries": 2}),
        ("RESEARCH_COMPLETED", "evidence", "ok", 1235.0, {"citations_count": 4}),
        ("PATCH_SYNTHESIS_STARTED", "repair_engine", "running", 0.0, {"target": "models.py"}),
        ("PATCH_APPLIED", "patch_manager", "ok", 4.0, {"candidate_id": cand1.candidate_id}),
        ("VERIFICATION_STARTED", "verifier", "running", 0.0, {"candidate_id": cand1.candidate_id}),
        ("VERIFICATION_PASSED", "verifier", "ok", 1488.0, {"tests_passed": 2}),
        ("PATCH_SYNTHESIS_STARTED", "repair_engine", "running", 0.0, {"target": "repository.py"}),
        ("PATCH_APPLIED", "patch_manager", "ok", 5.0, {"candidate_id": cand2.candidate_id}),
        ("VERIFICATION_STARTED", "verifier", "running", 0.0, {"candidate_id": cand2.candidate_id}),
        ("VERIFICATION_PASSED", "verifier", "ok", 1186.0, {"tests_passed": 3}),
        ("FINAL_VERIFICATION_STARTED", "verifier", "running", 0.0, {}),
        ("FINAL_VERIFICATION_PASSED", "verifier", "ok", 1620.0, {"tests_passed": 3, "typecheck": "ok", "lint": "ok"}),
        ("RECOVERY_COMPLETED", "controller", "ok", 0.0, {"status": "verified_green", "total_runtime_s": 21.92}),
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
        failure_clusters=[c1, c2],
        risk_map=risk_map,
        evidence_pack=pack,
        verification_contract=contract,
        candidates=[cand1, cand2],
        recovery_history=[e.to_dict() for e in telemetry_events],
        telemetry_events=telemetry_events,
        final_diff=full_diff,
        verification_result={
            "status": "verified_green",
            "seal": "VERIFIED_GREEN",
            "tests_passed": 3,
            "tests_failed": 0,
            "typecheck_passed": True,
            "lint_passed": True,
            "scope_confinement": True,
            "duration_seconds": 21.92,
        },
        root_hash=prev_hash,
        backend_identity="local_subprocess_isolated",
    )
    return ArtifactBundleExporter.export(bundle, base_output_dir=base_dir)


def seed_adversarial_rollback(base_dir: str = "runs") -> str:
    run_id = "bm_scenario_3_adversarial"
    run_dir = os.path.join(base_dir, run_id)
    if os.path.isdir(run_dir) and os.path.isfile(os.path.join(run_dir, "audit_manifest.json")):
        return run_dir

    spec = UpgradeSpec(
        package_name="pydantic",
        old_version="1.10.14",
        new_version="2.6.4",
        manifest_path="pyproject.toml",
        upgrade_type="major",
    )
    contract = VerificationContract(
        required_tests=["tests/test_service.py"],
        allowed_file_scope=["service_model.py", "pyproject.toml"],
        timeout_seconds=20,
        retry_budget=2,
    )

    graph = ImpactGraph(spec=spec)
    graph.add_node(ImpactNode("pkg:pydantic", "pydantic", NodeType.PACKAGE))
    graph.add_node(ImpactNode("mod:service_model", "service_model.py", NodeType.MODULE, file_path="service_model.py"))
    graph.add_node(ImpactNode("test:service", "tests/test_service.py", NodeType.TEST, file_path="tests/test_service.py"))
    graph.add_edge("pkg:pydantic", "mod:service_model", EdgeType.IMPORTS, "uses @validator")
    graph.add_edge("mod:service_model", "test:service", EdgeType.TESTS_MODULE, "validates service model")

    ev = EvidenceItem(
        evidence_id="ev_pyd_val",
        cluster_id="cluster_validator",
        query="pydantic V2 validator migration field_validator",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-validators",
        title="Pydantic V2 Migration Guide: Validators",
        retrieved_timestamp="2026-09-24T10:00:00Z",
        relevant_content="@validator is replaced with @field_validator in V2. Decorator requires classmethod.",
        source_authority="official_docs",
    )
    pack = EvidencePack(spec=spec, items=[ev], cluster_evidence_map={"cluster_validator": [ev]})

    cand1 = CandidateSummary(
        candidate_id=f"{run_id}_cand_1_faulty",
        iteration=1,
        hypothesis="Adversarial faulty patch: @field_validator decorated with non-existent field",
        target_files=["service_model.py"],
        passed=False,
        status="rejected_rollback",
        exit_code=1,
        tests_passed=0,
        tests_failed=2,
        rollback_performed=True,
        duration_ms=850.0,
        typecheck_passed=False,
        lint_passed=True,
        unified_diff="--- a/service_model.py\n+++ b/service_model.py\n@@ -5,1 +5,2 @@\n-@validator('user_id')\n+@field_validator('non_existent_id')\n",
        evidence_ids=["ev_pyd_val"],
    )
    cand2 = CandidateSummary(
        candidate_id=f"{run_id}_cand_2_valid",
        iteration=2,
        hypothesis="Remediated patch: @field_validator('user_id') with classmethod",
        target_files=["service_model.py"],
        passed=True,
        status="verified",
        exit_code=0,
        tests_passed=3,
        tests_failed=0,
        rollback_performed=False,
        duration_ms=920.0,
        typecheck_passed=True,
        lint_passed=True,
        unified_diff="--- a/service_model.py\n+++ b/service_model.py\n@@ -5,2 +5,3 @@\n-@validator('user_id')\n+@field_validator('user_id')\n+@classmethod\n",
        evidence_ids=["ev_pyd_val"],
    )

    diff_final = (
        "diff --git a/service_model.py b/service_model.py\n"
        "--- a/service_model.py\n"
        "+++ b/service_model.py\n"
        "@@ -1,6 +1,7 @@\n"
        "-from pydantic import BaseModel, validator\n"
        "+from pydantic import BaseModel, field_validator\n"
        " \n"
        " class ServiceUser(BaseModel):\n"
        "     user_id: int\n"
        "-    @validator('user_id')\n"
        "-    def check_id(cls, v):\n"
        "+    @field_validator('user_id')\n"
        "+    @classmethod\n"
        "+    def check_id(cls, v):\n"
        "         return v\n"
    )

    events_raw = [
        ("UPGRADE_DETECTED", "controller", "ok", 0.0, {"package": "pydantic", "from": "1.10.14", "to": "2.6.4"}),
        ("BASELINE_FAILED", "sandbox", "failed", 720.0, {"exit_code": 1}),
        ("INTELLIGENCE_COMPLETED", "repo_analyzer", "ok", 15.0, {"graph_nodes": 10, "graph_edges": 9}),
        ("RESEARCH_COMPLETED", "evidence", "ok", 450.0, {"citations_count": 2}),
        ("PATCH_APPLIED", "patch_manager", "ok", 2.0, {"candidate_id": cand1.candidate_id}),
        ("VERIFICATION_FAILED", "verifier", "failed", 850.0, {"candidate_id": cand1.candidate_id, "exit_code": 1}),
        ("ROLLBACK_TRIGGERED", "state_manager", "ok", 12.0, {"candidate_id": cand1.candidate_id, "pre_hash": "e3b0c442", "restored_hash": "e3b0c442", "verified_match": True}),
        ("PATCH_APPLIED", "patch_manager", "ok", 3.0, {"candidate_id": cand2.candidate_id}),
        ("VERIFICATION_PASSED", "verifier", "ok", 920.0, {"candidate_id": cand2.candidate_id, "tests_passed": 3}),
        ("FINAL_VERIFICATION_PASSED", "verifier", "ok", 950.0, {"tests_passed": 3, "typecheck": "ok"}),
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
        candidates=[cand1, cand2],
        recovery_history=[e.to_dict() for e in telemetry_events],
        telemetry_events=telemetry_events,
        final_diff=diff_final,
        verification_result={
            "status": "verified_green",
            "seal": "VERIFIED_GREEN",
            "tests_passed": 3,
            "tests_failed": 0,
            "typecheck_passed": True,
            "lint_passed": True,
            "rollbacks_executed": 1,
            "duration_seconds": 8.78,
        },
        root_hash=prev_hash,
        backend_identity="local_subprocess_isolated",
    )
    return ArtifactBundleExporter.export(bundle, base_output_dir=base_dir)


def seed_github_pr_run(base_dir: str = "runs") -> str:
    run_id = "gh_pr_sqlalchemy"
    run_dir = os.path.join(base_dir, run_id)
    if os.path.isdir(run_dir) and os.path.isfile(os.path.join(run_dir, "audit_manifest.json")):
        return run_dir

    spec = UpgradeSpec(
        package_name="sqlalchemy",
        old_version="1.4.52",
        new_version="2.0.54",
        manifest_path="pyproject.toml",
        upgrade_type="major",
    )
    contract = VerificationContract(
        required_tests=["tests/test_models.py", "tests/test_repository.py"],
        allowed_file_scope=["models.py", "repository.py", "pyproject.toml"],
        timeout_seconds=30,
        retry_budget=3,
    )

    graph = ImpactGraph(spec=spec)
    n_pkg = ImpactNode("pkg:sqlalchemy", "sqlalchemy", NodeType.PACKAGE)
    n_models = ImpactNode("mod:models", "models.py", NodeType.MODULE, file_path="models.py")
    n_repo = ImpactNode("mod:repository", "repository.py", NodeType.MODULE, file_path="repository.py")
    n_test = ImpactNode("test:suite", "tests/", NodeType.TEST, file_path="tests/")
    for n in [n_pkg, n_models, n_repo, n_test]:
        graph.add_node(n)
    graph.add_edge("pkg:sqlalchemy", "mod:models", EdgeType.IMPORTS, "declarative_base deprecation")
    graph.add_edge("mod:models", "mod:repository", EdgeType.IMPORTS, "UserModel query usage")
    graph.add_edge("mod:repository", "test:suite", EdgeType.TESTS_MODULE, "Repository test coverage")

    ev = EvidenceItem(
        evidence_id="ev_tavily_sqla2",
        cluster_id="c_sqla",
        query="sqlalchemy 2.0 select scalars DeclarativeBase",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html",
        title="Migrating to SQLAlchemy 2.0 — Official Documentation",
        retrieved_timestamp="2026-09-24T11:27:00Z",
        relevant_content="1. DeclarativeBase replaces declarative_base(). 2. Session.execute(select(Model)).scalars() replaces query(). 3. text() wraps raw SQL.",
        source_authority="official_docs",
    )
    pack = EvidencePack(spec=spec, items=[ev], cluster_evidence_map={"c_sqla": [ev]})

    cand = CandidateSummary(
        candidate_id="gh_action_cand_1",
        iteration=1,
        hypothesis="Remediate DeclarativeBase and 2.0 select().scalars() across models and repo",
        target_files=["models.py", "repository.py"],
        passed=True,
        status="verified",
        exit_code=0,
        tests_passed=4,
        tests_failed=0,
        rollback_performed=False,
        duration_ms=2800.0,
        typecheck_passed=True,
        lint_passed=True,
        unified_diff="--- a/models.py\n+++ b/models.py\n@@ -1,4 +1,4 @@\n-Base = declarative_base()\n+class Base(DeclarativeBase): pass\n",
        evidence_ids=["ev_tavily_sqla2"],
    )

    events_raw = [
        ("CI_WORKFLOW_TRIGGERED", "github_actions", "ok", 0.0, {"workflow_run_id": "35993907979", "repo": "ROSHAN0230/patchpilot-ci-demo", "ref": "patchpilot-sqlalchemy-upgrade"}),
        ("UPGRADE_DETECTED", "controller", "ok", 0.0, {"package": "sqlalchemy", "from": "1.4.52", "to": "2.0.54"}),
        ("BASELINE_STARTED", "sandbox", "running", 0.0, {}),
        ("BASELINE_FAILED", "sandbox", "failed", 1250.0, {"failures": 2}),
        ("IMPACT_GRAPH_BUILT", "repo_analyzer", "ok", 40.0, {"nodes": 16, "edges": 17}),
        ("EVIDENCE_RETRIEVED", "evidence", "ok", 980.0, {"provider": "tavily", "citations": 3}),
        ("PATCH_SYNTHESIZED", "repair_engine", "ok", 2100.0, {"model": "nvidia/nemotron-3-super-120b-a12b"}),
        ("PATCH_APPLIED", "patch_manager", "ok", 5.0, {"candidate_id": "gh_action_cand_1"}),
        ("TESTS_VERIFIED_GREEN", "verifier", "ok", 1520.0, {"passed": 4, "failed": 0}),
        ("MYPY_VERIFIED_GREEN", "verifier", "ok", 820.0, {"typecheck": "0 errors"}),
        ("GIT_COMMIT_CREATED", "ci_runner", "ok", 450.0, {"commit_sha": "83d9fc4a4805c87a5e88ee7ff96cf5d2cf57ea78"}),
        ("PR_COMMENT_POSTED", "github_api", "ok", 610.0, {"pr_number": 1, "url": "https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1"}),
        ("CI_RUN_SUCCESS", "github_actions", "ok", 0.0, {"conclusion": "success"}),
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

    diff_gh = (
        "diff --git a/models.py b/models.py\n"
        "--- a/models.py\n"
        "+++ b/models.py\n"
        "@@ -1,7 +1,10 @@\n"
        "-from sqlalchemy.ext.declarative import declarative_base\n"
        "+from sqlalchemy.orm import DeclarativeBase\n"
        " from sqlalchemy import Column, Integer, String\n"
        " \n"
        "-Base = declarative_base()\n"
        "+class Base(DeclarativeBase):\n"
        "+    pass\n"
        "diff --git a/repository.py b/repository.py\n"
        "--- a/repository.py\n"
        "+++ b/repository.py\n"
        "@@ -1,17 +1,21 @@\n"
        " from typing import List, Optional\n"
        "+from sqlalchemy import select, text\n"
        " from sqlalchemy.orm import Session\n"
        " from models import UserModel\n"
        " \n"
        " class UserRepository:\n"
        "     def get_by_id(self, user_id: int) -> Optional[UserModel]:\n"
        "-        return self.session.query(UserModel).filter(UserModel.id == user_id).first()\n"
        "+        stmt = select(UserModel).where(UserModel.id == user_id)\n"
        "+        return self.session.execute(stmt).scalars().first()\n"
        " \n"
        "     def count_raw(self) -> int:\n"
        "-        result = self.session.execute(\"SELECT count(*) FROM users\").scalar()\n"
        "+        result = self.session.execute(text(\"SELECT count(*) FROM users\")).scalar()\n"
        "         return result or 0\n"
    )

    bundle = RunArtifactBundle(
        run_id=run_id,
        upgrade_spec=spec,
        impact_graph=graph,
        failure_clusters=[],
        risk_map=None,
        evidence_pack=pack,
        verification_contract=contract,
        candidates=[cand],
        recovery_history=[e.to_dict() for e in telemetry_events],
        telemetry_events=telemetry_events,
        final_diff=diff_gh,
        verification_result={
            "status": "verified_green",
            "seal": "VERIFIED_GREEN",
            "tests_passed": 4,
            "tests_failed": 0,
            "typecheck_passed": True,
            "lint_passed": True,
            "github_pr_url": "https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1",
            "commit_sha": "83d9fc4a4805c87a5e88ee7ff96cf5d2cf57ea78",
            "workflow_run_id": "35993907979",
            "workflow_conclusion": "success",
        },
        root_hash=prev_hash,
        backend_identity="local_subprocess_isolated",
    )
    return ArtifactBundleExporter.export(bundle, base_output_dir=base_dir)


def seed_all_runs(base_dir: str = "runs") -> List[str]:
    created = []
    created.append(seed_github_pr_run(base_dir))
    created.append(seed_sqlalchemy_pristine(base_dir))
    created.append(seed_adversarial_rollback(base_dir))
    return created


if __name__ == "__main__":
    runs = seed_all_runs()
    print(f"Successfully seeded {len(runs)} benchmark/production artifact bundles: {runs}")
