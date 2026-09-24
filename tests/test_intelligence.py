"""
Unit Tests for Week 2 Repository Intelligence, Impact Graph, Clustering, and Security Policies.
"""

import os
import tempfile
import pytest
from patchpilot.types import (
    UpgradeSpec,
    DependencyDelta,
    FailureRecord,
    NodeType,
    EdgeType,
)
from patchpilot.intelligence.manifest import ManifestAnalyzer
from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
from patchpilot.intelligence.graph import ImpactGraphBuilder
from patchpilot.intelligence.clusterer import FailureClusterer
from patchpilot.intelligence.ordering import DependencyAwareSequencer
from patchpilot.intelligence.risk_map import RiskMapGenerator
from patchpilot.sandbox.security import SandboxSecurityPolicy, SecurityViolationError


def test_manifest_analyzer_pyproject():
    analyzer = ManifestAnalyzer()
    with tempfile.TemporaryDirectory() as tmpdir:
        pyproject_content = """[project]
name = "demo-app"
version = "0.1.0"
dependencies = [
    "pydantic>=2.6.4",
    "requests==2.31.0",
]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        spec = analyzer.detect_upgrade(tmpdir, package_hint="pydantic")
        assert spec is not None
        assert spec.package_name == "pydantic"
        assert spec.new_version == "2.6.4"
        assert spec.old_version == "1.10.14"
        assert spec.upgrade_type == "major"
        assert spec.manifest_path == "pyproject.toml"


def test_manifest_analyzer_requirements():
    analyzer = ManifestAnalyzer()
    with tempfile.TemporaryDirectory() as tmpdir:
        req_content = "sqlalchemy==2.0.28\npytest>=8.0.0\n"
        with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
            f.write(req_content)

        spec = analyzer.detect_upgrade(tmpdir, package_hint="sqlalchemy")
        assert spec is not None
        assert spec.package_name == "sqlalchemy"
        assert spec.new_version == "2.0.28"
        assert spec.old_version == "1.4.49"
        assert spec.upgrade_type == "major"


def test_ast_analyzer_and_impact_graph():
    ast_analyzer = AstRepositoryAnalyzer()
    graph_builder = ImpactGraphBuilder()

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "core"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "services"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "tests"), exist_ok=True)

        with open(os.path.join(tmpdir, "core", "schemas.py"), "w") as f:
            f.write("import pydantic\nclass Item(pydantic.BaseModel):\n    name: str\n")

        with open(os.path.join(tmpdir, "services", "item_service.py"), "w") as f:
            f.write("from core.schemas import Item\ndef get_item():\n    return Item(name='test')\n")

        with open(os.path.join(tmpdir, "tests", "test_items.py"), "w") as f:
            f.write("from services.item_service import get_item\ndef test_get():\n    assert get_item().name == 'test'\n")

        spec = UpgradeSpec("pydantic", "1.10.14", "2.6.4")
        analysis = ast_analyzer.analyze_repository(tmpdir, "pydantic")

        assert "core/schemas.py" in analysis.directly_affected_files
        assert "services/item_service.py" in analysis.transitively_affected_files

        graph = graph_builder.build_graph(spec, analysis)
        assert len(graph.nodes) >= 4
        assert len(graph.edges) >= 3

        # Explain impact path for services/item_service.py
        explanations = graph.explain_impact("mod:services/item_service.py")
        assert len(explanations) > 0
        path_str = " ".join(explanations)
        assert "pydantic" in path_str.lower() or "item_service.py" in path_str


def test_dependency_aware_ordering():
    sequencer = DependencyAwareSequencer()
    graph_builder = ImpactGraphBuilder()
    ast_analyzer = AstRepositoryAnalyzer()

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "app"), exist_ok=True)
        # B depends on A
        with open(os.path.join(tmpdir, "app", "base.py"), "w") as f:
            f.write("import pydantic\nclass Base:\n    pass\n")
        with open(os.path.join(tmpdir, "app", "derived.py"), "w") as f:
            f.write("from app.base import Base\nclass Derived(Base):\n    pass\n")

        spec = UpgradeSpec("pydantic", "1.10.14", "2.6.4")
        analysis = ast_analyzer.analyze_repository(tmpdir, "pydantic")
        graph = graph_builder.build_graph(spec, analysis)

        # Pass in reverse order: [derived, base]
        files = ["app/derived.py", "app/base.py"]
        ordered, rationale = sequencer.determine_repair_sequence(files, graph)

        # Topological ordering MUST place base before derived
        assert ordered == ["app/base.py", "app/derived.py"]
        assert "Derived graph-based repair sequence" in rationale


def test_failure_clustering():
    clusterer = FailureClusterer()
    spec = UpgradeSpec("pydantic", "1.10.14", "2.6.4")

    failures = [
        FailureRecord(
            run_id="run1",
            test_name="test_schema_a",
            file="core/schemas.py",
            line=10,
            symbol="validator",
            exception_type="PydanticDeprecatedSince20",
            message="@validator is deprecated in V2",
            stack_trace="...",
            dependency="pydantic",
            category="validator_deprecation",
        ),
        FailureRecord(
            run_id="run1",
            test_name="test_schema_b",
            file="core/models.py",
            line=25,
            symbol="validator",
            exception_type="PydanticDeprecatedSince20",
            message="@validator is deprecated in V2",
            stack_trace="...",
            dependency="pydantic",
            category="validator_deprecation",
        ),
        FailureRecord(
            run_id="run1",
            test_name="test_dict_dump",
            file="services/service.py",
            line=40,
            symbol="dict",
            exception_type="UserError",
            message=".dict() is deprecated",
            stack_trace="...",
            dependency="pydantic",
            category="model_dump_migration",
        ),
    ]

    clusters = clusterer.cluster_failures(failures, spec)
    # The two validator failures should be clustered together!
    assert len(clusters) == 2
    validator_cluster = next(c for c in clusters if c.failure_category == "validator_deprecation")
    assert len(validator_cluster.member_failures) == 2
    assert "core/schemas.py" in validator_cluster.affected_files
    assert "core/models.py" in validator_cluster.affected_files


def test_risk_map_generation():
    risk_gen = RiskMapGenerator()
    spec = UpgradeSpec("sqlalchemy", "1.4.49", "2.0.28")

    from patchpilot.intelligence.ast_analyzer import RepositoryAnalysis
    analysis = RepositoryAnalysis(repo_dir=".", target_package="sqlalchemy")
    analysis.directly_affected_files.add("models.py")

    from patchpilot.intelligence.graph import ImpactGraph
    graph = ImpactGraph(spec)

    risk_map = risk_gen.generate_risk_map(spec, analysis, graph, [])
    assert len(risk_map.known_breaking_changes) > 0
    assert any("declarative" in bc.lower() or "select" in bc.lower() for bc in risk_map.known_breaking_changes)
    assert 0.0 <= risk_map.uncertainty_score <= 1.0


def test_sandbox_security_policy():
    # Test sensitive environment variable scrubbing
    dirty_env = {
        "PATH": "C:\\Windows\\system32",
        "NEBIUS_API_KEY": "secret_key_123",
        "TAVILY_API_KEY": "tvly_secret_456",
        "AWS_SECRET_ACCESS_KEY": "super_secret",
        "TEMP": "C:\\Temp",
    }
    clean_env = SandboxSecurityPolicy.sanitize_environment(dirty_env)
    assert "NEBIUS_API_KEY" not in clean_env
    assert "TAVILY_API_KEY" not in clean_env
    assert "AWS_SECRET_ACCESS_KEY" not in clean_env
    assert clean_env["PATH"] == "C:\\Windows\\system32"

    # Test forbidden commands
    with pytest.raises(SecurityViolationError):
        SandboxSecurityPolicy.validate_command(["rm", "-rf", "/"])

    # Test safe commands
    SandboxSecurityPolicy.validate_command(["pytest", "tests/", "-v"])
