"""
Deterministic AST Repository Analyzer for Python.
Parses AST to extract module definitions, import graphs, symbol tables, and test linkages.
"""

import ast
import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any


@dataclass
class SymbolInfo:
    name: str
    kind: str  # "class", "function", "variable"
    file_path: str
    line: int
    docstring: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    file_path: str  # relative path, e.g. "core/config.py"
    module_name: str  # dotted, e.g. "core.config"
    is_test: bool
    imports: Set[str] = field(default_factory=set)  # imported module names or symbols
    direct_package_imports: Set[str] = field(default_factory=set)  # symbols imported directly from target package
    defined_symbols: Dict[str, SymbolInfo] = field(default_factory=dict)
    called_symbols: Set[str] = field(default_factory=set)


@dataclass
class RepositoryAnalysis:
    repo_dir: str
    target_package: str
    modules: Dict[str, ModuleInfo] = field(default_factory=dict)  # file_path -> ModuleInfo
    import_graph: Dict[str, Set[str]] = field(default_factory=dict)  # file_path -> set of imported file_paths
    reverse_import_graph: Dict[str, Set[str]] = field(default_factory=dict)  # file_path -> set of importing file_paths
    symbol_table: Dict[str, SymbolInfo] = field(default_factory=dict)  # "core.schemas.UserDTO" -> SymbolInfo
    test_mapping: Dict[str, Set[str]] = field(default_factory=dict)  # test_file -> set of exercised src_files
    directly_affected_files: Set[str] = field(default_factory=set)
    transitively_affected_files: Set[str] = field(default_factory=set)


class AstRepositoryAnalyzer:
    """Parses Python source files using standard library `ast`."""

    def __init__(self, ignore_dirs: Optional[Set[str]] = None):
        self.ignore_dirs = ignore_dirs or {".venv", "venv", ".git", "__pycache__", "build", "dist", ".pytest_cache"}

    def analyze_repository(self, repo_dir: str, target_package: str) -> RepositoryAnalysis:
        analysis = RepositoryAnalysis(repo_dir=repo_dir, target_package=target_package.lower())
        py_files: List[str] = []

        # 1. Discover all Python files
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), repo_dir).replace("\\", "/")
                    py_files.append(rel_path)

        # 2. Parse AST for each file
        module_name_to_file: Dict[str, str] = {}
        for rel_path in py_files:
            abs_path = os.path.join(repo_dir, rel_path)
            mod_name = self._to_module_name(rel_path)
            module_name_to_file[mod_name] = rel_path
            # Also register suffix aliases for relative imports
            parts = mod_name.split(".")
            for i in range(len(parts)):
                sub = ".".join(parts[i:])
                if sub not in module_name_to_file:
                    module_name_to_file[sub] = rel_path

            mod_info = self._parse_file(rel_path, abs_path, target_package)
            analysis.modules[rel_path] = mod_info

            for sym_name, sym_info in mod_info.defined_symbols.items():
                qualified = f"{mod_name}.{sym_name}"
                analysis.symbol_table[qualified] = sym_info

        # 3. Construct import graphs and test linkages
        target_pkg_lower = target_package.lower()
        for rel_path, mod_info in analysis.modules.items():
            analysis.import_graph[rel_path] = set()
            if rel_path not in analysis.reverse_import_graph:
                analysis.reverse_import_graph[rel_path] = set()

            # Check direct package imports
            if mod_info.direct_package_imports:
                analysis.directly_affected_files.add(rel_path)

            for imp in mod_info.imports:
                # Resolve to local file
                imported_file = self._resolve_import(imp, rel_path, module_name_to_file)
                if imported_file and imported_file != rel_path:
                    analysis.import_graph[rel_path].add(imported_file)
                    if imported_file not in analysis.reverse_import_graph:
                        analysis.reverse_import_graph[imported_file] = set()
                    analysis.reverse_import_graph[imported_file].add(rel_path)

                    # If this is a test file, link to tested source file
                    if mod_info.is_test:
                        if rel_path not in analysis.test_mapping:
                            analysis.test_mapping[rel_path] = set()
                        analysis.test_mapping[rel_path].add(imported_file)

        # 4. Compute transitive impact
        visited = set(analysis.directly_affected_files)
        queue = list(analysis.directly_affected_files)
        while queue:
            curr = queue.pop(0)
            for consumer in analysis.reverse_import_graph.get(curr, set()):
                if consumer not in visited:
                    visited.add(consumer)
                    analysis.transitively_affected_files.add(consumer)
                    queue.append(consumer)

        return analysis

    def _parse_file(self, rel_path: str, abs_path: str, target_package: str) -> ModuleInfo:
        mod_name = self._to_module_name(rel_path)
        is_test = "test" in rel_path.lower() or os.path.basename(rel_path).startswith("test_")
        mod_info = ModuleInfo(file_path=rel_path, module_name=mod_name, is_test=is_test)

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                code = f.read()
            tree = ast.parse(code, filename=rel_path)
        except Exception:
            return mod_info

        target_pkg_lower = target_package.lower()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_info.imports.add(alias.name)
                    if alias.name.lower() == target_pkg_lower or alias.name.lower().startswith(f"{target_pkg_lower}."):
                        mod_info.direct_package_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                mod_info.imports.add(module)
                if module.lower() == target_pkg_lower or module.lower().startswith(f"{target_pkg_lower}."):
                    for alias in node.names:
                        mod_info.direct_package_imports.add(f"{module}.{alias.name}")
            elif isinstance(node, ast.ClassDef):
                bases = []
                for b in node.bases:
                    if isinstance(b, ast.Name):
                        bases.append(b.id)
                    elif isinstance(b, ast.Attribute):
                        bases.append(f"{ast.unparse(b.value)}.{b.attr}")
                decs = [ast.unparse(d) for d in node.decorator_list]
                mod_info.defined_symbols[node.name] = SymbolInfo(
                    name=node.name,
                    kind="class",
                    file_path=rel_path,
                    line=node.lineno,
                    base_classes=bases,
                    decorators=decs,
                )
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                decs = [ast.unparse(d) for d in node.decorator_list]
                mod_info.defined_symbols[node.name] = SymbolInfo(
                    name=node.name,
                    kind="function",
                    file_path=rel_path,
                    line=node.lineno,
                    decorators=decs,
                )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    mod_info.called_symbols.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    mod_info.called_symbols.add(node.func.attr)

        return mod_info

    def _resolve_import(self, imp_name: str, src_file: str, name_to_file: Dict[str, str]) -> Optional[str]:
        if not imp_name:
            return None
        # Direct match
        if imp_name in name_to_file:
            return name_to_file[imp_name]
        # Check submodules
        parts = imp_name.split(".")
        for i in range(len(parts), 0, -1):
            sub = ".".join(parts[:i])
            if sub in name_to_file:
                return name_to_file[sub]

        # Handle relative imports (e.g. from .config import TagList)
        src_dir = os.path.dirname(src_file).replace("\\", "/")
        if src_dir:
            combined = f"{src_dir.replace('/', '.')}.{imp_name}"
            if combined in name_to_file:
                return name_to_file[combined]
        return None

    def _to_module_name(self, rel_path: str) -> str:
        clean = rel_path
        if clean.endswith(".py"):
            clean = clean[:-3]
        if clean.endswith("/__init__"):
            clean = clean[:-9]
        return clean.replace("/", ".")
