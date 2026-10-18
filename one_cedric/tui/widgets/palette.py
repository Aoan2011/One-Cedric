"""Shell C：命令面板（ctrl+p）。

对齐 OpenCode 的命令面板：居中浮层 + 筛选输入行（右上角 ``esc``）+ 命令
列表（左名右描述）。当前项是紫底 pill，输入即筛选，Enter 执行，Esc 关闭。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ...ui import icons
from ..design import cell_width, truncate
from ..theme import COLORS


class CommandPalette(Widget):
    """ctrl+p 的模糊搜索浮层。"""

    class Run(Message):
        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, commands: list[tuple[str, str]], **kwargs):
        super().__init__(**kwargs)
        self.commands = commands                 # (命令, 说明)
        self.query = ""
        self.cursor = 0
        self.can_focus = True

    @property
    def visible_items(self) -> list[tuple[str, str]]:
        if not self.query:
            return self.commands
        q = self.query.lower()
        return [(c, d) for c, d in self.commands
                if q in c.lower() or q in d.lower()]

    def render(self) -> Text:
        width = max(self.size.width - 2, 20)
        t = Text()
        hint = self.query or "Type a command..."
        t.append(icons.glyph("right") + " " + hint,
                 style=COLORS["accent"] if self.query else "dim")
        t.append(" " * max(width - cell_width(hint) - 3 - 3, 1) + "esc",
                 style="dim")
        t.append("\n\n")
        items = self.visible_items[:14]
        for i, (name, desc) in enumerate(items):
            label = truncate(name, max(width - 4, 8))
            gap = max(width - cell_width(label) - cell_width(desc) - 2, 1)
            if i == self.cursor:
                row = icons.glyph("collapse") + " " + label + " " * gap + desc
                t.append(row, style=f"bold #ffffff on {COLORS['pill']}")
            else:
                t.append(" " + label, style="")
                t.append(" " * gap + desc, style="dim")
            t.append("\n")
        if not items:
            t.append("  No matching commands\n", style="dim")
        return t

    def on_key(self, event: events.Key) -> None:
        items = self.visible_items
        if event.key == "down" and items:
            self.cursor = min(self.cursor + 1, len(items) - 1)
        elif event.key == "up":
            self.cursor = max(self.cursor - 1, 0)
        elif event.key == "enter" and items:
            self.post_message(self.Run(items[self.cursor][0]))
        elif event.key == "backspace":
            self.query = self.query[:-1]
            self.cursor = 0
        elif event.is_printable and event.character:
            self.query += event.character
            self.cursor = 0
        else:
            return
        self.refresh()
        event.stop()
