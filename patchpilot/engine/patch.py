"""
Scope-Enforced Patch Application and Syntax Verification Manager.
"""

import os
import ast
from typing import List, Dict
from patchpilot.types import CandidatePatch
from patchpilot.contracts import PatchManager
from patchpilot.state import ScopeViolationError


class ScopeEnforcedPatchManager(PatchManager):
    """Applies candidate modifications while strictly preventing out-of-scope edits."""

    def apply_candidate(
        self, repo_dir: str, candidate: CandidatePatch, allowed_scope: List[str]
    ) -> bool:
        norm_scope = {os.path.normpath(os.path.join(repo_dir, f)) for f in allowed_scope}

        # Step 1: Pre-validation of all files against allowed scope
        for rel_path, code in candidate.code_replacements.items():
            full_path = os.path.normpath(os.path.join(repo_dir, rel_path))
            if norm_scope and full_path not in norm_scope:
                raise ScopeViolationError(
                    f"Candidate {candidate.candidate_id} attempted to edit out-of-scope file: {rel_path}. "
                    f"Allowed scope: {allowed_scope}"
                )

            # Step 2: Validate Python syntax via ast.parse before touching disk
            try:
                ast.parse(code, filename=rel_path)
            except SyntaxError as e:
                raise ValueError(
                    f"Candidate {candidate.candidate_id} produced invalid Python syntax in {rel_path}: {e}"
                )

        # Step 3: Write validated code to disk atomically
        for rel_path, code in candidate.code_replacements.items():
            full_path = os.path.normpath(os.path.join(repo_dir, rel_path))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(code)

        return True
