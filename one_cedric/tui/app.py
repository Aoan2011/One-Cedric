"""Shell C：OpenCode 对齐版 TUI 主应用。

逐屏还原 OpenCode（sst/opencode v2.0.x）的终端界面：

* 首页 —— 巨型点阵 logo + 有边框 composer + 底部快捷键/版本；
* 会话中 —— 三栏（会话列表 | 对话流 | Context 面板）+ 顶部标签条 + 状态栏；
* ctrl+p 命令面板 —— 居中浮层，左名右描述；
* 思考/工具默认折叠，Esc 逐层关闭浮层。

流式输出：事件从 worker 线程经 ``post_message`` 进 UI 线程，绘制只更新
自绘 Static 的文本块（不整屏重排），不会每 token 卡 UI。
"""
from __future__ import annotations

import time

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from . import commands as cmd_mod
from . import kernel_cmds
from .app_css import CSS
from .bridge import Engine
from .commands import SLASH_ALIASES, build_commands
from .design import cell_width
from .events import (Chunk, Finished, KernelOutput, Reasoning, ToolEnd,
                     ToolStart, Usage, map_event)
from .state import SessionState, ToolRun
from .theme import COLORS, VERSION
from .widgets.composer import Composer
from .widgets.context_panel import ContextPanel
from .widgets.getting_started import GettingStartedCard
from .widgets.home import HomePanel
from .widgets.palette import CommandPalette
from .widgets.session_list import SessionList
from .widgets.settings import SettingsPanel
from .widgets.stats import StatsScreen
from .widgets.tabbar import TabBar
from .widgets.transcript import Transcript
from ..ui import icons

MODES = ("Build", "Plan")


