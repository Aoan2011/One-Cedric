"""Shared pytest fixtures for the One Cedric test suite.

The suite is deliberately dependency-light: it must run on a fresh checkout
with only ``pip install -r requirements-dev.txt`` plus the core runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    """Point ``Path.home()`` at a throwaway directory.

    Any code under test that reads or writes ``~/.one-cedric`` must use this
    fixture so the suite never touches the developer's real configuration,
    sessions or API keys.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture()
def workspace(tmp_path):
    """A scratch workspace directory with a few sample files."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "notes.txt").write_text(
        "hello world\nsecond line\nTHIRD line\n", encoding="utf-8")
    (ws / "data.json").write_text(
        '{"x": 1, "y": [1, 2, 3], "nested": {"k": "v"}}', encoding="utf-8")
    (ws / "rows.csv").write_text(
        "name,age\nalice,30\nbob,25\n", encoding="utf-8")
    (ws / "sub").mkdir()
    (ws / "sub" / "deep.txt").write_text("nested content\n", encoding="utf-8")
    return ws
