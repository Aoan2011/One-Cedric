"""REPL 输入框的生命周期：程序化回合与离开对话时都必须把它收起来。

两个回归场景：

* 网关线程跑 ``ask_no_ui`` → ``agent_turn`` 时会顺着 ``self.repl_ui``
  一路调 ``poll_during_turn()``，和 REPL 主线程抢 ``msvcrt.getwch``，
  把正在生成的 WebUI 流卡死到用户下一次按键 —— 回合内必须把
  ``repl_ui`` 摘掉，回合结束（含异常）再装回。
* ``run()`` 返回（``/menu``、``/exit``）时从不收拾常驻输入框，它的
  Rich ``Live`` 还在画 —— 主菜单底部就一直挂着一个对话输入框。
"""
from __future__ import annotations

import io

import pytest


def test_ask_no_ui_detaches_repl_ui_for_the_turn():
    from rich.console import Console

    from one_cedric.core import OneCedric

    class Shell(OneCedric):
        """不跑 __init__ 的壳：ask_no_ui 只碰下面这几个属性。"""

        def __init__(self):
            self.console = Console(file=io.StringIO(), force_terminal=False)
            self.auto_yes = False
            self._ask_write_action = None
            self._ask_shell_action = None
            self._log_tool = None
            self._stream_hook = None
            self.repl_ui = object()          # 模拟「REPL 正在运行」
            self.during_turn = "unset"

        def agent_turn(self, prompt):
            self.during_turn = self.repl_ui
            return "ok"

    shell = Shell()
    sentinel = shell.repl_ui

    result = shell.ask_no_ui("hi")

    assert result["answer"] == "ok"
    assert shell.during_turn is None     # 回合内看不见输入框
    assert shell.repl_ui is sentinel     # 回合结束后原样装回
    assert shell.auto_yes is False       # 其余状态同样复原


def test_ask_no_ui_restores_repl_ui_after_errors():
    from rich.console import Console

    from one_cedric.core import OneCedric

    class Shell(OneCedric):
        def __init__(self):
            self.console = Console(file=io.StringIO(), force_terminal=False)
            self.auto_yes = False
            self._ask_write_action = None
            self._ask_shell_action = None
            self._log_tool = None
            self._stream_hook = None
            self.repl_ui = object()
            self.during_turn = "unset"

        def agent_turn(self, prompt):
            self.during_turn = self.repl_ui
            raise RuntimeError("boom")

    shell = Shell()
    sentinel = shell.repl_ui

    result = shell.ask_no_ui("hi")

    assert result["answer"].startswith("ERROR")
    assert shell.during_turn is None
    assert shell.repl_ui is sentinel


@pytest.mark.parametrize("exit_kind", ["return", "menu", "error"])
def test_run_tears_down_repl_ui_on_exit(exit_kind):
    """互动会话结束（正常返回 / SystemExit / 异常）都要停掉输入框。"""
    from one_cedric.core import OneCedric

    class Shell(OneCedric):
        """不跑 __init__ 的壳：只验证 run() 的输入框生命周期。"""

        def __init__(self):
            self.repl_ui = None
            self.stops: list[str] = []

        def banner(self):
            pass

        def _init_repl_ui(self):
            stops = self.stops

            class _UI:
                def stop(self):
                    stops.append("stop")

            self.repl_ui = _UI()

        def _run_repl_loop(self, in_menu=False):
            assert self.repl_ui is not None
            if exit_kind == "return":
                return
            if exit_kind == "menu":
                raise SystemExit           # /menu、/exit 走 SystemExit
            raise RuntimeError("boom")

    shell = Shell()
    if exit_kind == "return":
        shell.run(in_menu=True)
    else:
        with pytest.raises((SystemExit, RuntimeError)):
            shell.run(in_menu=True)

    assert shell.repl_ui is None           # 已摘除
    assert shell.stops == ["stop"]         # Live 已停


def test_teardown_repl_ui_is_resilient():
    """stop() 炸了（终端已消失等）不能把菜单流程带崩，且照常摘除。"""
    from one_cedric.core import OneCedric

    class Shell(OneCedric):
        def __init__(self):
            self.repl_ui = None

    class _BadUI:
        def stop(self):
            raise RuntimeError("terminal already gone")

    shell = Shell()
    shell.repl_ui = _BadUI()
    shell._teardown_repl_ui()              # 不该抛
    assert shell.repl_ui is None

    shell._teardown_repl_ui()              # 本来就是 None 也不抛
    assert shell.repl_ui is None
