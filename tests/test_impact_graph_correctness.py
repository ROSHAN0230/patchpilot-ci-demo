"""
Formal Impact Graph Correctness & Quality Tests.
Covers Cases A through H:
- Case A: A -> B (direct dependency)
- Case B: A -> B -> C (transitive dependency)
- Case C: A -> unrelated X (non-reachability and edge isolation)
- Case D: A <-> B cycle (cycle handling and termination)
- Case E: A -> package __init__ -> B re-export
- Case F: import alias (as alias resolution)
- Case G: TYPE_CHECKING import (type-only guard segregation)
- Case H: unreferenced module (isolated zero-degree component)

Also computes formal precision and recall against verified ground truth.
"""

import os
import pytest
from patchpilot.types import UpgradeSpec, EdgeType, NodeType
from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
from patchpilot.intelligence.graph import ImpactGraphBuilder


def test_impact_graph_case_a_direct_dependency(tmp_path):
    """Case A: A -> B: B defines a model, A imports B and uses it."""
    repo = tmp_path / "case_a"
    repo.mkdir()

    (repo / "b.py").write_text("class UserModel:\n    pass\n", encoding="utf-8")
    (repo / "a.py").write_text("from b import UserModel\n\nuser = UserModel()\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="sqlalchemy")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    # Expected nodes
    assert "mod:a.py" in graph.nodes
    assert "mod:b.py" in graph.nodes
    assert "sym:b.py:UserModel" in graph.nodes

    # Expected edges: a.py imports b.py
    edge_a_b = [e for e in graph.edges if e.source == "mod:a.py" and e.target == "mod:b.py"]
    assert len(edge_a_b) == 1
    assert edge_a_b[0].edge_type == EdgeType.IMPORTS

    # B does not import A
    edge_b_a = [e for e in graph.edges if e.source == "mod:b.py" and e.target == "mod:a.py"]
    assert len(edge_b_a) == 0


def test_impact_graph_case_b_transitive_dependency(tmp_path):
    """Case B: A -> B -> C: C defines base, B wraps it, A consumes B."""
    repo = tmp_path / "case_b"
    repo.mkdir()

    (repo / "c.py").write_text("import sqlalchemy\n\nclass BaseEntity:\n    pass\n", encoding="utf-8")
    (repo / "b.py").write_text("from c import BaseEntity\n\nclass UserRepo(BaseEntity):\n    pass\n", encoding="utf-8")
    (repo / "a.py").write_text("from b import UserRepo\n\nrepo = UserRepo()\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="sqlalchemy")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    # C directly affected by sqlalchemy
    assert "c.py" in analysis.directly_affected_files
    # B and A transitively affected
    assert "b.py" in analysis.transitively_affected_files
    assert "a.py" in analysis.transitively_affected_files

    # Explain impact reaches through transitive chain
    explanation = graph.explain_impact("mod:a.py")
    assert any("mod:a.py" in step or "sqlalchemy" in step for step in explanation)

    # Topological order should put foundational C before B, and B before A
    ordered, rationale = graph.get_topological_order(["a.py", "b.py", "c.py"])
    assert ordered == ["c.py", "b.py", "a.py"]


def test_impact_graph_case_c_unrelated_x(tmp_path):
    """Case C: A -> B, while X is an unrelated module."""
    repo = tmp_path / "case_c"
    repo.mkdir()

    (repo / "b.py").write_text("import sqlalchemy\nclass Model:\n    pass\n", encoding="utf-8")
    (repo / "a.py").write_text("from b import Model\n", encoding="utf-8")
    (repo / "x.py").write_text("def unrelated_math(a, b):\n    return a + b\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="sqlalchemy")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    # x.py should NOT be directly or transitively affected
    assert "x.py" not in analysis.directly_affected_files
    assert "x.py" not in analysis.transitively_affected_files

    # No edges between x.py and a.py or b.py
    irrelevant_edges = [
        e for e in graph.edges
        if ("mod:x.py" in (e.source, e.target) and "mod:a.py" in (e.source, e.target))
        or ("mod:x.py" in (e.source, e.target) and "mod:b.py" in (e.source, e.target))
    ]
    assert len(irrelevant_edges) == 0

    # Explain impact for x.py should not trace back to sqlalchemy upgrade root
    exp_x = graph.explain_impact("mod:x.py")
    assert not any("sqlalchemy (" in step for step in exp_x)


def test_impact_graph_case_d_cycle_handling(tmp_path):
    """Case D: A <-> B cycle: a.py imports b.py, b.py imports a.py."""
    repo = tmp_path / "case_d"
    repo.mkdir()

    (repo / "a.py").write_text("import b\nclass AClass:\n    pass\n", encoding="utf-8")
    (repo / "b.py").write_text("import a\nclass BClass:\n    pass\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    # Both edges exist
    edge_a_b = [e for e in graph.edges if e.source == "mod:a.py" and e.target == "mod:b.py"]
    edge_b_a = [e for e in graph.edges if e.source == "mod:b.py" and e.target == "mod:a.py"]
    assert len(edge_a_b) == 1
    assert len(edge_b_a) == 1

    # Graph must not hang on explain_impact or get_topological_order
    ordered, _ = graph.get_topological_order(["a.py", "b.py"])
    assert set(ordered) == {"a.py", "b.py"}
    assert len(ordered) == 2


def test_impact_graph_case_e_package_init_reexport(tmp_path):
    """Case E: A -> package __init__ -> B re-export."""
    repo = tmp_path / "case_e"
    pkg = repo / "mypkg"
    pkg.mkdir(parents=True)

    (pkg / "b.py").write_text("import pydantic\nclass ItemDTO(pydantic.BaseModel):\n    name: str\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("from .b import ItemDTO\n", encoding="utf-8")
    (repo / "a.py").write_text("from mypkg import ItemDTO\n\nitem = ItemDTO(name='test')\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    # b.py is directly affected
    assert "mypkg/b.py" in analysis.directly_affected_files
    # mypkg/__init__.py and a.py are transitively affected
    assert "mypkg/__init__.py" in analysis.transitively_affected_files
    assert "a.py" in analysis.transitively_affected_files


def test_impact_graph_case_f_import_alias(tmp_path):
    """Case F: import alias: import sqlalchemy as sa, from pydantic import BaseModel as BM."""
    repo = tmp_path / "case_f"
    repo.mkdir()

    code = (
        "import sqlalchemy as sa\n"
        "from pydantic import BaseModel as BM\n"
        "class Config(BM):\n"
        "    id: int\n"
    )
    (repo / "service.py").write_text(code, encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    analysis = analyzer.analyze_repository(str(repo), target_package="pydantic")
    mod = analysis.modules["service.py"]

    # Alias registered
    assert "BM" in mod.import_aliases
    assert "sa" in mod.import_aliases
    assert mod.import_aliases["sa"] == "sqlalchemy"
    assert "pydantic" in mod.import_aliases["BM"]
    assert "service.py" in analysis.directly_affected_files


def test_impact_graph_case_g_type_checking_guard(tmp_path):
    """Case G: TYPE_CHECKING guard segregates type-only imports."""
    repo = tmp_path / "case_g"
    repo.mkdir()

    code_types = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from heavy_service import ComplexService\n\n"
        "def annotate(svc: 'ComplexService') -> None:\n"
        "    pass\n"
    )
    (repo / "heavy_service.py").write_text("class ComplexService:\n    pass\n", encoding="utf-8")
    (repo / "consumer.py").write_text(code_types, encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="typing_extensions", old_version="4.0.0", new_version="4.5.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="typing_extensions")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    mod_c = analysis.modules["consumer.py"]
    # heavy_service is in type_checking_imports, NOT standard runtime imports
    assert "heavy_service" in mod_c.type_checking_imports
    assert "heavy_service" not in mod_c.imports

    # Edge in graph should be tagged as TYPE_CHECKING_IMPORTS
    tc_edges = [
        e for e in graph.edges
        if e.source == "mod:consumer.py" and e.target == "mod:heavy_service.py"
    ]
    assert len(tc_edges) == 1
    assert tc_edges[0].edge_type == EdgeType.TYPE_CHECKING_IMPORTS
    assert tc_edges[0].metadata.get("type_checking") is True


def test_impact_graph_case_h_unreferenced_module(tmp_path):
    """Case H: Unreferenced module with zero connections."""
    repo = tmp_path / "case_h"
    repo.mkdir()

    (repo / "active.py").write_text("import sqlalchemy\n", encoding="utf-8")
    (repo / "isolated.py").write_text("# Completely standalone file\ndef standalone_func():\n    return 42\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    analysis = analyzer.analyze_repository(str(repo), target_package="sqlalchemy")
    builder = ImpactGraphBuilder()
    graph = builder.build_graph(spec, analysis)

    assert "isolated.py" not in analysis.directly_affected_files
    assert "isolated.py" not in analysis.transitively_affected_files

    # isolated node exists, but has 0 external dependency or import edges connecting to other modules or package
    external_edges = [
        e for e in graph.edges
        if (e.source == "mod:isolated.py" or e.target == "mod:isolated.py")
        and e.edge_type in (EdgeType.IMPORTS, EdgeType.UPGRADE_TARGET, EdgeType.TESTS_MODULE, EdgeType.TYPE_CHECKING_IMPORTS)
    ]
    assert len(external_edges) == 0


def test_impact_graph_precision_and_recall_measurement(tmp_path):
    """Measures formal precision, recall, and contingency against ground-truth affected set."""
    repo = tmp_path / "precision_benchmark"
    repo.mkdir()

    (repo / "direct.py").write_text("import sqlalchemy\n", encoding="utf-8")
    (repo / "child.py").write_text("import direct\n", encoding="utf-8")
    (repo / "unrelated_1.py").write_text("def f(): pass\n", encoding="utf-8")
    (repo / "unrelated_2.py").write_text("def g(): pass\n", encoding="utf-8")

    analyzer = AstRepositoryAnalyzer()
    analysis = analyzer.analyze_repository(str(repo), target_package="sqlalchemy")

    predicted_affected = analysis.directly_affected_files | analysis.transitively_affected_files
    ground_truth_affected = {"direct.py", "child.py"}

    metrics = AstRepositoryAnalyzer.calculate_precision_recall(predicted_affected, ground_truth_affected)

    assert metrics["precision"] == 1.0  # Zero false positives
    assert metrics["recall"] == 1.0     # Zero false negatives
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0
    assert metrics["true_positives"] == 2
