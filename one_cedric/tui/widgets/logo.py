"""Shell C：首页的巨型点阵 ASCII logo。

OpenCode 首页中央是一块很大的渐变点阵字。终端里没有图片，只能用
``█`` 拼：内置一套 5x7 点阵字模（只含用到的字母），每个点渲染成两个
``█``，整个词按 :data:`theme.LOGO_GRADIENT` 逐字母染色（橙→粉→紫→蓝，
和截图一致的渐变观感）。

字模刻意只收录用到的字母 —— 没有字库依赖，也不会在 Windows 编码上翻车。
"""
from __future__ import annotations

from rich.text import Text

from ..theme import COLORS, gradient_at

#: 5x7 点阵字模（1 = 亮点）。只收录 logo 需要的字母。
FONT = {
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "N": ["10001", "11001", "11001", "10101", "10011", "10011", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}


def dot_matrix(text: str, cell: str = "\u2588\u2588") -> list[str]:
    """把 ``text`` 渲染成点阵行（每个亮点 = 两个块字符）。"""
    glyphs = [FONT.get(ch.upper(), FONT[" "]) for ch in text]
    rows: list[str] = []
    for r in range(7):
        parts = []
        for glyph in glyphs:
            parts.append("".join(cell if bit == "1" else "  "
                                 for bit in glyph[r]))
            parts.append("  ")          # 字母间距
        rows.append("".join(parts).rstrip())
    return rows


def gradient_rows(text: str, cell: str = "\u2588\u2588") -> list[list[tuple[str, str]]]:
    """按字母渐变的点阵行：每行是 ``[(片段, 颜色), ...]``。

    调用方负责加左右留白；每行的总显示宽度一致，便于居中。
    """
    glyphs = [FONT.get(ch.upper(), FONT[" "]) for ch in text]
    span = max(len(glyphs) - 1, 1)
    rows: list[list[tuple[str, str]]] = []
    for r in range(7):
        segs: list[tuple[str, str]] = []
        for gi, glyph in enumerate(glyphs):
            color = gradient_at(gi / span)
            seg = "".join(cell if bit == "1" else "  " for bit in glyph[r])
            segs.append((seg, color))
            segs.append(("  ", color))  # 字母间距
        rows.append(segs)
    return rows


def logo_text(text: str = "CEDRIC") -> Text:
    """单色点阵 logo 的 rich 文本（兼容旧调用；首页已换用渐变版）。"""
    t = Text()
    for line in dot_matrix(text):
        t.append(line + "\n", style=COLORS["accent"])
    return t
