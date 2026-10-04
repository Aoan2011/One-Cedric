"""REPL 输入框：像素小狗 + 元信息行 + GPL-3.0 页脚。"""
from __future__ import annotations

import re

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.text import Text

from .dog import dog_inline
from ..config import ACCENT, BRAND, OK_C, WARN_C


def human_tok(n) -> str:
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 10000:
        return f"{n/1000:.1f}K"
    if n < 1_000_000:
        return f"{n/1000:.0f}K"
    return f"{n/1_000_000:.1f}M"


def _fmt_cost(cost: float) -> str:
    if cost <= 0:
        return "免费"
    if cost < 0.01:
        return f"${cost:.5f}"
    if cost < 1:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _plain_dog(state: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", dog_inline(state, index=0))


def format_meta_line(*, model: str, turn: int, steps: int,
                     ctx_used: int, ctx_max: int,
                     cost: float, tok_speed: float,
                     cached_tok: int = 0,
                     total_in: int = 0,
                     total_out: int = 0,
                     extra: str = "") -> str:
    parts = [model or "?"]
    parts.append(f"第{turn}轮 {steps}步")
    if ctx_max:
        pct = ctx_used / max(ctx_max, 1) * 100
        parts.append(
            f"ctx {human_tok(ctx_used)}/{human_tok(ctx_max)} ({pct:.0f}%)"
        )
    else:
        parts.append(f"ctx {human_tok(ctx_used)}")
    if total_in or total_out:
        parts.append(f"tok {human_tok(total_in)}↑ {human_tok(total_out)}↓")
    if cached_tok > 0:
        parts.append(f"缓存 {human_tok(cached_tok)}")
    parts.append(_fmt_cost(cost))
    if tok_speed > 0:
        parts.append(f"{tok_speed:.1f}tok/s")
    if extra:
        parts.append(extra)
    return " · ".join(parts)


def ask_with_box(console: Console, *, state: str, model: str,
                 turn: int, steps: int, ctx_used: int, ctx_max: int,
                 cost: float, tok_speed: float = 0.0,
                 cached_tok: int = 0,
                 total_in: int = 0, total_out: int = 0,
                 extra: str = "",
                 animate: bool = True,
                 footer: str = "One Cedric · GPL-3.0") -> str:
    meta = format_meta_line(
        model=model, turn=turn, steps=steps,
        ctx_used=ctx_used, ctx_max=ctx_max,
        cost=cost, tok_speed=tok_speed,
        cached_tok=cached_tok,
        total_in=total_in, total_out=total_out,
        extra=extra,
    )

    status = {
        "idle": ("Ready", OK_C, "✓"),
        "busy": ("Working", ACCENT, "⟳"),
        "confirm": ("Needs your choice", WARN_C, "✋"),
        "error": ("Last action failed", WARN_C, "⚠"),
    }
    label, color, icon = status.get(state, status["idle"])
    panel_content = [
        Text(f"{_plain_dog(state)}  {icon}  {label}",
             style=f"bold {color}")]
    if ctx_max > 0:
        ratio = min(max(ctx_used / ctx_max, 0.0), 1.0)
        panel_content.append(Text("Context", style="dim"))
        panel_content.append(ProgressBar(
            total=100,
            completed=round(ratio * 100),
            width=min(32, max(12, console.width - 32)),
            complete_style=BRAND,
            finished_style=WARN_C if ratio >= 0.9 else BRAND,
            pulse_style=ACCENT,
        ))
    panel_content.append(Text(meta, style="dim"))
    panel_content.append(Text(footer, style="dim"))
    console.print(Panel(
        Group(*panel_content),
        title="[bold]One Cedric[/]",
        title_align="left",
        border_style=color,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    ))
    prompt = Text("  ❯ ", style=f"bold {BRAND}")

    try:
        line = console.input(prompt, markup=False)
    except (EOFError, KeyboardInterrupt):
        raise
    return line


def quick_ask(console: Console, message: str,
              state: str = "confirm") -> str:
    color_map = {
        "idle": OK_C,
        "busy": ACCENT,
        "confirm": WARN_C,
    }
    color = color_map.get(state, color_map["confirm"])
    prompt = Text()
    prompt.append(f"{_plain_dog(state)} ", style=f"bold {color}")
    prompt.append(message + " ", style="bold")
    try:
        return Console().input(prompt, markup=False).strip()
    except (EOFError, KeyboardInterrupt):
        return ""