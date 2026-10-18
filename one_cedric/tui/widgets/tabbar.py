"""Shell C：顶部会话标签条。

对齐 OpenCode 顶部标签条：每个会话一项 —— 当前项是紫底 pill（``◆ 标题``
白字），其余是暗灰 ``● 标题``；最右侧一个 ``+ New session`` 深紫 pill。
命令面板已拆到 ``widgets/palette.py``。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ...ui import icons
from ..design import cell_width, truncate
from ..theme import COLORS

#: 侧栏收起/展开/上下文/主页（回退字形；实际字形经 icons 解析）
GLYPHS = {"menu": "\u2630", "left": "\u2039", "right": "\u203a", "side": "\u25a4",
          "panel": "\u25a5", "home": "\u2302"}


class TabBar(Widget):
    """顶部标签栏：``◆ 当前会话  ● 其它会话   + New session``。"""

    class Switch(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    class Close(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    class New(Message):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tabs: list[dict] = []      # {id,title}
        self.active = 0
        self.can_focus = True

    def set_tabs(self, tabs: list[dict], active: int = 0) -> None:
        self.tabs = tabs
        self.active = min(active, max(len(tabs) - 1, 0))
        self.refresh()

    def render(self) -> Text:
        width = max(self.size.width - 2, 12)
        t = Text()
        budget = max(width // max(len(self.tabs), 1), 10)
        used = 0
        for i, tab in enumerate(self.tabs):
            title = tab.get("title") or tab.get("id") or "session"
            label = truncate(title, budget - 4)
            if i == self.active:
                cell = f" {icons.glyph('diamond_filled')} {label} "
                t.append(cell, style=f"bold #ffffff on {COLORS['pill']}")
            else:
                cell = f" {icons.glyph('dot')} {label} "
                t.append(cell, style=COLORS["text-dim"])
            used += cell_width(cell)
        new = f" {icons.glyph('plus')} New session "
        pad = max(width - used - cell_width(new) - 1, 1)
        t.append(" " * pad)
        t.append(new, style=f"bold #ffffff on {COLORS['accent-deep']}")
        return t

    def on_key(self, event: events.Key) -> None:
        if event.key == "right" and self.tabs:
            self.post_message(self.Switch((self.active + 1) % len(self.tabs)))
        elif event.key == "left" and self.tabs:
            self.post_message(self.Switch((self.active - 1) % len(self.tabs)))
        elif event.key == "ctrl+w" and self.tabs:
            self.post_message(self.Close(self.active))
        elif event.key in ("n", "ctrl+n", "enter"):
            self.post_message(self.New())
        else:
            return
        event.stop()
