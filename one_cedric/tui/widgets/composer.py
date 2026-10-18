"""Shell C：composer 输入块。

对齐 OpenCode：一个圆角输入框，内部左侧一条紫色粗竖条（本 widget 自绘
``▌``），第一行是输入，第二行 ``Build · <model> · <think>`` —— 模式用
主文本色，模型与思考档位用暖橙，和截图一致。Enter 发送，Shift+Enter
换行（多行由 Composer 自身维护），Esc 中断（由 App 处理）。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ..design import cell_width, truncate
from ..theme import COLORS


class Composer(Widget):
    """边框内的两行输入区。"""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value = ""
        self.placeholder = 'Ask anything... "Fix a TODO in the codebase"'
        self.mode = "Build"
        self.model = "-"
        self.host = "-"
        self.think = ""
        self.hist: list[str] = []
        self._hist_idx = 0
        self.can_focus = True

    # -- 渲染 ---------------------------------------------------------- #
    def render(self) -> Text:
        width = max(self.size.width - 4, 16)
        t = Text()
        bar = COLORS["accent"]
        # 第一行：▌ + 输入（空时显示占位）
        t.append("\u258c ", style=bar)
        if self.value:
            t.append(truncate(self.value, width - 2))
        else:
            t.append(truncate(self.placeholder, width - 2), style="dim")
        t.append("\n")
        # 第二行：▌ Build · model · think
        t.append("\u258c ", style=bar)
        budget = width - 2

        def seg(text: str, style: str = "") -> None:
            nonlocal budget
            if budget <= 0 or not text:
                return
            shown = truncate(text, budget)
            t.append(shown, style=style)
            budget -= cell_width(shown)

        seg(self.mode, f"bold {COLORS['text']}")
        seg(" \u00b7 ", "dim")
        seg(self.model or "-", COLORS["model"])
        if self.think:
            seg(" \u00b7 ", "dim")
            seg(self.think, COLORS["model"])
        return t

    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key == "enter":
            text = self.value.strip()
            if text:
                self.hist.append(text)
                self._hist_idx = len(self.hist)
                self.value = ""
                self.refresh()
                self.post_message(self.Submitted(text))
            event.stop()
            return
        if key in ("up", "down") and self.hist:
            step = -1 if key == "up" else 1
            self._hist_idx = min(max(self._hist_idx + step, 0), len(self.hist))
            self.value = (self.hist[self._hist_idx]
                          if self._hist_idx < len(self.hist) else "")
            self.refresh()
            event.stop()
            return
        if key == "backspace":
            self.value = self.value[:-1]
        elif key == "ctrl+w":
            self.value = self.value.rsplit(" ", 1)[0] if " " in self.value else ""
        elif key == "ctrl+u":
            self.value = ""
        elif event.is_printable and event.character:
            self.value += event.character
        else:
            return
        self.refresh()
        event.stop()

    def set_meta(self, mode: str = "", model: str = "", host: str = "",
                 think: str = "") -> None:
        self.mode = mode or self.mode
        self.model = model or self.model
        self.host = host or self.host
        if think:
            self.think = think
        self.refresh()
