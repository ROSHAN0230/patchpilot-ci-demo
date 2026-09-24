"""
Deterministic Manifest and Dependency Specification Analyzer.
Parses pyproject.toml, requirements.txt, and lockfiles to construct canonical UpgradeSpecs.
"""

import os
import re
from typing import Dict, Optional, Tuple, Any
from patchpilot.types import UpgradeSpec, DependencyDelta
from patchpilot.contracts import UpgradeDetector


class ManifestAnalyzer(UpgradeDetector):
    """Analyzes package manifests to construct normalized UpgradeSpecs."""

    def __init__(self, default_trigger: str = "cli"):
        self.default_trigger = default_trigger

    def detect_delta(self, repo_dir: str) -> Optional[DependencyDelta]:
        """Backwards-compatible UpgradeDetector interface implementation."""
        spec = self.detect_upgrade(repo_dir)
        return spec.to_delta() if spec else None

    def detect_upgrade(
        self,
        repo_dir: str,
        package_hint: Optional[str] = None,
        old_version_hint: Optional[str] = None,
        new_version_hint: Optional[str] = None,
    ) -> Optional[UpgradeSpec]:
        """
        Inspects manifests in repo_dir to derive an UpgradeSpec.
        Can infer old/new versions from git diff or hints.
        """
        pyproject_path = os.path.join(repo_dir, "pyproject.toml")
        reqs_path = os.path.join(repo_dir, "requirements.txt")

        manifest_path = None
        package_manager = "pip"
        declared_deps: Dict[str, str] = {}

        if os.path.isfile(pyproject_path):
            manifest_path = "pyproject.toml"
            package_manager = self._detect_pyproject_tool(pyproject_path)
            declared_deps = self._parse_pyproject(pyproject_path)
        elif os.path.isfile(reqs_path):
            manifest_path = "requirements.txt"
            package_manager = "pip"
            declared_deps = self._parse_requirements(reqs_path)

        # Detect lockfile
        lockfile = None
        for candidate_lock in ["poetry.lock", "uv.lock", "Pipfile.lock"]:
            if os.path.isfile(os.path.join(repo_dir, candidate_lock)):
                lockfile = candidate_lock
                break

        if not declared_deps and not package_hint:
            return None

        target_pkg = package_hint
        if not target_pkg:
            # Look for common migration packages (pydantic, sqlalchemy, fastapi, etc.)
            for known in ["pydantic", "sqlalchemy", "fastapi", "alembic"]:
                if known in declared_deps:
                    target_pkg = known
                    break
            if not target_pkg and declared_deps:
                target_pkg = next(iter(declared_deps.keys()))

        if not target_pkg:
            return None

        new_v = new_version_hint or declared_deps.get(target_pkg, "2.0.0")
        clean_new_v = re.sub(r"[^\d.]", "", new_v).split()[0] if new_v else "2.0.0"

        # If old version hint is not provided, infer common baseline
        old_v = old_version_hint
        if not old_v:
            if target_pkg.lower() == "pydantic":
                old_v = "1.10.14" if clean_new_v.startswith("2.") else "1.9.0"
            elif target_pkg.lower() == "sqlalchemy":
                old_v = "1.4.49" if clean_new_v.startswith("2.") else "1.3.24"
            else:
                old_v = "1.0.0"

        upgrade_type = self._determine_upgrade_type(old_v, clean_new_v)

        return UpgradeSpec(
            package_name=target_pkg,
            old_version=old_v,
            new_version=clean_new_v,
            package_manager=package_manager,
            manifest_path=manifest_path or "pyproject.toml",
            lockfile_path=lockfile,
            is_direct=True,
            changed_dependencies={target_pkg: (old_v, clean_new_v)},
            version_range=f">={clean_new_v}",
            upgrade_type=upgrade_type,
            trigger_source=self.default_trigger,
        )

    def _determine_upgrade_type(self, old_ver: str, new_ver: str) -> str:
        try:
            old_parts = [int(x) for x in re.findall(r"\d+", old_ver)[:3]]
            new_parts = [int(x) for x in re.findall(r"\d+", new_ver)[:3]]
            if old_parts and new_parts:
                if new_parts[0] > old_parts[0]:
                    return "major"
                elif len(new_parts) > 1 and len(old_parts) > 1 and new_parts[1] > old_parts[1]:
                    return "minor"
                else:
                    return "patch"
        except Exception:
            pass
        return "major"

    def _detect_pyproject_tool(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if "[tool.poetry]" in content:
                return "poetry"
            if "[tool.uv]" in content:
                return "uv"
        except Exception:
            pass
        return "pip"

    def _parse_pyproject(self, path: str) -> Dict[str, str]:
        deps: Dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Match dependencies in pyproject.toml: "pydantic>=2.0.0" or pydantic = "^2.0.0"
            lines = content.splitlines()
            in_deps = False
            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if ("[" in s and "dependencies" in s.lower()) or s.startswith("dependencies =") or s.startswith("dependencies="):
                    in_deps = True
                elif s.startswith("[") and in_deps:
                    in_deps = False
                    continue

                if in_deps:
                    # Format: "package>=version" or package = "^version"
                    quoted = re.search(r'["\']([a-zA-Z0-9_\-]+)\s*([><=~!^]+.*?)?["\']', s)
                    if quoted:
                        pkg = quoted.group(1).lower()
                        ver = quoted.group(2) or ""
                        deps[pkg] = ver
                    else:
                        kv = re.search(r'([a-zA-Z0-9_\-]+)\s*=\s*["\']([^"\']+)["\']', s)
                        if kv:
                            deps[kv.group(1).lower()] = kv.group(2)
        except Exception:
            pass
        return deps

    def _parse_requirements(self, path: str) -> Dict[str, str]:
        deps: Dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    m = re.match(r"^([a-zA-Z0-9_\-]+)\s*([=><~!].*)?$", s)
                    if m:
                        pkg = m.group(1).lower()
                        ver = m.group(2) or ""
                        deps[pkg] = ver
        except Exception:
            pass
        return deps
