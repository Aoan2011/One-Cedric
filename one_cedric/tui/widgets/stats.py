"""Shell C：全屏统计屏（对齐 OpenCode /stats）。

元素从上到下：``one-cedric / stats`` + 日期范围；渐变点阵 logo（屏够高
才有）；巨型渐变点阵数字（当前会话 tokens）；16 周活跃热力图（数据来自
本机会话文件的更新时间戳，样本太少时给一张确定性生成的演示图）；
streak / active days / sessions 三色统计行；右下角版本号。

纯终端绘制，不引任何图表依赖。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from random import Random

from rich.text import Text
from textual.widget import Widget

from ..design import cell_width
from ..theme import COLORS, LOGO_GRADIENT, VERSION, gradient_at
from .logo import gradient_rows

#: 5x7 大数字字模（支撑 tokens 缩写，如 6.4K / 60.8M）。
DIGITS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("M", "T", "W", "T", "F", "S", "S")
WEEKS = 16


def human_tokens(n: int) -> str:
    """6369 → '6.4K'；60_800_000 → '60.8M'（大数字只留一位小数）。"""
    if n >= 1_000_000_000_000:
        v, suffix = n / 1e12, "T"
    elif n >= 1_000_000_000:
        v, suffix = n / 1e9, "B"
    elif n >= 1_000_000:
        v, suffix = n / 1e6, "M"
    elif n >= 1_000:
        v, suffix = n / 1e3, "K"
    else:
        return str(max(n, 0))
    text = f"{v:.1f}".rstrip("0").rstrip(".")
    return text + suffix


def big_rows(text: str, cell: str = "\u2588\u2588") -> list[list[tuple[str, str]]]:
    """把短字符串渲染成渐变大字（每行是 [(片段, 颜色), ...]）。"""
    glyphs = [DIGITS.get(ch, DIGITS[" "]) for ch in text]
    span = max(len(glyphs) - 1, 1)
    rows: list[list[tuple[str, str]]] = []
    for r in range(7):
        segs: list[tuple[str, str]] = []
        for gi, glyph in enumerate(glyphs):
            color = gradient_at(gi / span)
            seg = "".join(cell if bit == "1" else "  " for bit in glyph[r])
            segs.append((seg, color))
            segs.append(("  ", color))
        rows.append(segs)
    return rows


class StatsScreen(Widget):
    """全屏统计面板（palette 'stats' / ctrl+s 的落点）。"""

    can_focus = True

    # -- 数据 ---------------------------------------------------------- #
    def _activity(self) -> Counter:
        """按天聚合会话活跃度（本机会话时间戳；样本太少给演示图）。"""
        days: Counter = Counter()
        for s in self.app.sessions:
            ts = s.get("updated") or 0
            if not ts:
                continue
            try:
                d = datetime.fromtimestamp(ts).date()
            except (ValueError, OSError, OverflowError):
                continue
            days[d] += max(int(s.get("count") or 1), 1)
        if len(days) < 3:                    # 空数据/演示：确定性生成
            rng = Random(7)
            today = datetime.now().date()
            for i in range(120):
                if rng.random() < 0.3:
                    days[today - timedelta(days=i)] += rng.choice([1, 1, 2, 3])
        return days

    @staticmethod
    def _window():
        today = datetime.now().date()
        start = today - timedelta(days=today.weekday() + 7 * (WEEKS - 1))
        return start, today

    # -- 渲染 ---------------------------------------------------------- #
    def render(self) -> Text:
        width = max(self.size.width, 40)
        height = max(self.size.height, 10)
        out = Text()
        # 顶栏：one-cedric / stats  +  日期范围
        left = "one-cedric / stats"
        right = self._range_label()
        out.append(left, style=COLORS["accent"])
        out.append(" " * max(width - len(left) - len(right) - 1, 1) + right,
                   style="dim")
        out.append("\n\n")
        # 居中块
        block: list[list[tuple[str, str]]] = []
        logo = gradient_rows("CEDRIC")
        logo_w = max(sum(cell_width(s) for s, _ in row) for row in logo)
        if height >= 32 and logo_w + 4 <= width:
            block.extend(logo)
            block.append([])
        block.extend(big_rows(human_tokens(self.app.state.tokens)))
        block.append([("T O K E N S", "dim")])
        block.append([])
        block.extend(self._heatmap_lines())
        block.append([])
        block.append(self._stats_line())
        for segs in block:
            total = sum(cell_width(s) for s, _ in segs)
            out.append(" " * max((width - total) // 2, 0))
            for seg, style in segs:
                out.append(seg, style=style)
            out.append("\n")
        foot = f"one-cedric v{VERSION}"
        out.append("\n" + " " * max(width - len(foot) - 1, 1) + foot,
                   style=COLORS["text-faint"])
        return out

    def _range_label(self) -> str:
        start, today = self._window()
        if start.year != today.year:
            return (f"{MONTHS[start.month - 1]} {start.year} "
                    f"\u2013 {MONTHS[today.month - 1]} {today.year}")
        return (f"{MONTHS[start.month - 1]} \u2013 "
                f"{MONTHS[today.month - 1]} {today.year}")

    def _heatmap_lines(self) -> list[list[tuple[str, str]]]:
        days = self._activity()
        start, today = self._window()
        lines: list[list[tuple[str, str]]] = []
        # 月份标签行（颜色沿渐变换色，和截图一致）
        segs: list[tuple[str, str]] = [("  ", "")]
        x = 2
        prev_month = -1
        for col in range(WEEKS):
            mon = start + timedelta(weeks=col)
            if col == 0 or mon.month != prev_month:
                label = MONTHS[mon.month - 1]
                target = 2 + col * 2
                segs.append((" " * max(target - x, 0), ""))
                segs.append((label, gradient_at(col / max(WEEKS - 1, 1))))
                x = target + len(label)
            prev_month = mon.month
        lines.append(segs)
        for row in range(7):
            segs = [(WEEKDAYS[row] + " ", "dim")]
            for col in range(WEEKS):
                d = start + timedelta(weeks=col, days=row)
                count = days.get(d, 0)
                if d > today or count <= 0:
                    segs.append(("\u00b7", COLORS["text-faint"]))
                elif count == 1:
                    segs.append(("\u25a0", COLORS["accent-deep"]))
                elif count == 2:
                    segs.append(("\u25a0", COLORS["accent"]))
                else:
                    segs.append(("\u25a0", LOGO_GRADIENT[0]))
                segs.append((" ", ""))
            lines.append(segs)
        return lines

    def _stats_line(self) -> list[tuple[str, str]]:
        days = self._activity()
        active = {d for d, c in days.items() if c > 0}
        best = run = 0
        if active:
            cur, end = min(active), max(active)
            d = cur
            while d <= end:
                run = run + 1 if d in active else 0
                best = max(best, run)
                d += timedelta(days=1)
        sessions = len(self.app.sessions)
        return [
            (f"{best} days best streak", LOGO_GRADIENT[0]),
            ("    ", ""),
            (f"{len(active)} active days", LOGO_GRADIENT[2]),
            ("    ", ""),
            (f"{sessions} sessions", LOGO_GRADIENT[3]),
        ]
