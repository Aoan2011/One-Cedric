"""Shell C：首页（无会话时的欢迎屏）。

对齐 OpenCode 首页：垂直居中的渐变点阵 logo + 一行版本提示。
composer 与底部快捷键由 App 的 composer/状态栏提供，这里只画中间块。
"""
from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from ..design import truncate
from ..theme import VERSION
from .logo import gradient_rows

LOGO_WORD = "CEDRIC"


class HomePanel(Widget):
    """首页中央的渐变 logo + 版本行。"""

    def render(self) -> Text:
        width = max(self.size.width, 20)
        out = Text()
        segs_rows = gradient_rows(LOGO_WORD)
        art_width = max(sum(len(seg) for seg, _ in row) for row in segs_rows)
        if art_width + 2 <= width:               # 宽屏：渐变点阵字
            pad = (width - art_width) // 2
            for row in segs_rows:
                out.append(" " * pad)
                for seg, color in row:
                    out.append(seg, style=color)
                out.append("\n")
        else:                                    # 窄屏降级为普通大字
            pad = max((width - len(LOGO_WORD) - 2) // 2, 0)
            out.append(" " * pad + LOGO_WORD + "\n", style="bold accent")
        out.append("\n")
        hint = f"one-cedric v{VERSION}"
        out.append(truncate(" " * max((width - len(hint)) // 2, 0) + hint,
                            width) + "\n", style="dim")
        return out
