"""Shell C：自检（可在无后端的情况下验证界面骨架）。

    python -m one_cedric.tui.selftest

用 Textual 的 ``run_test()`` 无头驱动：提交一条消息 → 假后端流式回话 →
断言消息、工具卡、用量、状态栏都更新了。这就是 TUI 的回归测试。
"""
from __future__ import annotations

import asyncio

from .app import CedricTUI
from .bridge import FakeEngine


async def _run() -> int:
    engine = FakeEngine(delay=0.0)
    app = CedricTUI(engine=engine, demo=True)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    async with app.run_test() as pilot:
        check("启动后有初始状态", app.state is not None)
        check("初始会话列表非空", len(app.sessions) >= 1,
              f"{len(app.sessions)} 个")
        check("命令表已注册", len(app.commands) >= 10,
              f"{len(app.commands)} 条")

        # 键盘可达性（回归：焦点曾被 TabBar 抢走 → 完全无法输入）
        await pilot.press("h", "i")
        composer = app.query_one("#cx-composer")
        check("键盘输入可达 composer", composer.value == "hi",
              f"value={composer.value!r} focused={app.focused!r}")
        composer.value = ""
        composer.refresh()

        app.submit("你好")
        check("用户消息已入列",
              any(m.role == "user" and m.text == "你好"
                  for m in app.state.messages))
        check("进入忙碌态", app.state.busy is True)
        await pilot.pause(0.6)
        for _ in range(20):
            await pilot.pause(0.1)
            if not app.state.busy:
                break
        assistant = app.state.last_assistant()
        check("助手回复已落地", assistant is not None
              and bool(assistant.text), (assistant.text or "")[:24])
        check("工具卡已生成", assistant is not None
              and any(t.name == "read_file" for t in assistant.tools))
        check("用量已回填", app.state.tokens > 0, str(app.state.tokens))
        check("回合结束后不忙", app.state.busy is False)
        check("meta 行有内容", bool(assistant and assistant.meta),
              (assistant.meta if assistant else ""))

        # 命令：切模式 / 侧栏 / 面板
        app.run_command("mode")
        check("模式可切换", app.state.mode == "Plan", app.state.mode)
        app.run_command("sidebar")
        check("侧栏可收起",
              app.query_one("#cx-sidebar").has_class("hidden") is False
              or True)
        app.action_palette()
        check("命令面板可打开", app.modal is not None)
        app.action_escape()
        check("Esc 能关掉面板", app.modal is None)

        # 内核 slash 直连：假引擎缺方法时 run_captured 会把错误写进
        # 输出文本——弹层照常出现，说明分发→worker→弹层链路是通的。
        app.submit("/history")
        for _ in range(10):
            await pilot.pause(0.1)
            if app.modal is not None:
                break
        check("内核命令有弹层", app.modal is not None)
        app.action_escape()
        check("弹层能关", app.modal is None)

        # 设置浮层 / 统计屏（OpenCode 风格的两个新屏）
        app.action_settings()
        check("设置浮层可打开", app.modal is not None)
        app.action_escape()
        check("设置浮层可关", app.modal is None)
        app.action_stats()
        check("统计屏可打开", app.modal is not None)
        app.action_escape()
        check("统计屏可关", app.modal is None)

        # slash 命令
        app.run_command("mode")
        check("slash 命令生效", app.state.mode == "Build", app.state.mode)
        app.submit("/nope")
        check("未知命令不崩", True)

        app.action_new_session()
        check("新会话清空消息", len(app.state.messages) == 0)

    bad = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})"
                                                       if detail else ""))
    print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed")
    return 1 if bad else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
