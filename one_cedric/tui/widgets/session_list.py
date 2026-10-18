"""Shell C：左侧会话列表。

分组（今天 / 更早）、当前项高亮、``n / N`` 计数、搜索框。数据来自
``storage.list_session_files``，没有后端也能用。
"""
from __future__ import annotations

import time

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ...ui import icons
from ..design import pad, truncate


def _group_of(ts: float) -> str:
    now = time.time()
    if now - ts < 86400:
        return "今天"
    if now - ts < 7 * 86400:
        return "本周"
    return "更早"


class SessionList(Widget):
    """会话列表 + 搜索。"""

    class Picked(Message):
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class NewSession(Message):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sessions: list[dict] = []         # {id,title,updated,count}
        self.current = ""
        self.cursor = 0
        self.query = ""
        self.can_focus = True

    # -- 数据 ---------------------------------------------------------- #
    def set_sessions(self, items: list[dict], current: str = "") -> None:
        self.sessions = items
        self.current = current or self.current
        self.cursor = min(self.cursor, max(len(self.visible) - 1, 0))
        self.refresh()

    @property
    def visible(self) -> list[dict]:
        if not self.query:
            return self.sessions
        q = self.query.lower()
        return [s for s in self.sessions
                if q in (s.get("title") or "").lower()
                or q in (s.get("id") or "").lower()]

    # -- 渲染 ---------------------------------------------------------- #
    def render(self) -> Text:
        width = max(self.size.width - 2, 14)
        t = Text()
        search = icons.glyph("search")
        t.append(" " + pad(f"{search} 搜索会话…" if not self.query else
                           f"{search} " + self.query, width) + "\n",
                 style="dim" if not self.query else "accent")
        t.append("─" * width + "\n", style="dim")
        items = self.visible
        if not items:
            t.append("  （没有匹配的会话）\n", style="dim")
        group = ""
        for i, item in enumerate(items):
            g = _group_of(item.get("updated") or 0)
            if g != group:
                group = g
                t.append("\n " + g + "\n", style="dim bold")
            sid = item.get("id") or ""
            title = item.get("title") or sid or "(未命名)"
            sel = i == self.cursor
            mark = "▍" if sid == self.current else " "
            style = "reverse" if sel else ("bold" if sid == self.current
                                           else "none")
            t.append(mark + truncate(title, width - 2) + "\n", style=style)
            sub = f"{item.get('count', 0)} 条 · {_ago(item.get('updated') or 0)}"
            t.append("  " + truncate(sub, width - 2) + "\n", style="dim")
        t.append("\n")
        t.append(" " + f"{self.cursor + 1} / {len(items)}", style="dim")
        return t

    # -- 交互 ---------------------------------------------------------- #
    def on_key(self, event: events.Key) -> None:
        items = self.visible
        if event.key == "down" and items:
            self.cursor = min(self.cursor + 1, len(items) - 1)
            self.refresh()
        elif event.key == "up":
            self.cursor = max(self.cursor - 1, 0)
            self.refresh()
        elif event.key == "enter" and items:
            self.post_message(self.Picked(items[self.cursor].get("id") or ""))
        elif event.key == "backspace":
            self.query = self.query[:-1]
            self.cursor = 0
            self.refresh()
        elif event.is_printable and event.character:
            self.query += event.character
            self.cursor = 0
            self.refresh()
        else:
            return
        event.stop()

    def clear_query(self) -> None:
        if self.query:
            self.query = ""
            self.refresh()


def _ago(ts: float) -> str:
    if not ts:
        return "未知"
    delta = max(time.time() - ts, 0)
    if delta < 3600:
        return f"{delta / 60:.0f} 分钟前"
    if delta < 86400:
        return f"{delta / 3600:.0f} 小时前"
    return f"{delta / 86400:.0f} 天前"
