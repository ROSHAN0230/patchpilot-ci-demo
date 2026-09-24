"""
Migration Risk Map Generator.
Constructs structured risk assessments before autonomous code modifications.
"""

from typing import List, Dict, Any, Optional
from patchpilot.types import (
    UpgradeSpec,
    MigrationRiskMap,
    FailureCluster,
)
from patchpilot.intelligence.graph import ImpactGraph
from patchpilot.intelligence.ast_analyzer import RepositoryAnalysis


class RiskMapGenerator:
    """Evaluates upgrade blast radius and produces structured MigrationRiskMaps."""

    # Known breaking changes catalog
    KNOWN_BREAKING_CHANGES = {
        "pydantic": {
            "2": [
                "Config class replaced by model_config = ConfigDict(...)",
                "orm_mode renamed to from_attributes",
                "@validator deprecated and replaced by @field_validator with @classmethod",
                ".dict() deprecated and replaced by .model_dump()",
                "from_orm(obj) replaced by model_validate(obj)",
                "__root__ models replaced by RootModel",
                "Field regex parameter renamed to pattern",
            ]
        },
        "sqlalchemy": {
            "2": [
                "declarative_base() moved/deprecated in favor of DeclarativeBase class inheritance",
                "session.query() legacy interface replaced by select() with session.execute().scalars()",
                "Engine-level autocommit removed; explicit connection.begin() / commit() required",
                "engine.execute() removed; use with engine.connect() as conn: conn.execute()",
                "select(...) statements require scalar iteration instead of tuple slicing",
            ]
        },
    }

    def generate_risk_map(
        self,
        spec: UpgradeSpec,
        analysis: RepositoryAnalysis,
        graph: ImpactGraph,
        clusters: Optional[List[FailureCluster]] = None,
    ) -> MigrationRiskMap:
        pkg_lower = spec.package_name.lower()
        major_v = spec.new_version.split(".")[0]

        breaking_changes = self.KNOWN_BREAKING_CHANGES.get(pkg_lower, {}).get(major_v, [
            f"Major version bump for {spec.package_name} ({spec.old_version} -> {spec.new_version})"
        ])

        affected_mods = sorted(list(analysis.directly_affected_files.union(analysis.transitively_affected_files)))
        affected_syms: List[str] = []
        for mod in affected_mods:
            mod_info = analysis.modules.get(mod)
            if mod_info:
                affected_syms.extend([f"{mod}:{s}" for s in mod_info.defined_symbols])

        affected_tests = sorted(list(analysis.test_mapping.keys()))

        # Evaluate semantic risk regions
        semantic_risk_regions: List[Dict[str, Any]] = []
        for mod in analysis.directly_affected_files:
            consumers = analysis.reverse_import_graph.get(mod, set())
            in_degree = len(consumers)
            has_tests = any(mod in tests for tests in analysis.test_mapping.values())

            risk_level = "HIGH" if in_degree >= 2 else ("MEDIUM" if in_degree == 1 else "LOW")
            semantic_risk_regions.append({
                "file_path": mod,
                "in_degree": in_degree,
                "dependent_consumers": sorted(list(consumers)),
                "has_direct_tests": has_tests,
                "risk_level": risk_level,
                "rationale": f"Module {mod} is consumed by {in_degree} downstream files. Direct tests: {has_tests}."
            })

        # Uncertainty score calculation
        # Factors: presence of untested affected files, number of failure clusters, transitive blast radius
        untested_count = sum(1 for r in semantic_risk_regions if not r["has_direct_tests"])
        cluster_factor = len(clusters) * 0.1 if clusters else 0.2
        transitive_factor = min(len(analysis.transitively_affected_files) * 0.1, 0.4)
        base_uncertainty = (untested_count * 0.15) + cluster_factor + transitive_factor
        uncertainty = round(min(max(base_uncertainty, 0.1), 0.95), 2)

        evidence_refs: List[str] = []
        if clusters:
            for c in clusters:
                evidence_refs.extend(c.evidence_references)

        return MigrationRiskMap(
            spec=spec,
            known_breaking_changes=breaking_changes,
            affected_modules=affected_mods,
            affected_symbols=affected_syms[:30],
            affected_tests=affected_tests,
            semantic_risk_regions=semantic_risk_regions,
            uncertainty_score=uncertainty,
            evidence_references=evidence_refs,
        )
