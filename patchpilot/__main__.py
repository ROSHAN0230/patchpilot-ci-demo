"""
PatchPilot Package Entry Point.
Allows running `python -m patchpilot <command>` directly.
"""

import sys
from patchpilot.cli import main

if __name__ == "__main__":
    sys.exit(main())
