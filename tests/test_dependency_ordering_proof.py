"""
Dependency-Aware Ordering Proof Tests.
Proves that repair sequences are mathematically derived from the repository's Impact Graph
via Kahn's topological sorting algorithm on consumer-provider relationships, rather than hardcoded heuristics.
"""

import pytest
from patchpilot.types import UpgradeSpec, EdgeType, NodeType, FailureCluster, FailureRecord
from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
from patchpilot.intelligence.graph import ImpactGraphBuilder
from patchpilot.intelligence.ordering import DependencyAwareSequencer


def test_dependency_ordering_linear_chain_a_b_c(tmp_path):
    """
    Demonstrates a multi-file dependency chain:
    api.py -> services.py -> models.py
    where models.py is foundational, services.py wraps it, and api.py exposes it.
    Input order is intentionally reversed (api.py first) to prove graph derivation.
    """
    repo = tmp_path / "chain_repo"
    repo.mkdir()

    (repo / "models.py").write_text("import pydantic\nclass User(pydantic.BaseModel):\n    name: str\n", encoding="utf-8")
    (repo / "services.py").write_text("from models import User\nclass UserService:\n    def get(self) -> User: return User(name='x')\n", encoding="utf-8")
    (repo / "api.py").write_text("from services import UserService\ndef handler(): return UserService().get()\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    sequencer = DependencyAwareSequencer()

    # Intentionally provide shuffled / inverted target files
    input_order = ["api.py", "models.py", "services.py"]
    derived_order, rationale = sequencer.determine_repair_sequence(input_order, graph)

    # Derived sequence must strictly be models.py -> services.py -> api.py
    assert derived_order == ["models.py", "services.py", "api.py"], f"Expected foundational ordering, got {derived_order}"
    assert "models.py -> services.py -> api.py" in rationale
    assert "foundational definitions and schemas are remediated first" in rationale


def test_dependency_ordering_diamond_dag(tmp_path):
    """
    Demonstrates a diamond dependency DAG:
           core_schema.py
             /         \\
      auth_svc.py   billing_svc.py
             \\         /
            gateway.py
    Foundational core_schema.py must be repaired before intermediate services,
    and gateway.py (the ultimate downstream consumer) must be repaired last.
    """
    repo = tmp_path / "diamond_repo"
    repo.mkdir()

    (repo / "core_schema.py").write_text("import pydantic\nclass Account:\n    pass\n", encoding="utf-8")
    (repo / "auth_svc.py").write_text("from core_schema import Account\nclass Auth:\n    pass\n", encoding="utf-8")
    (repo / "billing_svc.py").write_text("from core_schema import Account\nclass Billing:\n    pass\n", encoding="utf-8")
    (repo / "gateway.py").write_text("from auth_svc import Auth\nfrom billing_svc import Billing\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    sequencer = DependencyAwareSequencer()

    # Pass in reverse order
    input_order = ["gateway.py", "billing_svc.py", "auth_svc.py", "core_schema.py"]
    derived_order, rationale = sequencer.determine_repair_sequence(input_order, graph)

    # core_schema must be index 0
    assert derived_order[0] == "core_schema.py"
    # gateway must be index 3 (last)
    assert derived_order[-1] == "gateway.py"
    # intermediate services must be in indices 1 and 2
    assert set(derived_order[1:3]) == {"auth_svc.py", "billing_svc.py"}


def test_dependency_ordering_cluster_enrichment(tmp_path):
    """
    Verifies that failure cluster context is properly incorporated into the repair rationale.
    """
    repo = tmp_path / "cluster_repo"
    repo.mkdir()

    (repo / "a.py").write_text("class A: pass\n", encoding="utf-8")
    (repo / "b.py").write_text("from a import A\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    cluster = FailureCluster(
        cluster_id="cluster_pydantic_1",
        dependency="pydantic",
        failure_category="validator_deprecated",
        exception_classes=["PydanticDeprecatedSince20"],
        symbols=["validator"],
        affected_files=["a.py"],
        member_failures=[],
        representative_failure=FailureRecord("r1", "t1", "a.py", 1, "validator", "DeprecationWarning", "", "", "pydantic", "validator_deprecated"),
    )

    sequencer = DependencyAwareSequencer()
    ordered, rationale = sequencer.determine_repair_sequence(["b.py", "a.py"], graph, clusters=[cluster])

    assert ordered == ["a.py", "b.py"]
    assert "cluster_pydantic_1" in rationale
    assert "validator_deprecated" in rationale
