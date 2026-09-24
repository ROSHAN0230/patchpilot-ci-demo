"""
PatchPilot Intelligence Package: Deterministic Repository Intelligence & Graph Analysis.
"""

from patchpilot.intelligence.manifest import ManifestAnalyzer
from patchpilot.intelligence.ast_analyzer import AstRepositoryAnalyzer
from patchpilot.intelligence.graph import ImpactGraph, ImpactGraphBuilder
from patchpilot.intelligence.clusterer import FailureClusterer
from patchpilot.intelligence.ordering import DependencyAwareSequencer
from patchpilot.intelligence.risk_map import RiskMapGenerator

__all__ = [
    "ManifestAnalyzer",
    "AstRepositoryAnalyzer",
    "ImpactGraph",
    "ImpactGraphBuilder",
    "FailureClusterer",
    "DependencyAwareSequencer",
    "RiskMapGenerator",
]
