"""
Impact Graph Engine: Deterministic Graph Model of Dependency Upgrade Surface.
Answers WHY files/symbols/tests are affected with machine-readable causal chains.
"""

from typing import Dict, List, Set, Optional, Any, Tuple
from collections import defaultdict, deque
from patchpilot.types import (
    ImpactNode,
    ImpactEdge,
    NodeType,
    EdgeType,
    UpgradeSpec,
    FailureRecord,
)
from patchpilot.intelligence.ast_analyzer import RepositoryAnalysis


class ImpactGraph:
    """Directed graph representing dependency impact, imports, symbols, and test failures."""

    def __init__(self, spec: UpgradeSpec):
        self.spec = spec
        self.nodes: Dict[str, ImpactNode] = {}  # node_id -> ImpactNode
        self.edges: List[ImpactEdge] = []
        self._adj: Dict[str, List[ImpactEdge]] = defaultdict(list)
        self._rev_adj: Dict[str, List[ImpactEdge]] = defaultdict(list)

    def add_node(self, node: ImpactNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, source: str, target: str, edge_type: EdgeType, explanation: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        edge = ImpactEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            explanation=explanation,
            metadata=metadata or {},
        )
        self.edges.append(edge)
        self._adj[source].append(edge)
        self._rev_adj[target].append(edge)

    def explain_impact(self, node_id: str) -> List[str]:
        """
        Derives the explainable causal path from the upgraded package to the given node.
        Returns a list of human/machine-readable path steps.
        """
        root_pkg_id = f"pkg:{self.spec.package_name.lower()}"
        if node_id == root_pkg_id:
            return [f"Root upgraded dependency: {self.spec.package_name} ({self.spec.old_version} -> {self.spec.new_version})"]

        # BFS from root_pkg_id to node_id
        queue: deque[Tuple[str, List[str]]] = deque([(root_pkg_id, [f"Package {self.spec.package_name}"])])
        visited: Set[str] = {root_pkg_id}

        found_path: Optional[List[str]] = None

        while queue:
            curr, path = queue.popleft()
            if curr == node_id:
                found_path = path
                break

            for edge in self._adj.get(curr, []):
                nxt = edge.target
                if nxt not in visited:
                    visited.add(nxt)
                    explanation = f" -> [{edge.edge_type.value}] {edge.explanation}"
                    queue.append((nxt, path + [explanation]))

        if found_path:
            return found_path

        # If not reachable directly from package root, check reverse path to nearest affected node
        return [f"Node {node_id} directly marked in impact scope for {self.spec.package_name}"]

    def get_topological_order(self, target_files: Optional[List[str]] = None) -> Tuple[List[str], str]:
        """
        Performs dependency-aware topological sorting of target files (upstream definitions first, downstream consumers last).
        Returns (ordered_file_list, explanation_text).
        """
        files = list(target_files) if target_files else [n.file_path for n in self.nodes.values() if n.file_path and n.node_type == NodeType.MODULE]
        file_set = set(files)

        # Build in-degree graph strictly among target files
        in_degree: Dict[str, int] = {f: 0 for f in file_set}
        graph: Dict[str, List[str]] = {f: [] for f in file_set}

        for edge in self.edges:
            # If edge represents dependency: target depends on source
            # E.g. A imports B -> B is upstream of A -> B must be repaired before A.
            # In our edges: source IMPORTS target means source depends on target.
            if edge.edge_type == EdgeType.IMPORTS:
                consumer = edge.source.replace("mod:", "")
                provider = edge.target.replace("mod:", "")
                if consumer in file_set and provider in file_set and consumer != provider:
                    # provider -> consumer
                    graph[provider].append(consumer)
                    in_degree[consumer] += 1

        # Kahn's algorithm
        queue = [f for f in file_set if in_degree[f] == 0]
        # Deterministic sorting for tie-breaking
        queue.sort()
        ordered: List[str] = []

        while queue:
            curr = queue.pop(0)
            ordered.append(curr)
            for nxt in graph[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
            queue.sort()

        # Add any cycles or remaining files
        for f in file_set:
            if f not in ordered:
                ordered.append(f)

        rationale = (
            f"Derived graph-based repair sequence ({' -> '.join(ordered)}): "
            "Upstream foundational definitions and schemas are remediated first before downstream callers/services."
        )
        return ordered, rationale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package": self.spec.package_name,
            "version_delta": f"{self.spec.old_version} -> {self.spec.new_version}",
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type.value,
                    "file_path": n.file_path,
                    "metadata": n.metadata,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                    "explanation": e.explanation,
                }
                for e in self.edges
            ],
        }


