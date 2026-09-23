"""
Comprehensive Test Suite for Cryptographic Snapshot & Rollback Mechanics.
Verifies byte-for-byte restoration, repeated rollbacks, and scope bounds.
"""

import os
import shutil
import tempfile
import pytest
from patchpilot.state import (
    SnapshotManager,
    RollbackIntegrityError,
    compute_file_sha256,
    compute_tree_hash,
)
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.types import CandidatePatch
from patchpilot.state import ScopeViolationError


@pytest.fixture
def temp_repo():
    temp_dir = tempfile.mkdtemp(prefix="pp_test_repo_")
    # Create sample files
    f1 = os.path.join(temp_dir, "models", "schema.py")
    f2 = os.path.join(temp_dir, "services", "svc.py")
    os.makedirs(os.path.dirname(f1), exist_ok=True)
    os.makedirs(os.path.dirname(f2), exist_ok=True)

    with open(f1, "w", encoding="utf-8") as f:
        f.write("# Schema v1\nclass User:\n    id: int\n")

    with open(f2, "w", encoding="utf-8") as f:
        f.write("# Service v1\ndef get_user():\n    return 'user'\n")

    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_snapshot_creation_and_clean_check(temp_repo):
    mgr = SnapshotManager(temp_repo)
    target_files = ["models/schema.py", "services/svc.py"]
    snap = mgr.create_snapshot("snap1", target_files)

    assert snap.snapshot_id == "snap1"
    assert len(snap.file_snapshots) == 2
    assert mgr.verify_clean_state(snap) is True


def test_atomic_rollback_integrity(temp_repo):
    mgr = SnapshotManager(temp_repo)
    target_files = ["models/schema.py", "services/svc.py"]
    snap = mgr.create_snapshot("snap_orig", target_files)

    initial_schema_hash = snap.file_snapshots["models/schema.py"].sha256_hash
    schema_abs = os.path.join(temp_repo, "models", "schema.py")

    # Corrupt/modify file
    with open(schema_abs, "w", encoding="utf-8") as f:
        f.write("# Corrupted bad patch\nraise RuntimeError('Syntax broken!')\n")

    assert compute_file_sha256(schema_abs) != initial_schema_hash
    assert mgr.verify_clean_state(snap) is False

    # Execute rollback
    restored = mgr.restore_snapshot(snap)
    assert restored is True

    # Assert byte-for-byte equivalence
    current_hash = compute_file_sha256(schema_abs)
    assert current_hash == initial_schema_hash
    assert mgr.verify_clean_state(snap) is True


def test_repeated_rollbacks(temp_repo):
    mgr = SnapshotManager(temp_repo)
    target_files = ["models/schema.py"]
    snap = mgr.create_snapshot("snap_repeat", target_files)
    schema_abs = os.path.join(temp_repo, "models", "schema.py")
    initial_hash = snap.file_snapshots["models/schema.py"].sha256_hash

    for cycle in range(5):
        # Modify file
        with open(schema_abs, "w", encoding="utf-8") as f:
            f.write(f"# Bad iteration {cycle}\nx = {cycle}\n")
        assert compute_file_sha256(schema_abs) != initial_hash

        # Revert
        mgr.restore_snapshot(snap)
        assert compute_file_sha256(schema_abs) == initial_hash


def test_scope_enforcement_blocks_out_of_scope_edit(temp_repo):
    patch_mgr = ScopeEnforcedPatchManager()
    allowed_scope = ["models/schema.py"]

    # Candidate attempts to edit services/svc.py which is out of allowed scope
    bad_cand = CandidatePatch(
        candidate_id="cand_rogue",
        iteration=1,
        hypothesis="Rogue edit",
        target_files=["services/svc.py"],
        code_replacements={"services/svc.py": "# Unauthorized edit\n"},
    )

    with pytest.raises(ScopeViolationError):
        patch_mgr.apply_candidate(temp_repo, bad_cand, allowed_scope)


def test_scope_enforcement_catches_syntax_error(temp_repo):
    patch_mgr = ScopeEnforcedPatchManager()
    allowed_scope = ["models/schema.py"]

    broken_cand = CandidatePatch(
        candidate_id="cand_syntax_error",
        iteration=1,
        hypothesis="Syntax error candidate",
        target_files=["models/schema.py"],
        code_replacements={"models/schema.py": "def invalid syntax {{{("},
    )

    with pytest.raises(ValueError, match="invalid Python syntax"):
        patch_mgr.apply_candidate(temp_repo, broken_cand, allowed_scope)
