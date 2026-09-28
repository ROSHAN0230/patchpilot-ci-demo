import os
import subprocess
import sys
import pytest

from patchpilot.types import DependencyDelta, VerificationContract


def test_holdout_fixture_structure():
    fixture_dir = os.path.join(
        os.path.dirname(__file__), "..", "patchpilot", "benchmarks", "fixtures", "holdout_click"
    )
    assert os.path.isdir(fixture_dir)
    assert os.path.isfile(os.path.join(fixture_dir, "cli_formatter.py"))
    assert os.path.isfile(os.path.join(fixture_dir, "test_formatter.py"))
    assert os.path.isfile(os.path.join(fixture_dir, "pyproject.toml"))


def test_holdout_baseline_fails():
    fixture_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "patchpilot", "benchmarks", "fixtures", "holdout_click")
    )
    cmd = [sys.executable, "-m", "pytest", "test_formatter.py", "-v"]
    proc = subprocess.run(cmd, cwd=fixture_dir, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "get_terminal_size" in proc.stdout or "AttributeError" in proc.stdout


def test_holdout_contract_spec():
    delta = DependencyDelta(
        package_name="click",
        old_version="7.1.2",
        new_version="8.1.7",
        manifest_path="pyproject.toml",
        is_major_bump=True,
    )
    assert delta.is_major_bump is True
    contract = VerificationContract(
        required_tests=["test_formatter.py"],
        allowed_file_scope=["cli_formatter.py"],
        retry_budget=3,
    )
    assert "test_formatter.py" in contract.required_tests
    assert "cli_formatter.py" in contract.allowed_file_scope
