import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from cli_formatter import format_banner, format_status


def test_format_banner():
    banner = format_banner("PATCHPILOT")
    assert "PATCHPILOT" in banner
    assert len(banner) >= len("PATCHPILOT")


def test_format_status():
    status_box = format_status("RECOVERED")
    assert "STATUS: RECOVERED" in status_box
    assert "===" in status_box
