"""高级进度/动画组件。

包含：
  ProgressMatrix   - 多任务并行矩阵
  Waveform         - 流式波形
  MetricDashboard  - 实时速率仪表盘
  Celebrate        - 奖励反馈
  RetryStatus      - 失败反转重试
"""
from __future__ import annotations

import shutil
import threading
import time
from collections import deque
from typing import Callable

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from ..config import (
    BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, TOOL_C,
)
from .accessibility import motion_enabled


def _term_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def _human_size(n: float) -> str:
    if n <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_dur(sec: float) -> str:
    if sec <= 0:
        return "?"
    if sec < 60:
        return f"{sec:.0f}s"
    if sec < 3600:
        return f"{sec / 60:.1f}m"
    return f"{sec / 3600:.1f}h"


BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
PULSE = "●◐◑◒◓◔◕○"
WAVE_BLOCKS = " ▁▂▃▄▅▆▇█"
SPARK_CHARS = " ▏▎▍▌▋▊▉█"


class ProgressMatrix:
    FRAME_INTERVAL = 0.08

    def __init__(self, console: Console, title: str = "运行中",
                 max_visible: int = 8):
        self.console = console
        self.title = title
        self.max_visible = max_visible
        self._tasks: dict = {}
        self._order: list = []
        self._lock = threading.Lock()
        self._live: Live | None = None
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None
        self._frame = 0
        self._next_id = 0
        self._animate = False

    def __enter__(self):
        self._animate = motion_enabled(self.console)
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=False,
            auto_refresh=False,
            vertical_overflow="visible",
        )
        self._live.__enter__()
        self._stop.clear()
        if self._animate:
            self._ticker = threading.Thread(target=self._tick, daemon=True)
            self._ticker.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._ticker:
            try:
                self._ticker.join(timeout=1)
            except Exception:
                pass
        if self._live:
            try:
                self._live.__exit__(*exc)
            except Exception:
                pass

    def _tick(self):
        while self._animate and not self._stop.is_set():
            self._frame += 1
            try:
                if self._live:
                    self._live.update(self._render(), refresh=True)
            except Exception:
                pass
            if self._stop.wait(self.FRAME_INTERVAL):
                return

    def add(self, name: str, target: str = "",
            progress: float = 0.0) -> int:
        with self._lock:
            tid = self._next_id
            self._next_id += 1
            self._tasks[tid] = {
                "name": name,
                "target": target[:40],
                "progress": progress,
                "status": "running",
                "start": time.time(),
            }
            self._order.append(tid)
        if self._live and not self._animate:
            self._live.update(self._render(), refresh=True)
        return tid

    def update(self, tid: int, progress: float | None = None,
               target: str = "", status: str = "running",
               summary: str = ""):
        with self._lock:
            t = self._tasks.get(tid)
            if not t:
                return
            if progress is not None:
                t["progress"] = max(0.0, min(1.0, progress))
            if target:
                t["target"] = target[:40]
            if summary:
                t["summary"] = summary
            if status:
                t["status"] = status
        if self._live and not self._animate:
            self._live.update(self._render(), refresh=True)

    def done(self, tid: int, summary: str = "", status: str = "ok"):
        with self._lock:
            t = self._tasks.get(tid)
            if t:
                t["status"] = status
                t["progress"] = 1.0
                t["summary"] = summary[:60]
                t["end"] = time.time()
        if self._live and not self._animate:
            self._live.update(self._render(), refresh=True)

    def remove(self, tid: int):
        with self._lock:
            self._tasks.pop(tid, None)
            if tid in self._order:
                self._order.remove(tid)

    def _render(self) -> RenderableType:
        with self._lock:
            tasks = [self._tasks[t] for t in self._order
                     if t in self._tasks]
            running = [t for t in tasks if t["status"] == "running"]

        show = tasks[: self.max_visible]
        hidden = len(tasks) - len(show)

        rows = []
        spinner = BRAILLE[self._frame % len(BRAILLE)]

        for t in show:
            status = t["status"]
            if status == "ok":
                icon = f"[bold {OK_C}]✓[/]"
            elif status == "error":
                icon = f"[bold {ERR_C}]✗[/]"
            elif status in ("blocked", "rejected"):
                icon = f"[bold {WARN_C}]⊘[/]"
            else:
                icon = f"[bold {ACCENT}]{spinner}[/]"

            elapsed = t.get("end", time.time()) - t["start"]
            p = t.get("progress", 0.0)
            bar_w = 10
            filled = int(p * bar_w)
            bar = "▰" * filled + "▱" * (bar_w - filled)

            name = t["name"][:18]
            target = t["target"][:32]
            summary = t.get("summary", "")

            line = Text()
            line.append("  ")
            line.append_text(Text.from_markup(icon))
            line.append(f" {name:<18} ", style=f"bold {TOOL_C}")
            line.append(f"{target:<32}", style="dim")
            line.append(f" {bar} ", style=ACCENT)
            if summary:
                line.append(summary, style="dim")
            line.append(f"  {elapsed:.1f}s", style="dim")
            rows.append(line)

        if hidden > 0:
            rows.append(Text(f"  ... 还有 {hidden} 个任务", style="dim"))

        title_line = Text()
        title_line.append("  ╭─ ", style="dim")
        title_line.append(self.title, style=f"bold {BRAND}")
        completed = len(tasks) - len(running)
        title_line.append(
            f" ({len(running)} running · {completed} done) ", style="dim"
        )
        title_line.append("─" * 30, style="dim")
        title_line.append("╮", style="dim")

        return Group(title_line, *rows)