class CedricTUI(App):
    """四界面之一的终端外壳。"""

    #: 启动后键盘焦点直接给 composer（否则会被 TabBar 抢走，表现为「无法输入」）。
    AUTO_FOCUS = "#cx-composer"

    CSS = CSS
    TITLE = "One Cedric TUI"
    BINDINGS = [
        ("ctrl+p", "palette", "commands"),
        ("ctrl+k", "focus_sessions", "search sessions"),
        ("shift+tab", "cycle_mode", "mode"),
        ("escape", "escape", "back/stop"),
        ("ctrl+q", "quit", "exit"),
        ("ctrl+b", "toggle_sidebar", "sidebar"),
        ("ctrl+n", "new_session", "new session"),
        ("ctrl+s", "stats", "stats"),
    ]

    def __init__(self, engine: Engine | None = None, demo: bool = False):
        super().__init__()
        self.engine = engine or Engine()
        self.state = SessionState()
        self.demo = demo
        self.sessions: list[dict] = []
        self.tabs: list[dict] = []
        self.tab_index = 0
        self.commands: list[tuple[str, str, object]] = []
        self.modal: Widget | None = None      # 命令面板/帮助/统计浮层容器
        self.gs_dismissed = False             # Getting started 卡已关闭
        self._reasoning_started: float | None = None

    # ------------------------------------------------------------ 组装 #
    def compose(self) -> ComposeResult:
        yield TabBar(id="cx-topbar")
        with Horizontal(id="cx-body"):
            yield SessionList(id="cx-sidebar")
            with Vertical(id="cx-middle"):
                yield HomePanel(id="cx-home")
                yield Transcript(self.state, id="cx-transcript")
                yield Composer(id="cx-composer")
            with Vertical(id="cx-right"):
                yield ContextPanel(self.state, id="cx-context")
                yield GettingStartedCard(id="getting-started")
        yield Static("", id="cx-statusbar")

    def on_mount(self) -> None:
        # Nerd Font 开关：环境变量 > config.toml [ui].nerd_font > 默认开启
        try:
            icons.configure_from_config()
        except Exception:
            pass
        self.commands = [(c, d, f) for c, d, f in build_commands(self)]
        info = self.engine.info()
        self.state.model = info.get("model") or "demo-model"
        self.state.host = info.get("host") or "localhost"
        self.state.title = info.get("session_title") or ""
        self.state.think = info.get("think_level") or self.state.think
        self._reload_sessions()
        self.query_one(Composer).set_meta(
            self.state.mode, self.state.model, self.state.host,
            self.state.think)
        self.query_one(Transcript).refresh_content()
        self.query_one(ContextPanel).refresh_panel()
        self._sync_view_mode()
        self._paint_statusbar()
        self.query_one(Composer).focus()
        self._check_narrow(self.size.width)

    def on_resize(self, event) -> None:
        self._check_narrow(self.size.width)
        self._refresh_all()

    def _check_narrow(self, width: int) -> None:
        """窄屏逐级收起：Context 面板在一个阈值，侧栏在更窄的阈值。

        （Textual 0.43 的 ``toggle_class`` 只接受一个类名，不带开关参数。）
        """
        if not width:
            return
        if width < 100:
            self.screen.add_class("narrow")
        else:
            self.screen.remove_class("narrow")
        if width < 60:
            self.screen.add_class("narrower")
        else:
            self.screen.remove_class("narrower")

    # ------------------------------------------------------------ 视图 #
    def _sync_view_mode(self) -> None:
        """messages 为空 → 首页（logo），有对话 → 三栏会话视图。"""
        screen = self.screen
        if self.state.messages:
            screen.remove_class("home")
            screen.add_class("session")
        else:
            screen.remove_class("session")
            screen.add_class("home")

    def _reload_sessions(self) -> None:
        try:
            from ..storage import list_session_files
            self.sessions = list_session_files()
        except Exception:
            self.sessions = []
        if not self.sessions:
            self.sessions = [{"id": "demo", "title": "demo session",
                              "count": 3, "updated": time.time()}]
        self.query_one(SessionList).set_sessions(self.sessions)
        if not self.tabs:
            current = {"id": self.engine.info().get("session_id") or "current",
                       "title": self.state.title or ""}
            self.tabs = [current] + [dict(s) for s in self.sessions[:3]]
        self.query_one(TabBar).set_tabs(self.tabs, self.tab_index)

    # ------------------------------------------------------------ 绘制 #
    def _refresh_all(self) -> None:
        self.query_one(TabBar).set_tabs(self.tabs, self.tab_index)
        self.query_one(Transcript).refresh_content()
        self.query_one(ContextPanel).refresh_panel()
        self._paint_statusbar()

    def _paint_statusbar(self) -> None:
        """两行底栏：第一行上下文提示，第二行 OpenCode 风格菜单条。"""
        from rich.text import Text
        width = max(self.size.width, 20)
        t = Text()
        if self.state.busy:
            t.append(" " + "\u00b7" * 7 + " esc interrupt",
                     style=COLORS["thought"])
            mid = f"{self.state.tokens_short} ({self.state.percent:.0f}%)"
            hint = "ctrl+p commands"
            gap = max(width - cell_width(mid) - cell_width(hint) - 3, 1)
            t.append(" " * gap + mid, style="dim")
            t.append("  " + hint, style="dim")
        elif self.state.messages:
            t.append(" ~", style="dim")
            mid = f"{self.state.tokens_short} ({self.state.percent:.0f}%)"
            hint = "ctrl+p commands"
            gap = max(width - cell_width(mid) - cell_width(hint) - 3, 1)
            t.append(" " * gap + mid, style="dim")
            t.append("  " + hint, style="dim")
        else:
            t.append(" ~", style="dim")
            right = "shift+tab mode   ctrl+p commands"
            gap = max(width - cell_width(right) - 3, 1)
            t.append(" " * gap + right, style="dim")
        t.append("\n")
        # 菜单条：✓ Kernel 绿 + 快捷入口 + 版本号
        kernel = f"{icons.glyph('ok')} Kernel"
        t.append(kernel, style=COLORS["ok"])
        items = ("Theme", "Sidebar", "Context", "Settings", "Stats", "Help")
        for item in items:
            t.append("  " + item, style="dim")
        used = len(kernel) + sum(len("  " + i) for i in items)
        tail = f"v{VERSION}"
        gap = max(width - used - len(tail) - 1, 1)
        t.append(" " * gap + tail, style=COLORS["text-faint"])
        self.query_one("#cx-statusbar", Static).update(t)

    # -------------------------------------------------------- 消息流 #
    def submit(self, text: str) -> None:
        """发送一条消息（Composer 或命令面板都会走这里）。"""
        text = text.strip()
        if text.startswith("/"):
            head = text.split()[0].lower()
            if head[1:] in kernel_cmds.SLASH:
                self._run_slash(text)
                return
            target = SLASH_ALIASES.get(head)
            if target:
                self.run_command(target, slash_text=text)
            else:
                self.notify(f"unknown command {head} (ctrl+p for all)",
                            timeout=3)
            return
        if self.state.busy:
            self.notify("busy - press Esc to stop", timeout=2)
            return
        # @ 引用与 CLI REPL 同款：进入回合前展开，段落随消息体进内核
        try:
            text, notes = kernel_cmds.expand_at(self.engine, text)
            for note in notes:
                self.notify(note, timeout=4)
        except Exception as exc:
            self.notify(f"@reference expansion failed: {exc}", timeout=4)
        self._submit_message(text)

    def _submit_message(self, text: str) -> None:
        """真正把一条消息交给流式回合（kernel 命令的 send 出口也走这里）。"""
        self.state.error = ""
        self._reasoning_started = None
        self.state.add_user(text)
        self.state.begin_assistant()
        self.state.busy = True
        self._sync_view_mode()
        self._refresh_all()

        def work() -> None:
            try:
                for evt in self.engine.ask(text):
                    msg = map_event(evt)
                    if msg is not None:
                        self.post_message(msg)
            except Exception as exc:                  # 网络/后端异常
                self.post_message(Finished("error", message=str(exc)))

        self.run_worker(work, thread=True, exclusive=True,
                        name="cedric-agent")

    # ------------------------------------------------------- 事件处理 #
    def on_chunk(self, msg: Chunk) -> None:
        if self.state.streaming is None:
            self.state.begin_assistant()
        self._seal_reasoning()
        self.state.streaming.text += msg.text
        self._refresh_all()

    def on_reasoning(self, msg: Reasoning) -> None:
        if self.state.streaming is None:
            self.state.begin_assistant()
        if self._reasoning_started is None:
            self._reasoning_started = time.time()
        self.state.streaming.reasoning += msg.text
        self._refresh_all()

    def on_tool_start(self, msg: ToolStart) -> None:
        if self.state.streaming is None:
            self.state.begin_assistant()
        self._seal_reasoning()
        self.state.streaming.tools.append(ToolRun(msg.name, msg.args))
        self._refresh_all()

    def on_tool_end(self, msg: ToolEnd) -> None:
        tools = self.state.streaming.tools if self.state.streaming else []
        for tool in reversed(tools):
            if tool.name == msg.name and tool.status == "running":
                tool.status = "error" if msg.status == "error" else "ok"
                tool.output = msg.output
                tool.ended = time.time()
                break
        self._refresh_all()

    def on_usage(self, msg: Usage) -> None:
        self.state.usage = dict(msg.payload)
        self.state.tokens = int(msg.payload.get("total_tokens") or 0)
        self._refresh_all()

    def on_finished(self, msg: Finished) -> None:
        self.state.busy = False
        self._seal_reasoning()
        duration = msg.duration
        speed = ""
        if duration:
            out_tokens = int(self.state.usage.get("completion_tokens") or 0)
            if not out_tokens:
                tok = self.state.streaming.text if self.state.streaming else ""
                out_tokens = int(len(tok) / 2.5)     # CJK 粗估：1 字 ≈ 2.5 tok
            speed = f" \u00b7 {out_tokens / max(duration, .01):.1f} tok/s"
        meta = (f"{self.state.mode} \u00b7 {self.state.model} \u00b7 "
                f"{duration:.1f}s{speed}")
        if msg.kind == "error":
            self.state.finish_assistant(meta=meta, error=msg.message)
            self.state.error = msg.message
        elif msg.kind == "aborted":
            self.state.finish_assistant(meta=meta + " \u00b7 aborted")
            self.notify("aborted", timeout=2)
        else:
            self.state.finish_assistant(meta=meta)
        self._sync_view_mode()
        self._refresh_all()

    def _seal_reasoning(self) -> None:
        """把正在流式消息的推理耗时定格（首个正文/工具/结束时调用）。"""
        if self._reasoning_started is None:
            return
        if self.state.streaming is not None and self.state.streaming.reasoning:
            self.state.streaming.reasoning_ms = \
                (time.time() - self._reasoning_started) * 1000
        self._reasoning_started = None

    # ------------------------------------------------------ 标签条交互 #
    def switch_tab(self, index: int) -> None:
        if not self.tabs:
            return
        self.tab_index = index % len(self.tabs)
        self._load_session(self.tabs[self.tab_index].get("id") or "")
        self._refresh_all()

    # ---------------------------------------------------------- 命令 #
    def run_command(self, name: str, slash_text: str = "") -> None:
        """跑一个面板命令；``slash_text`` 仅用于带参通知（面板命令
        均零参——CLI 里带参的命令在 ``submit`` 已被 kernel_cmds 接走）。"""
        name = cmd_mod.ALIASES.get(name, name)
        for c, _desc, func in self.commands:
            if c == name:
                func()
                return
        self.notify(f"not implemented: {name}", timeout=2)

    # -- 浮层 ---------------------------------------------------------- #
    def _open_modal(self, inner: Widget) -> None:
        """把一个 widget 装进居中的浮层容器（同屏只留一个）。"""
        self._close_modal()
        box = Widget(classes="modal-layer")
        self.modal = box
        self.mount(box)
        box.mount(inner)
        if inner.can_focus:
            inner.focus()

    def _close_modal(self) -> None:
        if self.modal is not None:
            self.modal.remove()
            self.modal = None
            self.query_one(Composer).focus()

    def action_palette(self) -> None:
        self._open_modal(
            CommandPalette([(c, d) for c, d, _ in self.commands]))

    def action_focus_sessions(self) -> None:
        self.query_one(SessionList).focus()

    # -- 内核直连（kernel_cmds） ---------------------------------------- #
    def _run_slash(self, line: str) -> None:
        """执行一条内核 slash 命令（submit 路由过来的）。"""
        res = kernel_cmds.dispatch(self.engine, line)
        kind = res["kind"]
        if kind == "notify":
            self.notify(res["text"], timeout=3)
        elif kind == "confirm":
            self.notify(res["text"], timeout=5)
        elif kind == "send":
            self._submit_message(res["text"])
        elif kind == "modal":
            self._execute_kernel(res["label"], res["fn"],
                                 res.get("busy_safe", False))

    def _execute_kernel(self, label: str, fn, busy_safe: bool) -> None:
        if self.state.busy and not busy_safe:
            self.notify("busy - press Esc to stop", timeout=2)
            return
        self.notify(f"running {label}...", timeout=2)

        def work() -> None:
            try:
                out = kernel_cmds.run_captured(self.engine.copilot, fn)
            except Exception as exc:            # 内核构造/执行兜底
                out = f"✗ kernel command failed: {exc}"
            self.post_message(KernelOutput(label, out))

        self.run_worker(work, thread=True, exclusive=False,
                         name="cedric-kernel")

    def on_kernel_output(self, msg: KernelOutput) -> None:
        from rich.text import Text
        text = (msg.text or "").strip()
        if not text:
            self.notify(f"{msg.label}: done", timeout=2)
            return
        self._open_modal(Static(Text(text), classes="modal-box modal-wide"))
        if msg.label == "resume":
            # 内核已把会话数据吃进去了，TUI 状态重新拉一次
            self._reload_sessions()
            self._load_session(
                self.engine.info().get("session_id") or "")

    def action_toggle_sidebar(self) -> None:
        self.query_one("#cx-sidebar").toggle_class("hidden")

    def action_toggle_context(self) -> None:
        self.query_one("#cx-right").toggle_class("hidden")

    def action_cycle_mode(self) -> None:
        idx = (MODES.index(self.state.mode) + 1) % len(MODES) \
            if self.state.mode in MODES else 0
        self.state.mode = MODES[idx]
        self.query_one(Composer).set_meta(mode=self.state.mode)
        self._refresh_all()

    def action_stop(self) -> None:
        if self.state.busy:
            self.engine.stop()
            self.notify("stopping...", timeout=2)

    def action_escape(self) -> None:
        """Esc 逐层关闭：浮层 → 停止生成 → 焦点回 composer。"""
        if self.modal is not None:
            self._close_modal()
        elif self.state.busy:
            self.action_stop()
        else:
            self.query_one(Composer).focus()

    def action_new_session(self) -> None:
        self.engine.new_session()
        self.state.reset()
        self.state.title = ""
        self.query_one(Transcript).view.expanded_thoughts.clear()
        self.query_one(Transcript).view.expanded_tools.clear()
        self.tabs.insert(0, {"id": self.engine.info().get("session_id")
                             or "new", "title": "New session"})
        self.tab_index = 0
        self._sync_view_mode()
        self.notify("new session", timeout=2)
        self._refresh_all()

    def action_clear(self) -> None:
        self.state.reset()
        self._sync_view_mode()
        self.notify("session cleared", timeout=2)
        self._refresh_all()

    def action_compact(self) -> None:
        removed = self.state.compact()
        self._sync_view_mode()
        if removed:
            self.notify(f"compact: {removed} message(s) dropped", timeout=2)
        else:
            self.notify("compact: nothing to drop", timeout=2)
        self._refresh_all()

    def action_undo(self) -> None:
        if self.state.busy:
            self.notify("busy - press Esc to stop", timeout=2)
            return
        if self.state.undo_last_exchange():
            self._sync_view_mode()
            self.notify("undo: last exchange removed", timeout=2)
            self._refresh_all()
        else:
            self.notify("undo: nothing to undo", timeout=2)

    def action_export(self) -> None:
        self.notify("export via WebUI or /export (CLI)", timeout=3)

    def action_toggle_reasoning(self) -> None:
        self.query_one(Transcript).view.toggle_last_thought()

    def action_toggle_theme(self) -> None:
        self.screen.toggle_class("light-mode")
        self.notify("theme switched", timeout=2)

    def action_help(self) -> None:
        from rich.text import Text
        t = Text()
        t.append("Shortcuts\n\n", style="bold")
        rows = [("ctrl+p", "command palette"), ("ctrl+k", "search sessions"),
                ("shift+tab", "cycle mode"), ("space", "expand tool"),
                ("t", "expand thought"), ("ctrl+b", "toggle sidebar"),
                ("ctrl+n", "new session"), ("ctrl+s", "stats screen"),
                ("esc", "close overlay / stop"), ("ctrl+q", "exit")]
        for k, v in rows:
            t.append(f"  {k:<12}", style=COLORS["accent"])
            t.append(v + "\n", style="")
        t.append("\nslash commands\n", style="bold")
        t.append("  ~45 kernel commands work as /model /think /mode "
                 "/tools\n", style=COLORS["accent"])
        t.append("  /cron /mem /cost /pricing /audit ... — same args as "
                 "the CLI.\n", style="dim")
        t.append("  ctrl+p lists them; unknown names will tell you.\n",
                 style="dim")
        self._open_modal(Static(t, classes="modal-box"))

    def action_pick_model(self) -> None:
        """切换模型：引擎给得出候选就在候选间轮换，否则只报当前值。"""
        try:
            models = list(self.engine.info().get("models") or [])
        except Exception:
            models = []
        if models:
            cur = self.state.model
            if cur in models:
                nxt = models[(models.index(cur) + 1) % len(models)]
            else:
                nxt = models[0]
            self.state.model = nxt
            self.query_one(Composer).set_meta(model=nxt)
            self.notify(f"model -> {nxt}", timeout=2)
        else:
            self.notify(f"model: {self.state.model} (engine-managed)",
                        timeout=3)
        self._refresh_all()

    def action_stats(self) -> None:
        """ctrl+s / palette stats：全屏统计屏（点阵数字 + 热力图）。"""
        self._open_modal(StatsScreen(classes="fs-panel"))

    def action_settings(self) -> None:
        """palette settings：交互式设置浮层（←/→ 改值）。"""
        self._open_modal(SettingsPanel())

    # -- 内核命令的零参面板入口（参数走 Composer 的 / 语法） ------------- #
    def action_resume(self):
        self._run_slash("/resume")

    def action_save_as(self):
        self._run_slash("/save-as")

    def action_think(self):
        self._run_slash("/think")

    def action_access_mode(self):
        self._run_slash("/mode")

    def action_yes(self):
        self._run_slash("/yes")

    def action_shell(self):
        self._run_slash("/shell")

    def action_sandbox(self):
        self._run_slash("/sandbox")

    def action_computer(self):
        self._run_slash("/computer")

    def action_tools(self):
        self._run_slash("/tools")

    def action_allow(self):
        self._run_slash("/allow")

    def action_plan(self):
        self._run_slash("/plan")

    def action_todos(self):
        self._run_slash("/todos")

    def action_history(self):
        self._run_slash("/history")

    def action_diff(self):
        self._run_slash("/diff")

    def action_tags(self):
        self._run_slash("/tag")

    def action_snapshots(self):
        self._run_slash("/snapshots")

    def action_replay(self):
        self._run_slash("/replay")

    def action_audit(self):
        self._run_slash("/audit")

    def action_cache(self):
        self._run_slash("/cache")

    def action_config(self):
        self._run_slash("/config")

    def action_save_config(self):
        self._run_slash("/save-config")

    def action_profile(self):
        self._run_slash("/profile")

    def action_lang(self):
        self._run_slash("/lang")

    def action_jobs(self):
        self._run_slash("/jobs")

    def action_email(self):
        self._run_slash("/email")

    def action_memory(self):
        self._run_slash("/mem")

    def action_cron(self):
        self._run_slash("/cron")

    def action_dream(self):
        self._run_slash("/dream")

    def action_asks(self):
        self._run_slash("/asks")

    def action_pricing(self):
        self._run_slash("/pricing")

    def action_cost(self):
        self._run_slash("/cost")

    def action_budget(self):
        self._run_slash("/budget")

    def action_dog(self):
        self._run_slash("/dog")

    def action_office_check(self):
        self._run_slash("/office-check")

    # ------------------------------------------------------ 子控件消息 #
    def on_composer_submitted(self, msg: Composer.Submitted) -> None:
        self.submit(msg.value)

    def on_session_list_picked(self, msg: SessionList.Picked) -> None:
        self._load_session(msg.session_id)

    def on_session_list_new_session(self, msg: SessionList.NewSession) -> None:
        self.action_new_session()

    def on_tab_bar_switch(self, msg: TabBar.Switch) -> None:
        self.switch_tab(msg.index)

    def on_tab_bar_close(self, msg: TabBar.Close) -> None:
        if not self.tabs:
            return
        self.tabs.pop(msg.index)
        self.tab_index = max(min(self.tab_index, len(self.tabs) - 1), 0)
        self._refresh_all()

    def on_tab_bar_new(self, msg: TabBar.New) -> None:
        self.action_new_session()

    def on_getting_started_card_dismiss(self, msg) -> None:
        try:
            self.query_one(GettingStartedCard).add_class("hidden")
        except Exception:
            pass
        self.gs_dismissed = True

    def _load_session(self, session_id: str) -> None:
        if not session_id:
            return
        data = self.engine.load_session(session_id)
        if data and not data.get("error"):
            self.state.load_from(data)
            self.state.title = data.get("title") or session_id
        else:
            self.state.reset()
            self.state.title = session_id
        self.query_one(Transcript).view.expanded_thoughts.clear()
        self.query_one(Transcript).view.expanded_tools.clear()
        self.query_one(SessionList).current = session_id
        self._sync_view_mode()
        self._refresh_all()
        self.notify(f"switched to \u300c{self.state.title or session_id}\u300d",
                    timeout=2)

    # ---------------------------------------------------------- 收尾 #
    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+c":
            if self.state.busy:
                self.engine.stop()
                event.stop()


def main(demo: bool = False) -> int:
    """``python -m one_cedric.tui`` / ``one-cedric --tui`` 的入口。"""
    try:
        import textual  # noqa: F401
    except ImportError:
        print("TUI needs textual: pip install 'one-cedric[tui]'")
        return 2
    engine = Engine()
    if demo:
        from .bridge import FakeEngine
        engine = FakeEngine()
    CedricTUI(engine=engine, demo=demo).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
