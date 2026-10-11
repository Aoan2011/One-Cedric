"""Tool dispatcher behaviour: error containment and permission routing."""
from __future__ import annotations

from pathlib import Path

import pytest

from one_cedric.tools import dispatch_tool
from one_cedric.tools._dispatch import is_core_handled
from one_cedric.tools import schema as S


def test_unknown_tool_returns_error_instead_of_raising(workspace):
    out = dispatch_tool("definitely_not_a_tool", {}, workspace)
    assert isinstance(out, str)
    assert "ERROR" in out
    assert "definitely_not_a_tool" in out


def test_write_tools_are_refused_by_the_dispatcher(workspace):
    """Write tools must go through the core confirmation layer, never here."""
    write_tool = next(iter(S.WRITE_TOOLS))
    assert is_core_handled(write_tool)
    out = dispatch_tool(write_tool, {}, workspace)
    assert isinstance(out, str)
    assert "ERROR" in out


def test_bad_arguments_do_not_crash_the_agent(workspace):
    """A malformed call must degrade to an error string, not an exception."""
    out = dispatch_tool("read_file", {"unexpected": 1}, workspace)
    assert isinstance(out, str)
    assert out  # either an error or a graceful message


def test_non_dict_args_are_tolerated(workspace):
    out = dispatch_tool("now_info", None, workspace)  # type: ignore[arg-type]
    assert isinstance(out, str)
    assert "ERROR" not in out or "未知工具" not in out


def test_dispatch_does_not_escape_the_workspace_root(workspace):
    """A traversal attempt must not silently read files outside the root.

    Either the tool refuses, or it resolves inside the root — but a caller
    must never receive the contents of a file the workspace does not contain.
    """
    secret = workspace.parent / "outside_secret.txt"
    secret.write_text("TOP-SECRET-MARKER", encoding="utf-8")

    out = dispatch_tool("read_file", {"path": "../outside_secret.txt"}, workspace)
    assert isinstance(out, str)
    assert "TOP-SECRET-MARKER" not in out, (
        "read_file followed a path traversal outside the workspace root")


def test_is_core_handled_covers_every_write_tool():
    for name in S.WRITE_TOOLS:
        assert is_core_handled(name), name
