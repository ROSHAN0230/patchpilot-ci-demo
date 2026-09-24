"""
Dependency-Aware Repair Sequencer.
Derives deterministic file repair sequences using topological graph analysis.
"""

from typing import List, Tuple, Set, Dict, Optional
from patchpilot.intelligence.graph import ImpactGraph
from patchpilot.types import FailureCluster


class DependencyAwareSequencer:
    """Computes deterministic repair sequences for multi-file migration recovery cases."""

    def determine_repair_sequence(
        self,
        target_files: List[str],
        graph: ImpactGraph,
        clusters: Optional[List[FailureCluster]] = None,
    ) -> Tuple[List[str], str]:
        """
        Derives repair order from the ImpactGraph.
        Ensures upstream definitions and models are remediated before downstream consumers.
        """
        if len(target_files) <= 1:
            return target_files, "Single file remediation; ordering is trivial."

        # Use the impact graph's topological ordering
        ordered, rationale = graph.get_topological_order(target_files)

        # Supplement rationale with cluster information if available
        if clusters:
            cluster_summary = [f"{c.cluster_id} ({c.failure_category})" for c in clusters[:3]]
            rationale += f" Addresses failure clusters: {', '.join(cluster_summary)}."

        return ordered, rationale
