"""网关界面：启动/停止 + 状态查看。"""
from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C
from ..keys import wait_for_return
from ..menu import Menu, MenuItem


def run_gateway_screen(console: Console, copilot) -> None:
    from ...gateway import get_gateway, reset_gateway

    while True:
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 网关[/]")
        console.print()

        try:
            gw = get_gateway(copilot)
        except Exception as exc:
            console.print(f"  [err]✗ 网关初始化失败: {exc}[/]")
            time.sleep(1.5)
            return

        status = gw.status()
        running = status.get("running", False)

        # 状态表
        t = Table(box=None, show_header=False, padding=(0, 2))
        t.add_column(style="dim")
        t.add_column(style="bold")
        t.add_row("状态",
                  f"[{OK_C}]运行中[/]" if running
                  else f"[{DIM_C}]已停止[/]")
        t.add_row("地址", status.get("url") or "—")
        t.add_row("主机", str(status.get("host", "?")))
        t.add_row("端口", str(status.get("port", "?")))
        t.add_row("Token", "已设置" if status.get("token_set")
                  else "[dim]未设置[/]")
        if running:
            t.add_row("请求数", str(status.get("requests", 0)))
            t.add_row("错误数", str(status.get("errors", 0)))
            t.add_row("运行时长", f"{status.get('uptime', 0)}s")
        console.print(t)
        console.print()

        if running:
            url = status.get("url", "")
            console.print(
                f"  [dim]WebUI: [/][accent]{url}[/]"
                f"  [dim]（浏览器打开即可使用）[/]"
            )
            console.print()

        subtitle = (
            f"{'运行中' if running else '已停止'}"
            f"  ·  {status.get('url') or 'One Cedric Gateway'}"
            + (
                f"  ·  请求 {status.get('requests', 0)}"
                f"  ·  错误 {status.get('errors', 0)}"
                if running else ""
            )
        )
        if running:
            items = [
                MenuItem("s", "停止网关", "安全关闭本地 API 服务"),
                MenuItem("r", "刷新状态", "更新网关运行信息"),
                MenuItem("l", "查看最近日志", "查看近期 API 请求"),
                MenuItem("q", "返回", "回到主菜单"),
            ]
        else:
            items = [
                MenuItem("s", "启动网关", "启动本地 API 与 WebUI"),
                MenuItem("r", "刷新状态", "更新网关运行信息"),
                MenuItem("q", "返回", "回到主菜单"),
            ]

        choice = Menu(
            console, "网关操作", items, subtitle=subtitle
        ).run()
        if choice in (None, "q"):
            return

        if choice == "r":
            continue

        if choice == "s":
            if running:
                ok, msg = gw.stop()
                if ok:
                    console.print(f"  [ok]✓ {msg}[/]")
                else:
                    console.print(f"  [err]✗ {msg}[/]")
            else:
                host = str(copilot.config.get("gateway", {})
                            .get("host", "127.0.0.1"))
                port = int(copilot.config.get("gateway", {})
                            .get("port", 2043))
                token = str(copilot.config.get("gateway", {})
                             .get("token", ""))
                console.print(f"  [dim]启动中 {host}:{port} …[/]")
                with console.status(
                    f"[{ACCENT}]启动网关中…[/]", spinner="dots"
                ):
                    ok, msg = gw.start(host=host, port=port, token=token)
                if ok:
                    console.print(f"  [ok]✓ 已启动[/]")
                    console.print(f"  [dim]访问: [/][accent]{msg}[/]")
                else:
                    console.print(f"  [err]✗ {msg}[/]")
            time.sleep(1.0)
            continue

        if choice == "l" and running:
            # 日志
            logs = gw.recent_logs(20)
            console.clear()
            console.print()
            console.print(f"  [bold {BRAND}]◆ 最近日志[/]")
            console.print()
            if not logs:
                console.print("  [dim]（无）[/]")
            else:
                tbl = Table(box=None, padding=(0, 2))
                tbl.add_column("时间", style="dim")
                tbl.add_column("方法", style="dim")
                tbl.add_column("路径")
                tbl.add_column("状态", justify="right")
                tbl.add_column("耗时", justify="right", style="dim")
                for e in logs[-20:]:
                    ts = time.strftime("%H:%M:%S",
                                       time.localtime(e.get("ts", 0)))
                    status_code = e.get("status", 0)
                    sc = OK_C if 200 <= status_code < 300 else \
                         WARN_C if 300 <= status_code < 400 else ERR_C
                    tbl.add_row(ts, e.get("method", ""),
                                e.get("path", ""),
                                f"[{sc}]{status_code}[/]",
                                f"{e.get('duration', 0):.3f}s")
                console.print(tbl)
            console.print()
            wait_for_return(console)
            continue