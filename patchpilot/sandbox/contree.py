"""
Nebius Token Factory ConTree Cloud Sandbox Driver.
Strictly adheres to truthful status reporting without simulating cloud execution.
"""

import requests
from typing import List, Tuple, Optional
from patchpilot.contracts import SandboxDriver


class ConTreeAccessGatedError(RuntimeError):
    """Raised when attempting cloud sandbox execution on an account where spawn=False."""
    pass


class ConTreeCloudDriver(SandboxDriver):
    """Interfaces with Nebius Token Factory Cloud Sandboxes API."""

    def __init__(self, api_key: str, base_url: str = "https://api.tokenfactory.nebius.com/sandboxes/v1"):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.authenticated = False
        self.spawn_allowed = False
        self.tenant_id: Optional[str] = None

    def get_backend_name(self) -> str:
        return "nebius_contree_microvm"

    def check_access(self) -> dict:
        """Query whoami endpoint to verify live authentication and spawn permissions."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.get(f"{self.base_url}/whoami", headers=headers, timeout=10)
        if resp.status_code != 200:
            raise RuntimeError(f"ConTree authentication failed: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        self.authenticated = True
        self.spawn_allowed = bool(data.get("spawn", False))
        self.tenant_id = data.get("tenant_id")
        return data

    def run_command(
        self, cmd: List[str], cwd: str, timeout_seconds: int = 30
    ) -> Tuple[int, str, float]:
        """
        Executes inside a ConTree cloud sandbox.
        STRICT RULE: Never simulate execution if spawn=False.
        """
        if not self.spawn_allowed:
            raise ConTreeAccessGatedError(
                f"Cannot execute in ConTree Cloud Sandbox: Tenant '{self.tenant_id}' has spawn=False. "
                "Cloud sandboxes are in private beta and require entitlement enablement from Nebius."
            )
        raise NotImplementedError("Cloud execution pathway active once tenant spawn permissions are enabled.")
