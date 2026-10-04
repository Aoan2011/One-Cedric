"""占位界面。"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from ..keys import wait_for_return


def run_placeholder(console: Console, copilot, name: str) -> None:
    console.clear()
    console.print()
    console.print(Panel(
        f"[dim]{name} 功能开发中[/]",
        border_style="dim",
        padding=(1, 2),
    ))
    console.print()
    wait_for_return(console)