class ImpactGraphBuilder:
    """Constructs an ImpactGraph from static repository analysis and failure logs."""

    def build_graph(
        self,
        spec: UpgradeSpec,
        analysis: RepositoryAnalysis,
        failures: Optional[List[FailureRecord]] = None,
    ) -> ImpactGraph:
        graph = ImpactGraph(spec)

        # 1. Package Root Node
        pkg_id = f"pkg:{spec.package_name.lower()}"
        graph.add_node(
            ImpactNode(
                id=pkg_id,
                name=spec.package_name,
                node_type=NodeType.PACKAGE,
                metadata={"old_version": spec.old_version, "new_version": spec.new_version},
            )
        )

        # 2. Add Module and Symbol Nodes
        for rel_path, mod_info in analysis.modules.items():
            mod_id = f"mod:{rel_path}"
            n_type = NodeType.TEST if mod_info.is_test else NodeType.MODULE
            graph.add_node(
                ImpactNode(
                    id=mod_id,
                    name=mod_info.module_name,
                    node_type=n_type,
                    file_path=rel_path,
                )
            )

            # Link directly affected modules to package root
            if rel_path in analysis.directly_affected_files:
                graph.add_edge(
                    source=pkg_id,
                    target=mod_id,
                    edge_type=EdgeType.UPGRADE_TARGET,
                    explanation=f"{rel_path} imports {spec.package_name} ({', '.join(sorted(mod_info.direct_package_imports))})",
                )

            # Add defined symbols
            for sym_name, sym_info in mod_info.defined_symbols.items():
                sym_id = f"sym:{rel_path}:{sym_name}"
                graph.add_node(
                    ImpactNode(
                        id=sym_id,
                        name=sym_name,
                        node_type=NodeType.SYMBOL,
                        file_path=rel_path,
                        metadata={"kind": sym_info.kind, "line": sym_info.line, "bases": sym_info.base_classes},
                    )
                )
                graph.add_edge(
                    source=mod_id,
                    target=sym_id,
                    edge_type=EdgeType.DEFINES_SYMBOL,
                    explanation=f"{rel_path} defines {sym_info.kind} {sym_name}",
                )

        # 3. Add Import Edges (Consumer -> Provider)
        for consumer_file, imported_files in analysis.import_graph.items():
            consumer_id = f"mod:{consumer_file}"
            for provider_file in imported_files:
                provider_id = f"mod:{provider_file}"
                if consumer_id in graph.nodes and provider_id in graph.nodes:
                    is_test = analysis.modules[consumer_file].is_test
                    edge_type = EdgeType.TESTS_MODULE if is_test else EdgeType.IMPORTS
                    graph.add_edge(
                        source=consumer_id,
                        target=provider_id,
                        edge_type=edge_type,
                        explanation=f"{consumer_file} imports {provider_file}",
                    )

        # 4. Integrate Failure Nodes if provided
        if failures:
            for f in failures:
                fail_id = f"fail:{f.fingerprint()}"
                graph.add_node(
                    ImpactNode(
                        id=fail_id,
                        name=f.test_name,
                        node_type=NodeType.FAILURE,
                        file_path=f.file,
                        metadata={"category": f.category, "exception": f.exception_type, "message": f.message},
                    )
                )
                # Link failure to file
                clean_f_file = f.file.replace("\\", "/").strip()
                mod_f_id = f"mod:{clean_f_file}"
                if mod_f_id in graph.nodes:
                    graph.add_edge(
                        source=fail_id,
                        target=mod_f_id,
                        edge_type=EdgeType.FAILS_AT,
                        explanation=f"Test {f.test_name} failed with {f.exception_type} in {clean_f_file}",
                    )

        return graph
