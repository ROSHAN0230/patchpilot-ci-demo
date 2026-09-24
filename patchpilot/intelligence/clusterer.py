"""
Migration-Level Failure Clustering Engine.
Clusters raw pytest failure records by root breaking-change category, symbols, and impact graph proximity.
"""

from collections import defaultdict
from typing import List, Dict, Set, Optional, Any
from patchpilot.types import FailureRecord, FailureCluster, UpgradeSpec
from patchpilot.intelligence.graph import ImpactGraph


class FailureClusterer:
    """Clusters normalized FailureRecords into coherent migration issue clusters."""

    def cluster_failures(
        self,
        failures: List[FailureRecord],
        spec: UpgradeSpec,
        graph: Optional[ImpactGraph] = None,
    ) -> List[FailureCluster]:
        if not failures:
            return []

        # Group by (dependency, category, dominant_symbol_or_exception)
        buckets: Dict[str, List[FailureRecord]] = defaultdict(list)

        for f in failures:
            dep = f.dependency or spec.package_name
            cat = f.category or "general_migration"
            # Normalize symbol or fall back to exception type
            sym = f.symbol or f.exception_type or "core"
            key = f"{dep.lower()}::{cat}::{sym.lower()}"
            buckets[key].append(f)

        clusters: List[FailureCluster] = []
        cluster_idx = 1

        for key, member_list in buckets.items():
            rep = member_list[0]
            affected_files: Set[str] = set()
            exception_classes: Set[str] = set()
            symbols: Set[str] = set()

            for mem in member_list:
                clean_f = mem.file.replace("\\", "/").strip()
                if clean_f:
                    affected_files.add(clean_f)
                for rel in mem.related_files:
                    affected_files.add(rel.replace("\\", "/").strip())
                exception_classes.add(mem.exception_type)
                if mem.symbol:
                    symbols.add(mem.symbol)

            # Extract graph relationships if graph available
            graph_context: Dict[str, Any] = {}
            if graph:
                related_nodes = []
                for f_path in affected_files:
                    mod_id = f"mod:{f_path}"
                    if mod_id in graph.nodes:
                        related_nodes.append(mod_id)
                        explanations = graph.explain_impact(mod_id)
                        graph_context[mod_id] = explanations

            cluster_id = f"cluster_{spec.package_name.lower()}_{cluster_idx}_{rep.category}"
            cluster_idx += 1

            clusters.append(
                FailureCluster(
                    cluster_id=cluster_id,
                    dependency=spec.package_name,
                    failure_category=rep.category,
                    exception_classes=sorted(list(exception_classes)),
                    symbols=sorted(list(symbols)),
                    affected_files=sorted(list(affected_files)),
                    member_failures=member_list,
                    representative_failure=rep,
                    graph_context=graph_context,
                    evidence_references=[],
                )
            )

        return clusters
