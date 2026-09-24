"""
Isolated Local Subprocess Sandbox Driver.
Executes test commands within segregated processes with strict timeout enforcement.
"""

import sys
import time
import subprocess
from typing import List, Tuple, Optional
from patchpilot.contracts import SandboxDriver
from patchpilot.sandbox.security import SandboxSecurityPolicy, SecurityViolationError


class LocalSubprocessDriver(SandboxDriver):
    """Executes verification commands locally in isolated subprocesses with security enforcement."""

    def __init__(self, python_executable: str = sys.executable, workspace_root: Optional[str] = None):
        self.python_bin = python_executable
        self.workspace_root = workspace_root

    def get_backend_name(self) -> str:
        return "local_subprocess_isolated"

    def run_command(
        self, cmd: List[str], cwd: str, timeout_seconds: int = 30
    ) -> Tuple[int, str, float]:
        """
        Executes command with shell=False, sanitized environment, and strict wall-clock timeout.
        Returns: (exit_code, combined_output, duration_ms)
        """
        t0 = time.time()
        try:
            # Enforce security policies
            SandboxSecurityPolicy.validate_command(cmd)
            if self.workspace_root:
                SandboxSecurityPolicy.validate_filesystem_boundary(cwd, self.workspace_root)
            clean_env = SandboxSecurityPolicy.sanitize_environment()

            res = subprocess.run(
                cmd,
                cwd=cwd,
                env=clean_env,
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout_seconds,
            )
            elapsed_ms = (time.time() - t0) * 1000
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            return res.returncode, output, elapsed_ms
        except SecurityViolationError as e:
            elapsed_ms = (time.time() - t0) * 1000
            return -3, f"SECURITY_VIOLATION: {str(e)}", elapsed_ms
        except subprocess.TimeoutExpired as e:
            elapsed_ms = (time.time() - t0) * 1000
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            err = (e.stderr or "") if isinstance(e.stderr, str) else ""
            output = f"TIMEOUT: Command exceeded {timeout_seconds}s execution limit.\n{out}\n{err}"
            return -1, output, elapsed_ms
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            return -2, f"Subprocess execution error: {str(e)}", elapsed_ms
