"""Shell C：设计令牌（单一来源仍是一处）。

TUI 不能读 CSS，但也不该把颜色散在每个 widget 里 —— 这里等价于
``webui/design/tokens.json`` 的终端版：一套 CJK 感知的文字宽度/截断工具
+ 一套语义颜色名（Textual 的 CSS 里用 ``$accent`` 这种变量即可，颜色值
只在这里定义一次）。
"""
from __future__ import annotations

import unicodedata

# 颜色的唯一来源挪到 theme.py（对齐 OpenCode token 体系）；这里保留
# ``COLORS`` 这个名字做兼容导出，widget 仍可 ``from .design import COLORS``。
from .theme import COLORS  # noqa: F401  (re-export)


def cell_width(text: str) -> int:
    """按终端显示宽度算长度（CJK/emoji 占 2 列）。

    len() 在中文下会算少一半，用它做对齐会让所有中文列表歪掉 —— 这是
    终端 UI 最常见的翻车点，所以统一走这里。
    """
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """按显示宽度截断，超长补省略号（永远不会超过 width 列）。"""
    if width <= 0:
        return ""
    if cell_width(text) <= width:
        return text
    keep = width - cell_width(ellipsis)
    out = []
    used = 0
    for ch in text:
        w = cell_width(ch)
        if used + w > keep:
            break
        out.append(ch)
        used += w
    return "".join(out) + ellipsis


def pad(text: str, width: int, align: str = "left") -> str:
    """按显示宽度补空格（左/右/居中）。"""
    text = truncate(text, width)
    fill = max(width - cell_width(text), 0)
    if align == "right":
        return " " * fill + text
    if align == "center":
        left = fill // 2
        return " " * left + text + " " * (fill - left)
    return text + " " * fill
