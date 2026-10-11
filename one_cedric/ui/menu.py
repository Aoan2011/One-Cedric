"""上下键导航菜单。"""
from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.text import Text

from ..config import ACCENT, BRAND, DIM_C
from ..i18n import t
from .keys import (
    KEY_DOWN,
    KEY_ENTER,
    KEY_ESC,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_UP,
    has_readchar,
    read_key,
)


def selection_progress(selected: int, total: int):
    if total <= 0:
        return None
    return Align.center(ProgressBar(
        total=total,
        completed=selected + 1,
        width=30,
        complete_style=BRAND,
        finished_style=BRAND,
        pulse_style=ACCENT,
    ))


class MenuItem:
    def __init__(self, key: str, label: str, desc: str = "",
                 enabled: bool = True):
        self.key = key
        self.label = label
        self.desc = desc
        self.enabled = enabled


class Menu:
    _ICONS = {
        "chat": "◇", "cli-chat": "◇", "gateway": "⌁", "tools": "⌘",
        "models": "◈", "mcp": "⟡", "hooks": "⟲", "settings": "⚙",
        "language": "文", "about": "i", "exit": "×", "quit": "×",
    }

    def __init__(self, console: Console, title: str, items: list[MenuItem],
                 subtitle: str = "", width: int = 60):
        self.console = console
        self.title = title
        self.subtitle = subtitle
        self.items = items
        self.width = width
        self.selected = 0

    def _icon_for(self, key: str) -> str:
        return self._ICONS.get(key, "·")

    def _render(self) -> None:
        self.console.clear()
        self.console.print()

        rows = []
        for i, item in enumerate(self.items):
            selected = i == self.selected
            if not item.enabled:
                style = "dim"
            elif selected:
                style = f"bold {BRAND}"
            else:
                style = ""

            line = Text()
            line.append("  ")
            if selected:
                line.append("▸ ", style=f"bold {BRAND}")
            else:
                line.append("  ")
            line.append(f"{self._icon_for(item.key)} ",
                        style=f"bold {BRAND}" if selected else DIM_C)
            line.append(item.label, style=style)
            if selected:
                line.append(" ◂", style=f"bold {BRAND}")
            if item.desc:
                line.append(f"   {item.desc}", style="dim")
            rows.append(line)

        title = Text()
        title.append(" ✦ ", style=f"bold {BRAND}")
        title.append("ONE CEDRIC", style=f"bold {BRAND}")
        title.append(f"   /   {self.title}", style="bold white")
        title = Align.center(title)

        content: list = [title]
        if self.subtitle:
            content.append(Align.center(
                Text(self.subtitle, style="dim")))
        content.append(Rule(style=DIM_C, characters="─"))
        content.extend(rows)
        if self.items:
            content.append(Rule(style=DIM_C, characters="─"))
            content.append(selection_progress(self.selected,
                                             len(self.items)))

        self.console.print(Panel(
            Group(*content),
            border_style=BRAND,
            box=box.ROUNDED,
            padding=(1, 2),
            expand=False,
        ))

        if has_readchar():
            hint = f"  [dim]{t('menu.hint.arrow')}[/]"
        else:
            hint = (
                f"  [dim]{t('menu.hint.text')}  ·  "
                f"[accent]q[/][dim] 返回[/]"
            )
        self.console.print(hint)

    def run(self) -> str | None:
        if not self.items or not any(item.enabled for item in self.items):
            return None
        self.selected = self._next_enabled(
            self.selected, 1, include_current=True
        )
        if not has_readchar():
            return self._run_fallback()

        while True:
            self._render()
            k = read_key()

            if k in (KEY_UP, KEY_LEFT):
                self.selected = self._next_enabled(self.selected, -1)
            elif k in (KEY_DOWN, KEY_RIGHT):
                self.selected = self._next_enabled(self.selected, 1)
            elif k == KEY_ENTER:
                item = self.items[self.selected]
                if item.enabled:
                    return item.key
            elif k in ("q", KEY_ESC):
                return None

    def _next_enabled(self, current: int, direction: int,
                      include_current: bool = False) -> int:
        index = current if include_current else current + direction
        for _ in self.items:
            index %= len(self.items)
            if self.items[index].enabled:
                return index
            index += direction
        return current

    def _run_fallback(self) -> str | None:
        while True:
            self._render_fallback()
            try:
                s = self.console.input(
                    f"  [dim]{t('menu.select_text')}[/] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            if s in ("q", "back", ""):
                return None
            matches = [item for item in self.items
                       if item.enabled and
                       s in (item.key.lower(), item.label.lower())]
            if len(matches) == 1:
                return matches[0].key
            self.console.print(f"  [dim]{t('menu.invalid')}[/]")

    def _render_fallback(self) -> None:
        """无 readchar 环境的轻量渲染：标题 + 编号列表（不重复打印面板）。"""
        self.console.clear()
        self.console.print()

        title = Text()
        title.append(" ✦ ", style=f"bold {BRAND}")
        title.append("ONE CEDRIC", style=f"bold {BRAND}")
        title.append(f"   /   {self.title}", style="bold white")
        self.console.print(Align.center(title))
        if self.subtitle:
            self.console.print(Align.center(
                Text(self.subtitle, style="dim")))
        self.console.print(Rule(style=DIM_C, characters="─"))
        for i, item in enumerate(self.items):
            flag = (
                "" if item.enabled
                else f" [dim]({t('menu.disabled_short')})[/]"
            )
            if not item.enabled:
                line = Text(f"  {i + 1}. {item.label}{flag}",
                            style="dim")
            else:
                line = Text()
                line.append(f"  {i + 1}. ", style=f"bold {BRAND}")
                line.append(item.label, style="bold")
                line.append(flag)
                if item.desc:
                    line.append(f"   {item.desc}", style="dim")
            self.console.print(line)
        self.console.print(Rule(style=DIM_C, characters="─"))
        self.console.print()


def select_menu(console: Console, title: str, items: list[MenuItem],
                subtitle: str = "") -> str | None:
    return Menu(console, title, items, subtitle).run()
