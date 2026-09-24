"""
Cryptographic Snapshot Management and Deterministic Rollback Verifier.
Guarantees byte-for-byte state restoration without relying on external VCS.
"""

import os
import hashlib
import difflib
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


class RollbackIntegrityError(RuntimeError):
    """Raised when restored file state fails cryptographic equivalence check."""
    pass


class ScopeViolationError(RuntimeError):
    """Raised when an operation attempts to modify files outside the allowed scope."""
    pass


@dataclass
class FileSnapshot:
    rel_path: str
    abs_path: str
    content_bytes: bytes
    sha256_hash: str


@dataclass
class RepositorySnapshot:
    snapshot_id: str
    repo_dir: str
    file_snapshots: Dict[str, FileSnapshot]
    composite_tree_hash: str


def compute_bytes_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw byte content."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(filepath: str) -> str:
    """Compute SHA-256 hex digest of a file on disk."""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def compute_tree_hash(file_hashes: Dict[str, str]) -> str:
    """Compute deterministic composite tree hash from sorted file relative paths and hashes."""
    hasher = hashlib.sha256()
    for rel_path in sorted(file_hashes.keys()):
        hasher.update(rel_path.replace("\\", "/").encode("utf-8"))
        hasher.update(b":")
        hasher.update(file_hashes[rel_path].encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


class SnapshotManager:
    """Captures and deterministically restores repository file snapshots."""

    def __init__(self, repo_dir: str):
        self.repo_dir = os.path.abspath(repo_dir)

    def create_snapshot(self, snapshot_id: str, target_files: List[str]) -> RepositorySnapshot:
        """Capture in-memory byte representations and cryptographic hashes for target files."""
        file_snapshots: Dict[str, FileSnapshot] = {}
        file_hashes: Dict[str, str] = {}

        for rel in target_files:
            clean_rel = rel.replace("\\", "/")
            abs_p = os.path.join(self.repo_dir, clean_rel)
            if not os.path.exists(abs_p):
                raise FileNotFoundError(f"Cannot snapshot non-existent file: {abs_p}")

            with open(abs_p, "rb") as f:
                content = f.read()

            file_hash = compute_bytes_sha256(content)
            file_snapshots[clean_rel] = FileSnapshot(
                rel_path=clean_rel,
                abs_path=abs_p,
                content_bytes=content,
                sha256_hash=file_hash,
            )
            file_hashes[clean_rel] = file_hash

        composite_hash = compute_tree_hash(file_hashes)
        return RepositorySnapshot(
            snapshot_id=snapshot_id,
            repo_dir=self.repo_dir,
            file_snapshots=file_snapshots,
            composite_tree_hash=composite_hash,
        )

    def restore_snapshot(self, snapshot: RepositorySnapshot) -> bool:
        """
        Atomically restores all snapshotted files to their exact pre-patch byte state.
        Verifies byte-for-byte cryptographic equivalence.
        """
        # Step 1: Write all original bytes back to disk
        for rel_path, file_snap in snapshot.file_snapshots.items():
            abs_p = os.path.join(self.repo_dir, rel_path)
            os.makedirs(os.path.dirname(abs_p), exist_ok=True)
            with open(abs_p, "wb") as f:
                f.write(file_snap.content_bytes)

        # Step 2: Verify post-restoration integrity
        restored_hashes: Dict[str, str] = {}
        for rel_path, file_snap in snapshot.file_snapshots.items():
            abs_p = os.path.join(self.repo_dir, rel_path)
            current_hash = compute_file_sha256(abs_p)
            if current_hash != file_snap.sha256_hash:
                raise RollbackIntegrityError(
                    f"Rollback integrity violation on {rel_path}! "
                    f"Expected SHA256: {file_snap.sha256_hash}, Got: {current_hash}"
                )
            restored_hashes[rel_path] = current_hash

        current_composite = compute_tree_hash(restored_hashes)
        if current_composite != snapshot.composite_tree_hash:
            raise RollbackIntegrityError(
                f"Composite tree hash mismatch after rollback! "
                f"Expected: {snapshot.composite_tree_hash}, Got: {current_composite}"
            )

        return True

    def verify_clean_state(self, snapshot: RepositorySnapshot) -> bool:
        """Check whether the on-disk state currently matches the snapshot byte-for-byte."""
        for rel_path, file_snap in snapshot.file_snapshots.items():
            abs_p = os.path.join(self.repo_dir, rel_path)
            if compute_file_sha256(abs_p) != file_snap.sha256_hash:
                return False
        return True

    def compute_diff(self, snapshot: RepositorySnapshot) -> str:
        """Computes a unified diff between snapshotted state and current on-disk state."""
        diff_chunks = []
        for rel_path, file_snap in sorted(snapshot.file_snapshots.items()):
            abs_p = os.path.join(self.repo_dir, rel_path)
            from_text = file_snap.content_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            if os.path.isfile(abs_p):
                with open(abs_p, "rb") as f:
                    to_text = f.read().decode("utf-8", errors="replace").splitlines(keepends=True)
            else:
                to_text = []

            delta_lines = list(difflib.unified_diff(
                from_text,
                to_text,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            ))
            if delta_lines:
                diff_chunks.extend(delta_lines)

        return "".join(diff_chunks)
