"""
Cryptographic Audit Ledger Verifier for PatchPilot.
Validates immutable hash chains, genesis continuity, and root hash integrity.
"""

import os
import json
import hashlib
from typing import Dict, Any, Tuple, Optional, List
from patchpilot.types import TelemetryEvent


class AuditLedgerVerifier:
    """Verifies cryptographic integrity of a recorded run's event stream and manifest."""

    GENESIS_HASH = "0" * 64

    @classmethod
    def verify_event_stream(cls, events: List[Dict[str, Any]]) -> Tuple[bool, Optional[str], str]:
        """
        Validates hash chain across events list.
        Returns: (is_valid, error_message, final_root_hash)
        """
        if not events:
            return True, None, cls.GENESIS_HASH

        current_prev = cls.GENESIS_HASH
        for i, ev_dict in enumerate(events):
            ev = TelemetryEvent(**ev_dict)
            if ev.previous_hash != current_prev:
                return (
                    False,
                    f"Chain break at sequence {ev.sequence_number}: expected prev {current_prev}, got {ev.previous_hash}",
                    "",
                )
            expected_hash = ev.compute_hash(current_prev)
            if ev.event_hash != expected_hash:
                return (
                    False,
                    f"Hash mismatch at sequence {ev.sequence_number}: expected {expected_hash}, recorded {ev.event_hash}",
                    "",
                )
            current_prev = ev.event_hash

        return True, None, current_prev

    @classmethod
    def verify_run_bundle(cls, run_dir: str) -> Dict[str, Any]:
        """
        Performs full cryptographic audit of a run artifact bundle directory.
        """
        telemetry_file = os.path.join(run_dir, "telemetry.jsonl")
        manifest_file = os.path.join(run_dir, "audit_manifest.json")

        if not os.path.isfile(telemetry_file):
            return {
                "verified": False,
                "error": "Missing telemetry.jsonl file",
                "events_checked": 0,
                "root_hash_match": False,
            }

        events = []
        with open(telemetry_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        valid, err, computed_root = cls.verify_event_stream(events)
        if not valid:
            return {
                "verified": False,
                "error": err,
                "events_checked": len(events),
                "computed_root_hash": computed_root,
                "root_hash_match": False,
            }

        manifest_root = None
        if os.path.isfile(manifest_file):
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                manifest_root = manifest_data.get("root_hash")

        root_match = (manifest_root == computed_root) if manifest_root else True

        return {
            "verified": valid and root_match,
            "error": None if root_match else f"Root hash mismatch: manifest {manifest_root} != computed {computed_root}",
            "events_checked": len(events),
            "computed_root_hash": computed_root,
            "manifest_root_hash": manifest_root,
            "root_hash_match": root_match,
        }