class Waveform:
    def __init__(self, label: str = "", max_points: int = 40,
                 unit: str = "tok/s", color: str = ACCENT):
        self.label = label
        self.max_points = max_points
        self.unit = unit
        self.color = color
        self._values: deque = deque(maxlen=max_points)
        self._lock = threading.Lock()

    def push(self, value: float):
        with self._lock:
            self._values.append(max(0.0, float(value)))

    def values(self) -> list:
        with self._lock:
            return list(self._values)

    def render(self, width: int | None = None) -> Text:
        with self._lock:
            vals = list(self._values)

        if not vals:
            return Text(f"{self.label}  等待数据…", style="dim")

        if width is None:
            width = min(self.max_points, 40)

        if len(vals) < width:
            vals = [0.0] * (width - len(vals)) + vals
        else:
            vals = vals[-width:]

        mx = max(vals) if vals else 0
        if mx <= 0:
            mx = 1

        chars = []
        for v in vals:
            idx = int(v / mx * (len(WAVE_BLOCKS) - 1))
            chars.append(WAVE_BLOCKS[max(0, min(idx,
                                                len(WAVE_BLOCKS) - 1))])

        avg = sum(vals) / len(vals)
        cur = vals[-1]

        if mx > 0:
            ratio = cur / mx
            if ratio >= 0.66:
                color = OK_C
            elif ratio >= 0.33:
                color = WARN_C
            else:
                color = ERR_C
        else:
            color = self.color

        t = Text()
        if self.label:
            t.append(f"{self.label}  ", style="dim")
        t.append(f"{cur:.1f}", style=f"bold {color}")
        t.append(f" {self.unit}  ", style="dim")
        t.append(f"avg {avg:.1f}  ", style="dim")
        t.append("".join(chars), style=color)
        return t


class MetricDashboard:
    FRAME_INTERVAL = 0.1

    def __init__(self, console: Console, title: str = "任务",
                 total: float = 0.0, unit: str = ""):
        self.console = console
        self.title = title
        self.total = total
        self.unit = unit
        self._progress = 0.0
        self._start = time.time()
        self._metrics: dict = {}
        self._footer = ""
        self._lock = threading.Lock()
        self._live: Live | None = None
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None
        self._frame = 0

    def __enter__(self):
        self._live = Live(
            self._render(), console=self.console,
            refresh_per_second=10, transient=True,
            vertical_overflow="visible",
        )
        self._live.__enter__()
        self._stop.clear()
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._ticker:
            try:
                self._ticker.join(timeout=1)
            except Exception:
                pass
        if self._live:
            try:
                self._live.__exit__(*exc)
            except Exception:
                pass

    def _tick(self):
        while not self._stop.is_set():
            self._frame += 1
            try:
                if self._live:
                    self._live.update(self._render())
            except Exception:
                pass
            if self._stop.wait(self.FRAME_INTERVAL):
                return

    def set_progress(self, p: float):
        with self._lock:
            self._progress = max(0.0, min(1.0, p))

    def set_metric(self, name: str, value: str = "",
                   waveform: Waveform | None = None):
        with self._lock:
            self._metrics[name] = {"value": value, "waveform": waveform}

    def set_footer(self, text: str):
        with self._lock:
            self._footer = text

    def _render(self) -> RenderableType:
        with self._lock:
            p = self._progress
            metrics = dict(self._metrics)
            footer = self._footer

        w = min(50, max(20, _term_width(80) - 30))
        filled = int(p * w)
        bar = "█" * filled + "░" * (w - filled)
        spinner = BRAILLE[self._frame % len(BRAILLE)]

        lines = []
        lines.append(Text.from_markup(
            f"  [dim]{spinner}[/] [bold {BRAND}]{self.title}[/]"
        ))
        lines.append(Text.from_markup(
            f"  [{ACCENT}]{bar}[/]  [bold {OK_C}]{p * 100:.1f}%[/]"
        ))
        lines.append(Text(""))

        for name, m in metrics.items():
            line = Text()
            line.append(f"  {name:<8} ", style="dim")
            if m.get("waveform"):
                wf_txt = m["waveform"].render(width=30)
                line.append_text(wf_txt)
            else:
                line.append(m["value"],
                            style=f"bold {self._metric_color(name)}")
            lines.append(line)

        if footer:
            lines.append(Text(""))
            lines.append(Text(f"  {footer}", style="dim"))

        from rich import box as _box
        return Panel(
            Group(*lines),
            title="", border_style=DIM_C,
            box=_box.ROUNDED,
            padding=(0, 0), expand=False,
        )

    def _metric_color(self, name: str) -> str:
        n = name.lower()
        if "cpu" in n or "内存" in n or "memory" in n:
            return WARN_C
        if "速率" in n or "speed" in n or "速度" in n:
            return OK_C
        return ACCENT


