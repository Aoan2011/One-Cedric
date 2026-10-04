"""统一 UI 主题工厂。

所有 Panel / Table / Tree 都从这里生成，保证视觉一致。
"""
from __future__ import annotations

from rich import box
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..config import (
    BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C,
    TOOL_C, USER_C, PLAN_C, THEME,
)


# ── Panel 语义类型 ────────────────────────────────────────────────────

PANEL_KINDS = {
    "info":    {"border": ACCENT,   "title_style": f"bold {ACCENT}"},
    "ok":      {"border": OK_C,     "title_style": f"bold {OK_C}"},
    "success": {"border": OK_C,     "title_style": f"bold {OK_C}"},
    "warn":    {"border": WARN_C,   "title_style": f"bold {WARN_C}"},
    "error":   {"border": ERR_C,    "title_style": f"bold {ERR_C}"},
    "err":     {"border": ERR_C,    "title_style": f"bold {ERR_C}"},
    "plan":    {"border": PLAN_C,   "title_style": f"bold {PLAN_C}"},
    "tool":    {"border": TOOL_C,   "title_style": f"bold {TOOL_C}"},
    "user":    {"border": USER_C,   "title_style": f"bold {USER_C}"},
    "brand":   {"border": BRAND,    "title_style": f"bold {BRAND}"},
    "dim":     {"border": DIM_C,    "title_style": f"bold {DIM_C}"},
    "neutral": {"border": "white",  "title_style": "bold white"},
}


def panel(content, title: str = "", kind: str = "info",
          subtitle: str = "", expand: bool = False,
          padding=(0, 1)):
    """统一风格的 Panel。

    content 可以是 str / Text / Group / Markdown / renderable
    kind: info / ok / warn / error / plan / tool / user / brand / dim / neutral
    """
    spec = PANEL_KINDS.get(kind, PANEL_KINDS["info"])

    if isinstance(content, str):
        body = Text(content)
    else:
        body = content

    return Panel(
        body,
        title=f"[{spec['title_style']}]{title}[/]" if title else "",
        title_align="left",
        subtitle=subtitle,
        subtitle_align="right",
        border_style=spec["border"],
        box=box.ROUNDED,
        padding=padding,
        expand=expand,
    )


def panel_markdown(md_text: str, title: str = "", kind: str = "info"):
    """Markdown 内容的 Panel。"""
    spec = PANEL_KINDS.get(kind, PANEL_KINDS["info"])
    return Panel(
        Markdown(md_text, code_theme="monokai"),
        title=f"[{spec['title_style']}]{title}[/]" if title else "",
        title_align="left",
        border_style=spec["border"],
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    )


# ── Table ────────────────────────────────────────────────────────────

def table(*columns, title: str = "", show_header: bool = True,
          box_style=None):
    """统一风格的 Table。

    用法：
        t = theme.table("列1", "列2", title="标题")
        t.add_row("值1", "值2")
    """
    t = Table(
        box=box_style or box.SIMPLE,
        header_style=f"bold {BRAND}",
        title=title,
        title_justify="left",
        title_style=f"bold {BRAND}",
        show_header=show_header,
        padding=(0, 1),
    )
    for col in columns:
        if isinstance(col, tuple):
            name, kwargs = col
            t.add_column(name, **kwargs)
        else:
            t.add_column(str(col))
    return t


def kv_table(pairs, title: str = "", key_style="dim",
             value_style=""):
    """键值对表格：无表头，两列。"""
    t = Table(
        box=box.SIMPLE,
        show_header=False,
        title=title,
        title_justify="left",
        title_style=f"bold {BRAND}",
        padding=(0, 2),
    )
    t.add_column(style=key_style or "dim")
    t.add_column(style=value_style or "")
    for k, v in pairs:
        t.add_row(str(k), v if hasattr(v, "__rich__") or isinstance(v, Text)
                  else str(v))
    return t


# ── Tree ─────────────────────────────────────────────────────────────

def tree(label: str, style: str = ""):
    """统一风格的 Tree。"""
    return Tree(
        label,
        guide_style=style or DIM_C,
        hide_root=False,
    )


# ── 快捷文本 ─────────────────────────────────────────────────────────

def text_ok(s: str) -> Text:
    return Text(s, style=f"bold {OK_C}")


def text_err(s: str) -> Text:
    return Text(s, style=f"bold {ERR_C}")


def text_warn(s: str) -> Text:
    return Text(s, style=f"bold {WARN_C}")


def text_dim(s: str) -> Text:
    return Text(s, style=DIM_C)


def text_accent(s: str) -> Text:
    return Text(s, style=ACCENT)


def text_brand(s: str) -> Text:
    return Text(s, style=f"bold {BRAND}")


# ── 状态图标 ─────────────────────────────────────────────────────────

STATUS_ICONS = {
    "ok":      (OK_C, "✓"),
    "success": (OK_C, "✓"),
    "warn":    (WARN_C, "⚠"),
    "error":   (ERR_C, "✗"),
    "err":     (ERR_C, "✗"),
    "info":    (ACCENT, "ℹ"),
    "skip":    (DIM_C, "⊘"),
    "running": (ACCENT, "⟳"),
}


def status_icon(kind: str) -> str:
    """返回带颜色的状态图标 markup。"""
    color, icon = STATUS_ICONS.get(kind, (DIM_C, "·"))
    return f"[bold {color}]{icon}[/]"


def status_line(kind: str, message: str) -> Text:
    """'✓ 消息' 这类状态行。"""
    color, icon = STATUS_ICONS.get(kind, (DIM_C, "·"))
    t = Text()
    t.append(f"  {icon} ", style=f"bold {color}")
    t.append(message)
    return t


# ── 水平分隔 ─────────────────────────────────────────────────────────

def divider(width: int = 60, style: str = "", char: str = "─"):
    """一条横线。"""
    return Text(char * width, style=style or DIM_C)


def header(text: str, width: int = 60):
    """带分隔线的标题。"""
    return Group(
        Text(f"  {text}", style=f"bold {BRAND}"),
        divider(width),
    )