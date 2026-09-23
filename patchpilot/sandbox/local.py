"""
Isolated Local Subprocess Sandbox Driver.
Executes test commands within segregated processes with strict timeout enforcement.
"""

import sys
import time
import subprocess
from typing import List, Tuple
from patchpilot.contracts import SandboxDriver


class LocalSubprocessDriver(SandboxDriver):
    """Executes verification commands locally in isolated subprocesses."""

    def __init__(self, python_executable: str = sys.executable):
        self.python_bin = python_executable

    def get_backend_name(self) -> str:
        return "local_subprocess_isolated"

    def run_command(
        self, cmd: List[str], cwd: str, timeout_seconds: int = 30
    ) -> Tuple[int, str, float]:
        """
        Executes command with shell=False and strict wall-clock timeout.
        Returns: (exit_code, combined_output, duration_ms)
        """
        t0 = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout_seconds,
            )
            elapsed_ms = (time.time() - t0) * 1000
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            return res.returncode, output, elapsed_ms
        except subprocess.TimeoutExpired as e:
            elapsed_ms = (time.time() - t0) * 1000
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            err = (e.stderr or "") if isinstance(e.stderr, str) else ""
            output = f"TIMEOUT: Command exceeded {timeout_seconds}s execution limit.\n{out}\n{err}"
            return -1, output, elapsed_ms
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            return -2, f"Subprocess execution error: {str(e)}", elapsed_ms
