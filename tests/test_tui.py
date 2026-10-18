"""Shell C（Textual TUI）的回归测试。

跑法：``python -m pytest tests/test_tui.py -q``

不需要真后端：用 ``FakeEngine`` 驱动，覆盖布局装配、流式消息、工具卡、
用量回填、命令表、slash 命令与弹层开合。

异步用例一律走 ``asyncio.run`` —— 项目里没装 pytest-asyncio，不为一个
模块改全局测试基建。
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

pytest.importorskip("textual")

from one_cedric.tui.app import CedricTUI                      # noqa: E402
from one_cedric.tui.bridge import Engine, FakeEngine          # noqa: E402


def run(coro):
    return asyncio.run(coro)


def test_engine_falls_back_to_lazy_core():
    """不给 copilot 时不该在构造阶段就 import core（TUI 启动要快）。"""
    eng = Engine()
    assert eng._copilot is None


def test_engine_wraps_given_copilot():
    sentinel = object()
    eng = Engine(copilot=sentinel)
    assert eng.copilot is sentinel


def test_boots_with_session_list_and_commands():
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            for wid in ("#cx-sidebar", "#cx-transcript", "#cx-context",
                        "#cx-composer", "#cx-statusbar", "#cx-topbar",
                        "#getting-started"):
                assert app.query_one(wid) is not None
            assert len(app.commands) >= 10
            assert app.sessions
    run(main())


def test_boot_focuses_composer_and_types():
    """启动焦点必须在 composer 且能敲进字。

    回归背景：composer 漏掉 ``can_focus`` 时焦点落到 TabBar，键盘全部
    被吞 —— 表现为完全无法输入。
    """
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            assert app.focused is not None
            assert app.focused.id == "cx-composer"
            await pilot.press("h", "i")
            await pilot.pause(0.05)
            assert app.query_one("#cx-composer").value == "hi"
            await pilot.press("enter")           # Enter 提交走完整链路
            await pilot.pause(0.1)
            assert any(m.role == "user" and m.text == "hi"
                       for m in app.state.messages)
    run(main())


def test_streaming_turn_fills_transcript_and_usage():
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test() as pilot:
            app.submit("你好")
            assert any(m.role == "user" and m.text == "你好"
                       for m in app.state.messages)
            assert app.state.busy is True
            for _ in range(60):
                await pilot.pause(0.05)
                if not app.state.busy:
                    break
            last = app.state.last_assistant()
            assert last is not None and last.text
            assert last.done is True
            assert any(t.name == "read_file" for t in last.tools)
            assert app.state.tokens == 6369
            assert app.state.busy is False
            assert last.meta
            # OpenCode 风格的元信息行：Build · model · <s> · <tok/s> tok/s
            assert "tok/s" in last.meta and "Build" in last.meta
    run(main())


def test_commands_and_slash():
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test() as pilot:
            # Build/Plan 翻转走面板命令（shift+tab 同一入口）
            app.run_command("mode")
            assert app.state.mode == "Plan"
            app.run_command("mode")
            assert app.state.mode == "Build"
            # CLI 参数型命令由 kernel_cmds 直连：裸 /mode = 访问模式报告
            # （与 CLI 语义一致），不再做 Build/Plan 翻转
            app.submit("/mode")
            for _ in range(10):
                await pilot.pause(0.05)
                if app.modal is not None:
                    break
            assert app.modal is not None
            app.action_escape()
            assert app.modal is None
            app.submit("/nope")            # 未知命令只提示，不抛
            app.action_palette()
            assert app.modal is not None
            app.action_escape()
            assert app.modal is None
    run(main())


def test_settings_panel_cycles_values():
    """设置浮层：←/→ 改值（Theme 行切 light-mode），esc 关闭。"""
    from one_cedric.tui.widgets.settings import SettingsPanel

    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test() as pilot:
            app.action_settings()
            assert app.modal is not None
            panel = app.query_one(SettingsPanel)
            assert panel.rows
            # 第一行是 Theme（dark），右方向键切到 light
            assert not app.screen.has_class("light-mode")
            await pilot.press("right")
            await pilot.pause(0.05)
            assert app.screen.has_class("light-mode")
            # 左方向键切回 dark
            await pilot.press("left")
            await pilot.pause(0.05)
            assert not app.screen.has_class("light-mode")
            # 输入即筛选
            await pilot.press("s")
            await pilot.pause(0.05)
            assert panel.query == "s"
            app.action_escape()
            assert app.modal is None
    run(main())


def test_stats_screen_opens_and_renders():
    """统计屏：可打开、render 有内容、esc 关闭。"""
    from one_cedric.tui.widgets.stats import StatsScreen, human_tokens

    assert human_tokens(6369) == "6.4K"
    assert human_tokens(60_800_000) == "60.8M"
    assert human_tokens(512) == "512"

    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            app.action_stats()
            assert app.modal is not None
            screen = app.query_one(StatsScreen)
            text = screen.render()
            assert text.plain.strip()
            assert "one-cedric / stats" in text.plain
            app.action_escape()
            assert app.modal is None
    run(main())


def test_palette_contains_required_commands():
    """OpenCode 对齐：面板必须包含这十个命令。"""
    required = {"new session", "switch model", "toggle theme", "help",
                "exit", "sessions", "compact", "undo", "settings", "stats"}
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            names = {c for c, _d, _f in app.commands}
            assert required <= names
    run(main())


def test_home_then_session_view():
    """首页（logo）→ 发送第一条消息 → 切到三栏会话视图。"""
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test() as pilot:
            assert app.screen.has_class("home")
            assert not app.screen.has_class("session")
            app.submit("你好")
            assert app.screen.has_class("session")
            assert not app.screen.has_class("home")
            await pilot.pause(1.5)
            assert app.state.messages
            # 回到新会话应回到首页
            app.action_new_session()
            await pilot.pause(0.05)
            assert app.screen.has_class("home")
    run(main())


def test_new_session_resets_messages():
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            app.state.add_user("旧消息")
            assert app.state.messages
            app.action_new_session()
            assert app.state.messages == []
    run(main())


def test_compact_and_undo():
    async def main():
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            for i in range(8):
                app.state.add_user(f"m{i}")
                app.state.begin_assistant()
                app.state.streaming.reasoning = "thinking"
                app.state.finish_assistant(meta="Build · x · 1.0s")
                app.state.streaming = None
            # undo：最后一轮连 user 带回复消失
            before = len(app.state.messages)
            assert app.state.undo_last_exchange()
            assert len(app.state.messages) == before - 2
            # compact：推理清空、只留最近 4 轮
            app.state.compact(keep_turns=4)
            assert len(app.state.messages) == 8
            assert all(not m.reasoning for m in app.state.messages)
    run(main())


def test_stop_is_cooperative_when_idle():
    """空闲时按 Esc/停止不该报错（引擎没有可中断的回合）。"""
    app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
    app.engine.stop()
    app.action_stop()


def test_cell_width_handles_cjk():
    """中文对齐是终端 UI 最容易翻车的地方，单独测。"""
    from one_cedric.tui.design import cell_width, pad, truncate
    assert cell_width("中文") == 4
    assert cell_width("ab") == 2
    assert cell_width(truncate("中文标题很长很长", 8)) <= 8
    assert cell_width(pad("中文", 8)) == 8


def test_css_is_ascii_only():
    """Textual 0.43 在 Windows 用 cp936 读样式表，非 ASCII 会直接崩。

    遍历 one_cedric/tui/ 下所有 .tcss/.css 文件，外加内联的 app_css.CSS。
    """
    tui_dir = pathlib.Path(__file__).resolve().parents[1] / "one_cedric" / "tui"
    styles = sorted(tui_dir.rglob("*.tcss")) + sorted(tui_dir.rglob("*.css"))
    assert styles, "expected at least one stylesheet under one_cedric/tui/"
    for path in styles:
        assert path.read_bytes().isascii(), f"non-ASCII in {path}"
    from one_cedric.tui.app_css import CSS
    assert CSS.isascii()
    assert "Screen" in CSS


def test_theme_colors_defined():
    """配色单一来源：theme.COLORS 里的关键 token 必须齐。"""
    from one_cedric.tui.theme import COLORS, VERSION
    for key in ("bg", "bg-elev", "border", "text", "text-dim", "accent",
                "danger", "ok"):
        assert key in COLORS
        assert COLORS[key].startswith("#")
    # 版本号来自包元数据，不是硬编码字符串
    assert isinstance(VERSION, str) and VERSION


def test_theme_colors_match_css_variables():
    """CSS 里的 $变量 与 theme.COLORS 是同一套值，防止两边漂移。"""
    from one_cedric.tui.app_css import CSS
    from one_cedric.tui.theme import COLORS
    keys = {"bg": "$bg:", "bg-elev": "$bg-elev:", "border": "$border:",
            "text": "$text:", "text-dim": "$text-dim:", "accent": "$accent:"}
    for key, varname in keys.items():
        for line in CSS.splitlines():
            if line.strip().startswith(varname) and ":" in line:
                value = line.split(":", 1)[1].strip().rstrip(";").strip()
                assert value.lower() == COLORS[key], \
                    f"{varname} = {value}, theme.COLORS['{key}'] = {COLORS[key]}"
                break
        else:
            pytest.fail(f"variable {varname} missing in CSS")


def test_tui_does_not_import_core():
    """TUI 在 run_test() 下不能把 one_cedric.core 拉起来（保持惰性）。"""
    async def main():
        before = set(sys.modules)
        app = CedricTUI(engine=FakeEngine(delay=0.0), demo=True)
        async with app.run_test():
            assert "one_cedric.core" not in (set(sys.modules) - before)
    run(main())
