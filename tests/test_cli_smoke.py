"""CLI surface smoke tests — run the real entry point in a subprocess."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.smoke


def _run(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "one_cedric", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def test_version_flag_exits_zero_and_prints_version():
    from one_cedric._version import __version__

    proc = _run("--version")
    assert proc.returncode == 0, proc.stderr
    assert __version__ in proc.stdout
    assert "One Cedric" in proc.stdout
    assert "GPL-3.0" in proc.stdout


def test_license_flag_prints_gpl_notice():
    proc = _run("--license")
    assert proc.returncode == 0, proc.stderr
    assert "GNU General Public License" in proc.stdout


def test_help_flag_lists_documented_options():
    proc = _run("--help")
    assert proc.returncode == 0, proc.stderr
    for flag in ("--chat", "--gateway", "--token", "--version",
                 "--sandbox-terminal", "--no-sandbox-terminal"):
        assert flag in proc.stdout, f"{flag} missing from --help"


def test_unknown_flag_fails_cleanly():
    proc = _run("--definitely-not-a-flag")
    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr
