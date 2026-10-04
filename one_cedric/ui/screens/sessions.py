"""会话管理：上下切换 + 快速恢复 + 完整恢复。"""
from __future__ import annotations

import time
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, TOOL_C
from ...storage import list_session_files, delete_session_file
from ..menu import selection_progress


def _session_summary(s: dict) -> dict:
    msgs = s.get("messages", [])
    n_user = sum(1 for m in msgs if m.get("role") == "user")
    n_total = len(msgs)
    tools = 0
    for m in msgs:
        tools += len(m.get("tool_calls") or [])
    title = s.get("title") or "（未命名）"
    updated = s.get("updated_at", 0)
    model = s.get("model", "?")
    root = s.get("root", "")
    return {
        "id": s.get("id", ""),
        "title": title,
        "model": model,
        "root": root,
        "turns": n_user,
        "messages": n_total,
        "tools": tools,
        "updated": updated,
        "size": len(msgs),
    }


def run_sessions_screen(console, copilot) -> None:
    from ..keys import (
        read_key, KEY_UP, KEY_DOWN, KEY_ENTER, KEY_ESC,
        KEY_LEFT, KEY_RIGHT, has_readchar, wait_for_return,
    )

    root = copilot.root
    sessions_raw = list_session_files(root=root)
    if not sessions_raw:
        console.clear()
        console.print()
        console.print(f"  [dim]当前工作目录下没有已保存的会话。[/]")
        wait_for_return(console)
        return

    summaries = [_session_summary(s) for s in sessions_raw]
    summaries.sort(key=lambda x: x["updated"], reverse=True)

    idx = 0
    search = ""

    def _filtered():
        if not search:
            return summaries
        q = search.lower()
        return [x for x in summaries
                if q in x["title"].lower() or q in x["id"].lower()]

    while True:
        items = _filtered()
        if not items:
            idx = 0
        elif idx >= len(items):
            idx = len(items) - 1

        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 会话管理[/]")
        console.print(
            f"  [dim]共 {len(summaries)} 个 · 当前 {copilot.session_id}[/]"
        )
        if search:
            console.print(f"  [dim]搜索: [/][accent]{search}[/]")
        console.print()

        if not items:
            console.print("  [dim]（无匹配）[/]")
        else:
            win = 9
            lo = max(0, idx - win)
            hi = min(len(items), idx + win + 1)
            for i in range(lo, hi):
                s = items[i]
                active = (i == idx)
                is_current = (s["id"] == copilot.session_id)
                marker = "▸" if active else " "
                title = s["title"]
                if is_current:
                    title = f"[bold {OK_C}]●[/] {title}"
                ts = time.strftime("%m-%d %H:%M",
                                   time.localtime(s["updated"]))
                line = (
                    f"  [bold {BRAND}]{marker}[/] "
                    f"{title[:42]:<42} "
                    f"[dim]{s['model'][:18]:<18}[/] "
                    f"[dim]{s['turns']}轮 {s['tools']}工具[/] "
                    f"[dim]{ts}[/]"
                )
                if active:
                    console.print(f"[reverse]{line}[/]")
                else:
                    console.print(line)

            cur = items[idx] if items else None
            if cur:
                console.print()
                detail = [
                    f"[dim]ID:[/] {cur['id']}",
                    f"[dim]根目录:[/] {cur['root']}",
                    f"[dim]消息:[/] {cur['messages']} 条 "
                    f"（{cur['turns']} 轮对话）",
                    f"[dim]模型:[/] {cur['model']}",
                ]
                console.print(Panel(
                    Text.from_markup("\n".join(detail)),
                    title="[bold]详情[/]", title_align="left",
                    border_style=DIM_C, box=box.ROUNDED,
                    padding=(0, 1), expand=False,
                ))

        console.print()
        if items:
            console.print(selection_progress(idx, len(items)))
        console.print(
            f"  [dim]↑↓←→ 选择 · [/]"
            f"[accent]Enter[/][dim] 恢复 · [/]"
            f"[accent]d[/][dim] 删除 · [/]"
            f"[accent]/[/][dim] 搜索 · [/]"
            f"[accent]Esc[/][dim]/[/][accent]q[/][dim] 返回[/]"
        )

        if not has_readchar():
            try:
                ans = console.input(
                    "  [dim]会话名称或 ID / q >[/] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if ans.lower() in ("q", "back", ""):
                return
            if ans == "/":
                try:
                    search = console.input("  [dim]搜索: [/]").strip()
                except (EOFError, KeyboardInterrupt):
                    search = ""
                continue
            if ans == "d" and items:
                _do_delete(console, copilot, items[idx])
                sessions_raw = list_session_files(root=root)
                summaries = [_session_summary(s) for s in sessions_raw]
                summaries.sort(key=lambda x: x["updated"], reverse=True)
                continue
            match = next((session for session in items
                          if ans.casefold() in (
                              session["id"].casefold(),
                              session["title"].casefold(),
                          )), None)
            if match:
                _do_resume(console, copilot, match)
                return
            continue

        k = read_key()
        if k in (KEY_UP, KEY_LEFT):
            idx = max(0, idx - 1)
        elif k in (KEY_DOWN, KEY_RIGHT):
            idx = min(len(items) - 1, idx + 1)
        elif k == KEY_ENTER:
            if items:
                _do_resume(console, copilot, items[idx])
                return
        elif k in (KEY_ESC, "q"):
            return
        elif k == "/":
            try:
                search = console.input("  [dim]搜索: [/]").strip()
            except (EOFError, KeyboardInterrupt):
                search = ""
        elif k == "d":
            if items:
                _do_delete(console, copilot, items[idx])
                sessions_raw = list_session_files(root=root)
                summaries = [_session_summary(s) for s in sessions_raw]
                summaries.sort(key=lambda x: x["updated"], reverse=True)
        elif k == "j":
            idx = min(len(items) - 1, idx + 1)
        elif k == "k":
            idx = max(0, idx - 1)


def _do_delete(console, copilot, s: dict):
    try:
        ans = console.input(
            f"  [warn]删除会话 '{s['title']}'？(y/N)[/] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if ans not in ("y", "yes"):
        return
    delete_session_file(s["id"])
    console.print("  [ok]✓ 已删除[/]")
    time.sleep(0.5)


def _do_resume(console, copilot, s: dict):
    sid = s["id"]
    if sid == copilot.session_id:
        console.print("  [dim]已经是当前会话。[/]")
        time.sleep(0.4)
        return

    if s["root"] != str(copilot.root):
        console.print(
            f"  [err]✗ 会话工作目录为 {s['root']}，与当前不同，"
            f"无法恢复。[/]"
        )
        wait_for_return(console, "  [dim]按任意键继续…[/] ")
        return

    copilot._do_resume(sid)

    console.print()
    console.print(Panel(
        Text.from_markup(
            f"[dim]ID:[/] {sid}\n"
            f"[dim]标题:[/] {s['title']}\n"
            f"[dim]消息:[/] {s['messages']} 条\n"
            f"[dim]模型:[/] {s['model']}\n"
            f"[dim]撤销栈:[/] {len(copilot.undo_stack)}\n"
            f"[dim]快照:[/] {len(copilot.snapshots)}\n"
            f"[dim]待办:[/] {len(copilot.todos)}\n"
            f"[dim]问答历史:[/] {len(getattr(copilot, 'session_asks', []))}"
        ),
        title="[bold ok]✓ 已完整恢复[/]",
        title_align="left",
        border_style=OK_C,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    ))
    wait_for_return(console, "  [dim]按任意键继续…[/] ")