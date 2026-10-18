"""Shell C：Context 面板下方的 Getting started 卡片。

对齐 OpenCode 右栏的可关闭提示卡：``◇ Getting started`` 标题一行（右上角
``✕``）+ 细分隔线 + 两三行提示正文；动作行左侧白字、右侧 ``/connect``
强调色。``x`` 键或鼠标点击都会关掉它（运行期内不再弹回）。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ...ui import icons
from ..design import cell_width, pad, truncate
from ..theme import COLORS


class GettingStartedCard(Widget):
    """可关闭的入门提示卡。"""

    class Dismiss(Message):
        pass

    def __init__(self, lines: list[tuple[str, str]] | None = None, **kwargs):
        super().__init__(**kwargs)
        #: (正文, 右侧强调动作) 列表；动作为空则整行按次要文本画。
        self.lines = lines or [
            ("One Cedric ships with a local kernel so you can start "
             "right away.", ""),
            ("Connect any OpenAI-compatible provider: DeepSeek, Kimi, "
             "GLM, Ollama.", ""),
            ("Connect provider", "/connect"),
        ]
        self.can_focus = True

    def render(self) -> Text:
        width = max(self.size.width - 4, 12)
        t = Text()
        head = "Getting started"
        t.append(icons.glyph("diamond") + " ", style=COLORS["accent"])
        t.append(head, style="bold")
        t.append(" " * max(width - cell_width(head) - 3, 1) +
                 icons.glyph("close"), style="dim")
        t.append("\n")
        t.append("\u2500" * width + "\n", style=COLORS["border"])
        t.append("\n")
        for body, action in self.lines:
            if body and action:
                gap = max(width - cell_width(body) - cell_width(action) - 1, 1)
                t.append(truncate(body, width - cell_width(action) - 2))
                t.append(" " * gap)
                t.append(action, style=COLORS["accent"])
                t.append("\n")
                continue
            if body:
                t.append(truncate(body, width) + "\n", style="dim")
            if action:
                t.append(pad(action, width, "right") + "\n",
                         style=COLORS["accent"])
        return t

    def on_key(self, event: events.Key) -> None:
        if event.key in ("x", "delete", "escape"):
            self.post_message(self.Dismiss())
            event.stop()

    def on_click(self) -> None:
        self.post_message(self.Dismiss())
