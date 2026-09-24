#!/usr/bin/env python3
"""
PatchPilot Quickstart & Canonical Live Demo.
Executes the canonical recovery loop:
RED -> INVESTIGATE -> TRY -> FAIL -> RECOVER -> GREEN
"""

import sys
from patchpilot.demo.canonical import run_canonical_demo

if __name__ == "__main__":
    result = run_canonical_demo()
    if result.get("status") == "verified_green":
        sys.exit(0)
    else:
        sys.exit(1)
