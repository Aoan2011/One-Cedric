"""kernel_cmds（TUI → 内核直连层）的回归测试。

不需要真内核：

* parity —— 从 ``core.py`` 源码里提取 REPL 实际暴露的 ``/`` 命令名，
  断言它们全部由 ``kernel_cmds.SLASH`` 直连或由 ``SLASH_ALIASES`` 接住
  （CLI 加命令、TUI 没跟上时这条先红）；
* dispatch —— 各类指令形状（modal / notify / confirm / send）与
  ``busy_safe`` 标记；
* run_captured —— Console 换进换出、异常降级为文本。
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

from one_cedric.tui import kernel_cmds
from one_cedric.tui.commands import ALIASES, SLASH_ALIASES  # noqa: F401


class _Stub:
    """带真实 Console 的假内核（只够 run_captured 用）。"""

    def __init__(self):
        from rich.console import Console
        self.console = Console(file=io.StringIO(), width=80)


# ------------------------------------------------------------- parity #
def _cli_slash_names() -> set[str]:
    """扫 core.py 提取 REPL 的 ``startswith("/…")`` / ``== "/…"`` 命令名。"""
    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "one_cedric" / "core.py").read_text(encoding="utf-8")
    names = set(re.findall(r'line\.startswith\((?:f)?["\'](/[a-z0-9-]+)', src))
    names |= set(re.findall(r'line\s*==\s*["\'](/[a-z0-9-]+)["\']', src))
    return {n.lstrip("/") for n in names}


def test_every_cli_slash_is_handled_by_tui():
    missing = sorted(
        n for n in _cli_slash_names()
        if n not in kernel_cmds.SLASH and f"/{n}" not in SLASH_ALIASES)
    assert not missing, (
        f"CLI 有但这些命令 TUI 没接住: {missing}；"
        f"要么加进 kernel_cmds.SLASH，要么加进 SLASH_ALIASES")


def test_slash_aliases_are_wellformed():
    for key, target in SLASH_ALIASES.items():
        assert key.startswith("/"), key
        assert isinstance(target, str) and target, key


# ----------------------------------------------------------- dispatch #
@pytest.mark.parametrize("line,kind", [
    ("/cost", "modal"),
    ("/pricing", "modal"),
    ("/history", "modal"),
    ("/compact", "modal"),
    ("/models", "notify"),
    ("/model gpt-x", "modal"),
    ("/compact x", "notify"),
    ("/mem clear", "confirm"),
    ("/asks clear", "confirm"),
    ("/upload", "notify"),
    ("/zzz-unknown", "notify"),
])
def test_dispatch_kind(line, kind):
    assert kernel_cmds.dispatch(None, line)["kind"] == kind


def test_dispatch_busy_safe_flags():
    # 只读报表流式中也允许跑；改状态 / 长调用一律拒绝
    assert kernel_cmds.dispatch(None, "/cost")["busy_safe"] is True
    assert kernel_cmds.dispatch(None, "/history")["busy_safe"] is True
    assert kernel_cmds.dispatch(None, "/compact")["busy_safe"] is False
    assert kernel_cmds.dispatch(None, "/model gpt-x")["busy_safe"] is False


def test_dispatch_non_slash_is_send():
    res = kernel_cmds.dispatch(None, "hello world")
    assert res["kind"] == "send" and res["text"] == "hello world"


def test_upload_builds_send_with_file_content(tmp_path):
    target = tmp_path / "a.py"
    target.write_text("print(42)\n", encoding="utf-8")

    class _Engine:
        class copilot:                       # noqa: N801 仅占位
            root = str(tmp_path)

    res = kernel_cmds.dispatch(_Engine, f"/upload {target.name}")
    assert res["kind"] == "send"
    assert "print(42)" in res["text"]


def test_upload_missing_path_is_notify():
    class _Engine:
        class copilot:                       # noqa: N801
            root = "."

    res = kernel_cmds.dispatch(_Engine, "/upload not-exist-xyz.bin")
    assert res["kind"] == "notify"


# -------------------------------------------------------- run_captured #
def test_run_captured_swaps_and_restores_console():
    stub = _Stub()
    original = stub.console

    def fn(cp):
        cp.console.print("[ok]hello[/]")

    out = kernel_cmds.run_captured(stub, fn)
    assert "hello" in out
    assert stub.console is original          # 跑完必须换回去


def test_run_captured_reports_exceptions_as_text():
    stub = _Stub()

    def fn(cp):
        raise RuntimeError("boom")

    out = kernel_cmds.run_captured(stub, fn)
    assert "boom" in out


def test_expand_at_without_reference_is_identity():
    text, notes = kernel_cmds.expand_at(None, "plain text")
    assert text == "plain text" and notes == []
