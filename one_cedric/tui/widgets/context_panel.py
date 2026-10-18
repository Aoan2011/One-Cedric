"""Shell C：右侧 Context 面板。

对齐 OpenCode 右栏：当前会话标题（粗体）+ 分隔线 + ``Context`` 小节，
下面两行分别是 ``<N> tokens`` 与 ``<P>% used``（占用高过 80% 时变暖橙）。
Getting started 卡是独立 widget，由 App 挂在本面板下方。
"""
from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from ..design import truncate
from ..state import SessionState
from ..theme import COLORS


class ContextPanel(Widget):
    """只读上下文用量栏。"""

    def __init__(self, state: SessionState, **kwargs):
        super().__init__(**kwargs)
        self.state = state

    def refresh_panel(self) -> None:
        self.refresh()

    def render(self) -> Text:
        st = self.state
        width = max(self.size.width - 3, 16)
        t = Text()
        t.append(truncate(st.title or "New session", width) + "\n",
                 style="bold")
        t.append("\u2500" * width + "\n", style=COLORS["border"])
        t.append("\n")
        t.append("Context\n", style="dim")
        tokens = st.tokens
        if tokens >= 1000:
            shown = f"{tokens / 1000:.1f}K"
        else:
            shown = f"{tokens:,}"
        t.append(shown + " tokens\n", style="bold")
        pct = st.percent
        t.append(f"{pct:.0f}% used\n",
                 style=COLORS["model"] if pct >= 80 else "dim")
        if st.model:
            t.append("\n" + truncate(st.model, width) + "\n", style="dim")
        if st.host:
            t.append(truncate(st.host, width) + "\n", style=COLORS["text-faint"])
        return t
