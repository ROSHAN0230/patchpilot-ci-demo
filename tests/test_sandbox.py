"""
Test Suite for Sandbox Drivers: Local Subprocess & ConTree Gating.
"""

import sys
import pytest
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.sandbox.contree import ConTreeCloudDriver, ConTreeAccessGatedError


def test_local_subprocess_execution():
    driver = LocalSubprocessDriver()
    assert driver.get_backend_name() == "local_subprocess_isolated"

    # Run quick echo/python print
    cmd = [sys.executable, "-c", "print('hello_sandbox')"]
    rc, out, elapsed = driver.run_command(cmd, cwd=".", timeout_seconds=5)

    assert rc == 0
    assert "hello_sandbox" in out
    assert elapsed > 0


def test_local_subprocess_timeout_enforcement():
    driver = LocalSubprocessDriver()
    # Execute a command that sleeps for 3 seconds with a 1 second timeout
    cmd = [sys.executable, "-c", "import time; time.sleep(3)"]
    rc, out, elapsed = driver.run_command(cmd, cwd=".", timeout_seconds=1)

    assert rc == -1
    assert "TIMEOUT" in out
    assert elapsed >= 1000  # at least 1s


def test_contree_driver_truthful_gating():
    driver = ConTreeCloudDriver(api_key="mock_key")
    assert driver.get_backend_name() == "nebius_contree_microvm"
    assert driver.spawn_allowed is False

    with pytest.raises(ConTreeAccessGatedError, match="spawn=False"):
        driver.run_command(["pytest"], cwd=".")