CELEBRATION_FRAMES = [
    "✧･ﾟ: *✧･ﾟ:*",
    "*✧･ﾟ: ✧･ﾟ:*",
    "･ﾟ: *✧･ﾟ:*✧",
]

DOG_HAPPY = "▐^ᴥ^▌"
DOG_LOVE = "▐♥ᴥ♥▌"
DOG_WINK = "▐^ᴥ-▌"


def celebrate(console: Console, message: str,
              duration: float = 0.5,
              dog_face: str = DOG_HAPPY,
              sparkle: bool = True,
              stats: str = "") -> None:
    GREEN = f"bold {OK_C}"
    if sparkle:
        for i, frame in enumerate(CELEBRATION_FRAMES):
            line = Text()
            line.append(f"  {dog_face}  ", style=GREEN)
            line.append(message, style=GREEN)
            line.append(f"  {frame}", style=f"dim {ACCENT}")
            if stats and i == len(CELEBRATION_FRAMES) - 1:
                console.print(line)
                console.print(Text(f"     {stats}", style="dim"))
            else:
                console.print(line)
            time.sleep(duration / len(CELEBRATION_FRAMES))
        return

    console.print(Text.from_markup(
        f"  [{GREEN}]{dog_face}  {message}[/]"
    ))
    if stats:
        console.print(Text(f"     {stats}", style="dim"))


DOG_ERROR = "▐✕ᴥ✕▌"
DOG_HOPEFUL = "▐•ᴥ•▌"


def retry_with_feedback(console: Console, func: Callable,
                        max_retries: int = 3,
                        retry_delay: float = 1.5,
                        label: str = "",
                        show_error: bool = True) -> tuple:
    attempt = 0
    last_err = ""

    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            ok, result = func()
            if ok:
                celebrate(console, label or "完成", duration=0.3)
                return True, result, 1
            last_err = str(result)
            if show_error:
                console.print(Text.from_markup(
                    f"  [bold {ERR_C}]{DOG_ERROR}  失败[/]"
                ))
                console.print(Text(f"     {last_err[:100]}", style="dim"))
        else:
            console.print(Text.from_markup(
                f"  [dim]{DOG_HOPEFUL}  自动重试第 {attempt} 次[/]"
            ))

            t0 = time.time()
            while time.time() - t0 < retry_delay:
                bar_w = 14
                p = (time.time() - t0) / retry_delay
                filled = int(p * bar_w)
                bar = "█" * filled + "░" * (bar_w - filled)
                console.print(
                    f"\r     [dim]{bar}[/]", end="", highlight=False)
                time.sleep(0.08)
            console.print()

            ok, result = func()
            if ok:
                stats = f"（第 {attempt} 次尝试成功）"
                celebrate(console, label or "完成",
                          duration=0.4, stats=stats)
                return True, result, attempt
            last_err = str(result)
            if show_error:
                console.print(Text.from_markup(
                    f"  [dim]{DOG_ERROR}  仍失败[/]"
                ))

    return False, last_err, attempt