"""Shell C：交互式设置浮层（对齐 OpenCode Settings 屏）。

``up/down`` 选择行，``left/right`` 改值，输入即筛选，``esc`` 关闭。
行都是真实开关：主题、侧栏、Thinking 折叠、思考档位、模型 ——
左列蓝底条形高亮 + ``●`` 圆点，分区标题用暖橙，和截图一致。
"""
from __future__ import annotations

from rich.text import Text
from textual import events
from textual.widget import Widget

from ...config import THINK_LEVELS
from ...ui import icons
from ..design import cell_width, truncate
from ..theme import COLORS


class SettingsPanel(Widget):
    """OpenCode 风格的设置浮层。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.query = ""
        self.cursor = 0
        self.can_focus = True
        self.rows = self._build_rows()

    # -- 行定义 -------------------------------------------------------- #
    def _build_rows(self) -> list[dict]:
        rows: list[dict] = []

        def add(section, label, options, get, setv):
            rows.append({"section": section, "label": label,
                         "options": options, "get": get, "set": setv})

        def theme_get(p):
            return "light" if p.app.screen.has_class("light-mode") else "dark"

        def theme_set(p, v):
            if v == "light":
                p.app.screen.add_class("light-mode")
            else:
                p.app.screen.remove_class("light-mode")

        def side_get(p):
            w = p.app.query_one("#cx-sidebar")
            return "hide" if w.has_class("hidden") else "show"

        def side_set(p, v):
            w = p.app.query_one("#cx-sidebar")
            if v == "hide":
                w.add_class("hidden")
            else:
                w.remove_class("hidden")

        def think_get(p):
            view = p.app.query_one("#cx-transcript-view")
            return "show" if getattr(view, "show_thought_lines", True) \
                else "hide"

        def think_set(p, v):
            view = p.app.query_one("#cx-transcript-view")
            view.show_thought_lines = (v == "show")
            view.rebuild()

        def depth_get(p):
            return p.app.state.think

        def depth_set(p, v):
            p.app.state.think = v
            try:
                p.app.query_one("#cx-composer").set_meta(think=v)
            except Exception:
                pass
            cp = getattr(p.app.engine, "_copilot", None)
            if cp is not None:
                try:
                    cp.think_level = v
                except Exception:
                    pass

        def model_get(p):
            return p.app.state.model or "-"

        def model_set(p, v):
            p.app.state.model = v
            try:
                p.app.query_one("#cx-composer").set_meta(model=v)
            except Exception:
                pass
            try:
                p.app._refresh_all()
            except Exception:
                pass

        add("Appearance", "Theme", ["dark", "light"], theme_get, theme_set)
        add("Session", "Sidebar", ["show", "hide"], side_get, side_set)
        add("Session", "Thinking", ["show", "hide"], think_get, think_set)
        add("Session", "Reasoning depth", list(THINK_LEVELS), depth_get,
            depth_set)
        add("Session", "Model", self._model_options(), model_get, model_set)
        return rows

    def _model_options(self) -> list:
        try:
            models = list(self.app.engine.info().get("models") or [])
        except Exception:
            models = []
        if not models:
            models = [self.app.state.model or "-"]
        return models

    # -- 数据 ---------------------------------------------------------- #
    def visible_rows(self) -> list[dict]:
        if not self.query:
            return self.rows
        q = self.query.lower()
        return [r for r in self.rows if q in r["label"].lower()]

    def _cycle(self, row: dict, step: int) -> None:
        opts = [str(o) for o in row["options"]]
        if len(opts) <= 1:
            return
        cur = str(row["get"](self))
        idx = opts.index(cur) if cur in opts else 0
        row["set"](self, opts[(idx + step) % len(opts)])

    # -- 渲染 ---------------------------------------------------------- #
    def render(self) -> Text:
        width = max(self.size.width - 4, 24)
        t = Text()
        title = "Settings"
        t.append(title, style=f"bold {COLORS['accent']}")
        t.append(" " * max(width - cell_width(title) - 3, 1) + "esc",
                 style="dim")
        t.append("\n")
        t.append("Search ", style=COLORS["accent"])
        hint = self.query or "type to filter..."
        t.append(truncate(hint, width - 9),
                 style="" if self.query else "dim")
        t.append(" \u258c", style=COLORS["accent"])
        t.append("\n\n")
        vis = self.visible_rows()
        if not vis:
            t.append("  no matches\n", style="dim")
        last_section = None
        for i, row in enumerate(vis):
            if row["section"] != last_section:
                t.append(row["section"] + "\n", style=COLORS["model"])
                last_section = row["section"]
            label = row["label"]
            value = truncate(str(row["get"](self)), max(width // 2, 8))
            gap = max(width - cell_width(label) - cell_width(value) - 5, 1)
            if i == self.cursor:
                band = COLORS["band"]
                t.append(f" {icons.glyph('dot')} ",
                         style=f"{COLORS['accent']} on {band}")
                t.append(label, style=f"bold on {band}")
                t.append(" " * gap + " ", style=f"on {band}")
                t.append(value, style=f"bold on {band}")
            else:
                t.append("   " + label, style="")
                t.append(" " * gap + " ", style="")
                t.append(value, style=COLORS["model"])
            t.append("\n")
        t.append("\n")
        t.append("change \u2190/\u2192", style="dim")
        t.append(" " * max(width - 12 - 1, 1))
        t.append("enter cycle", style=COLORS["text-faint"])
        return t

    # -- 交互 ---------------------------------------------------------- #
    def on_key(self, event: events.Key) -> None:
        vis = self.visible_rows()
        if event.key == "down" and vis:
            self.cursor = min(self.cursor + 1, len(vis) - 1)
        elif event.key == "up":
            self.cursor = max(self.cursor - 1, 0)
        elif event.key in ("left", "right") and vis:
            row = vis[min(self.cursor, len(vis) - 1)]
            self._cycle(row, -1 if event.key == "left" else 1)
        elif event.key == "enter" and vis:
            self._cycle(vis[self.cursor], 1)
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
