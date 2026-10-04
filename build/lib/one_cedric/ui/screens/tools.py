"""工具管理：启用/禁用 + 分类 + 批量。"""
from __future__ import annotations

import time

from rich import box
from rich.table import Table

from ...config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C
from ...storage import save_tools_config
from ..menu import selection_progress


def run_tools_screen(console, copilot) -> None:
    from ..keys import (
        read_key, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
        KEY_ENTER, KEY_ESC, has_readchar,
    )
    from ..confirm import confirm_yes_no

    selected_category = 0
    while True:
        try:
            from ...tools.schema import TOOLS
        except ImportError:
            console.print("[err]无法加载工具表[/]")
            return
        try:
            from ...integrations import external_tool_schemas
            all_schemas = [*TOOLS, *external_tool_schemas()]
        except (OSError, RuntimeError, ValueError) as exc:
            console.print(f"[err]无法加载外部工具: {exc}[/]")
            return

        disabled = getattr(copilot, "disabled_tools", set()) or set()

        all_tools = []
        for t in all_schemas:
            fn = t["function"]
            name = fn["name"]
            desc = (fn.get("description") or "").split("\n")[0][:60]
            all_tools.append({
                "name": name,
                "desc": desc,
                "enabled": name not in disabled,
            })

        categories = _categorize(all_tools)

        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 工具管理[/]")
        enabled_count = sum(1 for t in all_tools if t["enabled"])
        console.print(
            f"  [dim]{enabled_count} / {len(all_tools)} 启用[/]"
        )
        console.print()

        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}",
                    padding=(0, 1))
        tbl.add_column("", width=2)
        tbl.add_column("分类", style="bold")
        tbl.add_column("已启用", justify="right")
        tbl.add_column("总数", justify="right", style="dim")
        cat_list = list(categories.items())
        if cat_list:
            selected_category %= len(cat_list)
        for i, (cat, tools) in enumerate(cat_list, 1):
            on = sum(1 for t in tools if t["enabled"])
            total = len(tools)
            color = OK_C if on == total else (WARN_C if on else ERR_C)
            marker = f"[{BRAND}]▸[/]" if i - 1 == selected_category else ""
            tbl.add_row(marker, cat, f"[{color}]{on}[/]", str(total))
        console.print(tbl)
        console.print(selection_progress(selected_category, len(cat_list)))

        console.print()
        console.print(
            f"  [dim]操作：[/]"
            f"[accent]Enter[/][dim] 进入分类 · [/]"
            f"[accent]t[/][dim] 单工具切换 · [/]"
            f"[accent]T[/][dim] 批量切换 · [/]"
            f"[accent]a[/][dim] 全部启用 · [/]"
            f"[accent]n[/][dim] 全部禁用 · [/]"
            f"[accent]c[/][dim] 自定义工具 · [/]"
            f"[accent]q[/][dim] 返回[/]"
        )

        if not has_readchar():
            try:
                ans = console.input(
                    "  [dim]Enter 分类 / t 工具 / T 批量 / "
                    "a 全部启用 / n 全部禁用 / q 返回 >[/] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if ans.lower() in ("q", "back"):
                return
            if ans.lower() == "c":
                from .integrations import run_custom_tools_screen
                run_custom_tools_screen(console, copilot)
                continue
            if ans.lower() in ("", "enter", "select"):
                if cat_list:
                    cat_name, cat_tools = cat_list[selected_category]
                    _toggle_category(console, copilot, cat_tools, cat_name)
                continue
            if ans.lower() == "a":
                _set_all(copilot, all_tools, True)
                continue
            if ans.lower() == "n":
                if confirm_yes_no(console, "禁用所有工具？",
                                   default_yes=False, danger=True):
                    _set_all(copilot, all_tools, False)
                continue
            if ans == "T":
                _batch_toggle(console, copilot, all_tools)
                continue
            if ans.lower() == "t":
                _single_toggle(console, copilot, all_tools)
                continue
            matched = next(
                ((i, entry) for i, entry in enumerate(cat_list)
                 if ans.casefold() == entry[0].casefold()),
                None,
            )
            if matched:
                selected_category, (cat_name, cat_tools) = matched
                _toggle_category(console, copilot, cat_tools, cat_name)
            continue

        k = read_key()
        if k in (KEY_ESC, "q"):
            return
        if k in (KEY_UP, KEY_LEFT) and cat_list:
            selected_category = (selected_category - 1) % len(cat_list)
            continue
        if k in (KEY_DOWN, KEY_RIGHT) and cat_list:
            selected_category = (selected_category + 1) % len(cat_list)
            continue
        if k == "a":
            if confirm_yes_no(console, "启用所有工具？", default_yes=True):
                _set_all(copilot, all_tools, True)
            continue
        if k == "n":
            if confirm_yes_no(console, "禁用所有工具？",
                               default_yes=False, danger=True):
                _set_all(copilot, all_tools, False)
            continue
        if k == "c":
            from .integrations import run_custom_tools_screen
            run_custom_tools_screen(console, copilot)
            continue
        if k == "t":
            _single_toggle(console, copilot, all_tools)
            continue
        if k == "T":
            _batch_toggle(console, copilot, all_tools)
            continue
        if k == KEY_ENTER:
            if cat_list:
                cat_name, cat_tools = cat_list[selected_category]
                _toggle_category(console, copilot, cat_tools, cat_name)
            continue


def _categorize(tools: list) -> dict:
    from collections import OrderedDict
    cats = OrderedDict()

    def _cat(name):
        if name.startswith(("read_", "write_", "edit_", "list_",
                             "glob", "grep", "search_in", "file_",
                             "apply_", "hash_", "find_dup")):
            return "文件"
        if name.startswith("web_") or name in ("http_request",
                                                 "download",
                                                 "download_info",
                                                 "get_public_ip",
                                                 "ping_host",
                                                 "port_scan",
                                                 "traceroute",
                                                 "http_head"):
            return "网络"
        if name.startswith("lsp_"):
            return "LSP"
        if name.startswith("docx") or name.startswith("pdf") \
                or name.startswith("pptx") or name.startswith("excel"):
            return "办公"
        if name.startswith("sysop"):
            return "系统"
        if name.startswith("amap_"):
            return "地图"
        if name.startswith("email_"):
            return "邮件"
        if name.startswith("qrcode_"):
            return "二维码"
        if name.startswith("python_"):
            return "Python"
        if name in ("bash", "bash_bg", "git", "docker"):
            return "执行"
        if name in ("screen_capture", "screen_info",
                    "mouse_action", "keyboard_action", "window_action"):
            return "Computer"
        if name in ("spawn_agent", "multi_review", "ask_user"):
            return "Agent"
        if name.startswith(("memory_", "cron_", "dream_")):
            return "记忆"
        if name.startswith(("video_", "audio_")):
            return "媒体"
        if name in ("json_query", "csv_query", "sqlite",
                    "json_schema_validate", "sqlite_tables",
                    "sqlite_schema", "postgres_query", "mysql_query",
                    "mongo_find"):
            return "数据"
        if name in ("image_info", "image_process"):
            return "图像"
        if name.startswith("ansi_"):
            return "文本"
        if name.startswith("notify"):
            return "通知"
        if name.startswith("pkg_") or name in ("open_app",
                                                 "list_apps",
                                                 "find_app"):
            return "应用"
        if name.startswith("cost_"):
            return "成本"
        if name == "weather":
            return "天气"
        if name.startswith(("k8s_", "compose_")):
            return "容器"
        if name.startswith("ocr_"):
            return "OCR"
        if name.startswith("wechat_"):
            return "微信"
        if name.startswith("locate_"):
            return "定位"
        if name.startswith("mcp__"):
            return "MCP"
        if name.startswith("custom__"):
            return "自定义"
        if name == "file_attrs":
            return "文件"
        return "其他"

    for t in tools:
        c = _cat(t["name"])
        cats.setdefault(c, []).append(t)
    return cats


def _toggle_category(console, copilot, tools: list, cat_name: str):
    from ..confirm import confirm_multi
    from ..progress import celebrate

    items = [(t["name"], t["name"], t["desc"]) for t in tools]
    preselect = [t["name"] for t in tools if t["enabled"]]

    chosen = confirm_multi(
        console, f"{cat_name} 分类工具",
        items, preselect=preselect,
        hint="↑↓←→ 移动 · Space 勾选 · Enter 保存 · q 取消",
    )

    all_names = {t["name"] for t in tools}
    current_disabled = set(copilot.disabled_tools or set())

    for name in all_names:
        if name in chosen:
            current_disabled.discard(name)
        else:
            current_disabled.add(name)

    copilot.disabled_tools = current_disabled
    save_tools_config(current_disabled)
    celebrate(console, "已保存", duration=0.2,
              stats=f"{cat_name}: {len(chosen)}/{len(tools)} 启用")
    time.sleep(0.5)


def _single_toggle(console, copilot, tools: list):
    from ..confirm import confirm_choice

    items = [
        (t["name"],
         f"{'[on ]' if t['enabled'] else '[off]'} {t['name']}",
         t["desc"])
        for t in tools
    ]
    picked = confirm_choice(console, "切换工具", items)
    if not picked:
        return
    current = set(copilot.disabled_tools or set())
    if picked in current:
        current.discard(picked)
        action = "启用"
    else:
        current.add(picked)
        action = "禁用"
    copilot.disabled_tools = current
    save_tools_config(current)
    console.print(f"  [ok]✓ {action} {picked}[/]")
    time.sleep(0.4)


def _batch_toggle(console, copilot, tools: list):
    from ..confirm import confirm_multi
    from ..progress import celebrate

    items = [
        (t["name"], t["name"],
         f"{'✓' if t['enabled'] else '○'}  {t['desc']}")
        for t in tools
    ]
    preselect = [t["name"] for t in tools if t["enabled"]]

    chosen = confirm_multi(
        console, f"批量选择工具（{len(tools)}）",
        items, preselect=preselect,
        hint="↑↓←→ 移动 · Space 勾选 · a 全选 · n 全不选 · "
             "i 反选 · Enter 保存",
    )

    all_names = {t["name"] for t in tools}
    current = set(copilot.disabled_tools or set())
    for name in all_names:
        if name in chosen:
            current.discard(name)
        else:
            current.add(name)

    copilot.disabled_tools = current
    save_tools_config(current)
    celebrate(console, "已保存", duration=0.2,
              stats=f"{len(chosen)}/{len(tools)} 启用")
    time.sleep(0.5)


def _set_all(copilot, tools: list, enabled: bool):
    if enabled:
        copilot.disabled_tools = set()
        save_tools_config(set())
    else:
        names = {t["name"] for t in tools}
        copilot.disabled_tools = names
        save_tools_config(names)