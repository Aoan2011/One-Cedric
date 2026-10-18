"""Shell C：对话流。

对齐 OpenCode 的消息块渲染：

* 每条消息左侧一条细竖线（用户 = 深强调色，助手 = 暗灰）；
* 推理内容默认折叠成一行 ``▸ Thought · <ms>``，``t`` 键展开；
* 工具调用折叠成 ``▸ <name> · <args> · <s>``（名称粗体 + 状态色圆点），
  空格键展开输出；识别到 unified diff 时按 ``+``/``-`` 着色平铺；
* 助手消息尾部一行元信息 ``Build · <model> · <s> · <tok/s> tok/s``。

之所以自绘而不用一堆子控件，是因为流式增量每 30ms 就来一次，堆叠控件会
不停重排整棵树；这里只重建一段 rich 文本。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.containers import ScrollableContainer
from textual.widgets import Static

from ...ui import icons
from ..design import truncate
from ..state import ChatMessage, SessionState, ToolRun
from ..theme import COLORS

BAR_USER = COLORS["accent-deep"]
BAR_ASSIST = COLORS["border-strong"]

_STATUS_STYLE = {"running": COLORS["thought"], "ok": COLORS["ok"],
                 "error": COLORS["danger"]}
#: 状态 -> 图标语义键（回退字形见 icons.CATALOG）
_STATUS_ICON_KEYS = {"running": "running_half", "ok": "check",
                     "error": "error_thick"}


def is_diff(text: str) -> bool:
    """粗判一段工具输出是不是 unified diff。"""
    for line in text.splitlines()[:8]:
        if line.startswith(("diff --git", "@@ ", "+++ ", "--- ")):
            return True
    return False


class TranscriptView(Static):
    """对话内容本身（纯 rich 文本，由 Transcript 刷新）。"""

    def __init__(self, state: SessionState, **kwargs):
        super().__init__("", **kwargs)
        self.state = state
        self.expanded_thoughts: set[int] = set()      # 消息下标
        self.expanded_tools: set[tuple[int, int]] = set()
        #: 设置浮层里的 Thinking 开关：关闭后连折叠行都不画。
        self.show_thought_lines = True

    def on_mount(self) -> None:
        self.rebuild()

    # -- 渲染 ---------------------------------------------------------- #
    def rebuild(self) -> None:
        width = max(self.size.width - 2, 24)
        self.update(self._content(width))
        parent = self.parent
        if isinstance(parent, ScrollableContainer):
            parent.scroll_end(animate=False)

    def _bar(self, out: Text, style: str) -> None:
        out.append("\u258e ", style=style)

    def _content(self, width: int) -> Text:
        out = Text()
        st = self.state
        if not st.messages:
            return out
        for idx, msg in enumerate(st.messages):
            if msg.role == "user":
                for i, raw in enumerate(msg.text.splitlines() or [""]):
                    self._bar(out, BAR_USER)
                    out.append(truncate(raw, width - 2) + "\n",
                               style="bold" if i == 0 else "")
                out.append("\n")
                continue
            if msg.role == "system":
                for raw in msg.text.splitlines() or [""]:
                    self._bar(out, BAR_ASSIST)
                    out.append(truncate(raw, width - 2) + "\n", style="dim")
                out.append("\n")
                continue
            self._append_assistant(out, msg, idx, width)
        return out

    def _append_assistant(self, out: Text, msg: ChatMessage, idx: int,
                          width: int) -> None:
        if msg.reasoning and self.show_thought_lines:
            open_ = idx in self.expanded_thoughts
            glyph = icons.glyph("expand") if open_ else icons.glyph("collapse")
            ms = int((msg.reasoning_ms or 0) * 1000)
            self._bar(out, BAR_ASSIST)
            out.append(f"{glyph} Thought \u00b7 {ms}ms\n",
                       style=COLORS["thought"])
            if open_:
                for raw in msg.reasoning.splitlines()[:60]:
                    self._bar(out, BAR_ASSIST)
                    out.append("  " + truncate(raw, width - 4) + "\n",
                               style="dim")
        for t_idx, tool in enumerate(msg.tools):
            self._append_tool(out, tool, (idx, t_idx), width)
        body = msg.text or ("" if msg.done else "\u258c")
        for raw in (body.splitlines() if msg.text else [body]):
            self._bar(out, BAR_ASSIST)
            out.append(truncate(raw, width - 2) + "\n")
        if msg.error:
            self._bar(out, BAR_ASSIST)
            out.append(" " + icons.glyph("error_thick") + " " +
                       truncate(msg.error, width - 3) + "\n",
                       style=COLORS["danger"])
        if msg.meta:
            self._bar(out, BAR_ASSIST)
            out.append(" " + truncate(msg.meta, width - 2) + "\n",
                       style="dim")
        out.append("\n")

    def _append_tool(self, out: Text, tool: ToolRun, key, width: int) -> None:
        status_style = _STATUS_STYLE.get(tool.status, "dim")
        status_glyph = icons.glyph(_STATUS_ICON_KEYS.get(tool.status, ""),
                                   icons.glyph("bullet"))
        open_ = key in self.expanded_tools or tool.status == "running"
        glyph = icons.glyph("expand") if open_ else icons.glyph("collapse")
        self._bar(out, BAR_ASSIST)
        out.append(f"{glyph} ", style="dim")
        out.append(tool.name, style=f"bold {status_style}")
        if tool.args:
            out.append(" \u00b7 " +
                       truncate(tool.args, max(width - 34, 10)),
                       style="dim")
        out.append(f"  {tool.elapsed:.1f}s", style=COLORS["text-faint"])
        out.append(" " + status_glyph, style=status_style)
        out.append("\n")
        if not open_:
            return
        body = tool.output or tool.detail or ""
        if is_diff(body):
            self._append_diff(out, body, width)
            return
        for raw in body.splitlines()[:10]:
            self._bar(out, BAR_ASSIST)
            out.append("  " + truncate(raw, width - 4) + "\n", style="dim")

    def _append_diff(self, out: Text, body: str, width: int) -> None:
        """diff 平铺：+ 绿底、- 红底、@@ 强调、文件头暗色。"""
        for raw in body.splitlines()[:80]:
            self._bar(out, BAR_ASSIST)
            if raw.startswith("@@"):
                style = COLORS["accent"]
            elif raw.startswith(("+++", "---", "diff --git", "index ")):
                style = "dim"
            elif raw.startswith("+"):
                style = f"{COLORS['ok']} on {COLORS['diff-add']}"
            elif raw.startswith("-"):
                style = f"{COLORS['danger']} on {COLORS['diff-del']}"
            else:
                style = "dim"
            out.append("  " + truncate(raw, width - 4) + "\n", style=style)

    # -- 交互 ---------------------------------------------------------- #
    def toggle_last_tool(self) -> None:
        """空格键：展开/收起最后一条工具输出。"""
        for idx in range(len(self.state.messages) - 1, -1, -1):
            tools = self.state.messages[idx].tools
            if tools:
                key = (idx, len(tools) - 1)
                if key in self.expanded_tools:
                    self.expanded_tools.discard(key)
                else:
                    self.expanded_tools.add(key)
                self.rebuild()
                return

    def toggle_last_thought(self) -> None:
        """``t`` 键：展开/收起最后一条推理内容。"""
        for idx in range(len(self.state.messages) - 1, -1, -1):
            if self.state.messages[idx].reasoning:
                if idx in self.expanded_thoughts:
                    self.expanded_thoughts.discard(idx)
                else:
                    self.expanded_thoughts.add(idx)
                self.rebuild()
                return


class Transcript(ScrollableContainer):
    """滚动容器 + 内容 widget。"""

    def __init__(self, state: SessionState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.view = TranscriptView(state, id="cx-transcript-view")

    def compose(self):
        yield self.view

    def on_key(self, event: events.Key) -> None:
        if event.key == "space":
            self.view.toggle_last_tool()
            event.stop()
        elif event.key == "t":
            self.view.toggle_last_thought()
            event.stop()

    @property
    def show_reasoning(self) -> bool:
        """兼容旧接口：现在默认折叠，逐条展开。"""
        return True

    def refresh_content(self, force: bool = False) -> None:
        self.view.rebuild()
