"""关于界面：仅展示项目信息（版本 / 作者 / 仓库 / 协议）。

依赖与运行环境检查已拆分到 diagnose 界面（诊断）。
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...config import (
    BRAND, ACCENT, DIM_C, BETA_VERSION,
    PROJECT_NAME, PROJECT_AUTHOR, PROJECT_REPO, PROJECT_LICENSE,
)
from ..keys import wait_for_return


def run_about_screen(console: Console, copilot) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ {PROJECT_NAME} {BETA_VERSION}[/]")
    console.print()

    console.print(Panel(
        f"[dim]{PROJECT_NAME} —— An AI agent for beginners[/]\n"
        f"[dim]版本: [/][accent]{BETA_VERSION}[/]\n"
        f"[dim]开发: [/][accent]{PROJECT_AUTHOR}[/][dim] 主持开发[/]\n"
        f"[dim]仓库: [/][accent]{PROJECT_REPO}[/]\n"
        f"[dim]协议: [/][accent]{PROJECT_LICENSE}[/]",
        title=f"[bold {BRAND}]关于[/]",
        border_style=BRAND,
        padding=(0, 1),
        expand=False,
    ))
    console.print()

    tbl = Table(box=None, padding=(0, 1))
    tbl.add_column("项目", style="dim")
    tbl.add_column("当前值", style="accent")
    tbl.add_row("模型", str(copilot.model))
    tbl.add_row("API 地址", str(copilot.host or ""))
    tbl.add_row("工作目录", str(copilot.root))
    tbl.add_row("会话 ID", str(copilot.session_id)[:12])
    console.print(tbl)
    console.print()

    console.print("  [dim]依赖与运行环境检查 → [/]"
                  f"[accent]主菜单 · 诊断（diagnose）[/]")
    console.print("  [dim]许可证全文 → [/]"
                  f"[accent]python -m one_cedric --license[/]")
    console.print()
    wait_for_return(console)
