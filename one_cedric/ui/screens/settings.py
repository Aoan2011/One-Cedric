"""设置界面：配置查看 + 实时修改。"""
from __future__ import annotations

from rich import box
from rich.table import Table

from ...config import (
    BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C,
    THINK_LEVELS, ACCESS_MODES, ACCESS_MODE_DESC,
    DEFAULT_ACCESS_MODE, DEFAULT_THINK_LEVEL,
)
from ..keys import (
    read_key, has_readchar, wait_for_return,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC,
    KEY_BACKSPACE,
)
from ..menu import selection_progress


def _masked_input(console, label: str = "api_key") -> str:
    """遮罩输入：逐字符回显 *，Enter 确认，Esc 取消。"""
    console.print(f"  [dim]{label} =[/] ", end="")
    if not has_readchar():
        try:
            return console.input().strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    buf: list[str] = []
    while True:
        k = read_key()
        if k == KEY_ENTER:
            console.print()
            return "".join(buf)
        if k == KEY_ESC:
            console.print()
            return ""
        if k == KEY_BACKSPACE:
            if buf:
                buf.pop()
                console.print("\b \b", end="")
        elif len(k) == 1 and k.isprintable():
            buf.append(k)
            console.print("*", end="")


def _test_connection(console, copilot) -> None:
    """测试当前 API 地址连通性。"""
    host = str(copilot.host or "").rstrip("/")
    if not host:
        console.print("  [warn]⚠ API 地址为空[/]")
        return
    console.print(f"  [dim]正在测试 [accent]{host}[/] …[/]")
    try:
        import requests
    except ImportError:
        console.print("  [warn]⚠ 缺少 requests，无法测试（pip install requests）[/]")
        return
    headers = None
    if copilot.api_key:
        headers = {"Authorization": f"Bearer {copilot.api_key}"}
    probes = [host + "/api/tags", host + "/v1/models", host]
    for probe in probes:
        try:
            r = requests.get(probe, timeout=4, headers=headers)
            if r.status_code < 400:
                console.print(f"  [ok]✓ 连通：{probe} → HTTP {r.status_code}[/]")
                return
            console.print(f"  [warn]⚠ {probe} → HTTP {r.status_code}[/]")
        except Exception as exc:
            console.print(f"  [err]✗ {probe} → {type(exc).__name__}[/]")
    console.print("  [dim]没有探测到可用的 API 端点（Ollama / OpenAI 兼容）[/]")


def run_settings_screen(console, copilot) -> None:
    selected = 0
    while True:
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 设置[/]")
        console.print()

        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}",
                    padding=(0, 1))
        tbl.add_column("", width=2)
        tbl.add_column("项")
        tbl.add_column("当前值", style="accent")
        tbl.add_column("说明", style="dim")

        cfg = copilot.config.get("default", {})
        rows = [
            ("model", copilot.model, "模型名"),
            ("host", copilot.host, "API 地址"),
            ("api_key", "已设置" if copilot.api_key else "未设置",
             "API Key"),
            ("temperature", str(copilot.temperature), "温度 0-2"),
            ("max_steps", str(copilot.max_steps), "最大工具步数"),
            ("auto_yes", "开" if copilot.auto_yes else "关",
             "自动确认写操作"),
            ("show_reasoning",
             "开" if copilot.show_reasoning else "关",
             "显示推理过程"),
            ("think_level", copilot.think_level or DEFAULT_THINK_LEVEL,
             "思考模式"),
            ("access_mode", copilot.access_mode or DEFAULT_ACCESS_MODE,
             "访问模式"),
            ("allow_arbitrary_shell",
             "开" if copilot.allow_arbitrary_shell else "关",
             "允许任意 shell 命令"),
            ("sandbox_terminal",
             "开" if copilot.sandbox_terminal else "关",
             "shell 工具沙箱终端"),
            ("computer_use",
             "开" if copilot._computer_policy.enabled else "关",
             "Computer Use"),
            ("vision", "开" if copilot.enable_vision else "关",
             "图像识别"),
            ("disabled_tools",
             f"{len(copilot.disabled_tools)} 个",
             "已禁用的工具"),
        ]
        for i, (k, v, d) in enumerate(rows):
            marker = f"[{BRAND}]▸[/]" if i == selected else ""
            key_style = f"bold {BRAND}" if i == selected else ""
            tbl.add_row(
                marker,
                f"[{key_style}]{k}[/]" if key_style else k,
                str(v), d,
            )

        console.print(tbl)
        console.print(selection_progress(selected, len(rows)))
        console.print()
        console.print(
            f"  [dim]↑↓ 选择 · [/][accent]Enter[/][dim] 修改 · "
            f"[/][accent]c[/][dim] 配置文件 · "
            f"[/][accent]s[/][dim] 保存到全局 · "
            f"[/][accent]t[/][dim] 测试连接 · "
            f"[/][accent]q[/][dim] 返回[/]"
        )

        if has_readchar():
            key = read_key()
            if key in (KEY_UP, KEY_LEFT):
                selected = (selected - 1) % len(rows)
                continue
            if key in (KEY_DOWN, KEY_RIGHT):
                selected = (selected + 1) % len(rows)
                continue
            if key in (KEY_ESC, "q"):
                return
            ans = str(selected + 1) if key == KEY_ENTER else key
        else:
            try:
                ans = console.input(
                    "  [dim]设置名称 / edit / c / s / t / q >[/] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if ans == "edit":
                ans = str(selected + 1)
            elif ans.isdigit():
                ans = "invalid"
            elif not ans.isdigit():
                selected_row = next(
                    (i + 1 for i, row in enumerate(rows)
                     if row[0].lower() == ans),
                    None,
                )
                if selected_row is not None:
                    ans = str(selected_row)

        if ans in ("q", ""):
            return

        if ans == "s":
            copilot._save_config("global")
            console.print("  [ok]✓ 已保存到全局配置[/]")
            continue

        if ans == "t":
            _test_connection(console, copilot)
            continue

        if ans == "c":
            console.clear()
            console.print()
            console.print(f"  [bold {BRAND}]◆ 配置文件[/]")
            console.print()
            console.print(f"  [dim]全局:[/] [path]{copilot.config_path}[/]")
            console.print(f"  [dim]项目:[/] [path]"
                          f"{copilot.project_config_path}[/]")
            console.print()
            try:
                from ...storage import tools_config_path
                console.print(f"  [dim]工具:[/] [path]"
                              f"{tools_config_path()}[/]")
            except Exception:
                pass
            console.print()
            wait_for_return(console)
            continue

        try:
            idx = int(ans)
        except ValueError:
            console.print("  [err]✗ 未知设置或操作。[/]")
            continue

        if idx == 1:
            v = console.input(f"  [dim]model =[/] ").strip()
            if v:
                copilot.model = v
        elif idx == 2:
            v = console.input(f"  [dim]host =[/] ").strip()
            if v:
                copilot.host = v
                copilot._save_config("global")
                console.print(f"  [ok]✓ API 地址已保存[/]")
        elif idx == 3:
            v = _masked_input(console)
            if v:
                copilot.api_key = v
                copilot._save_config("global")
                console.print(f"  [ok]✓ API Key 已保存（{len(v)} 位）[/]")
            else:
                console.print("  [dim]已取消（未修改）[/]")
        elif idx == 4:
            v = console.input(f"  [dim]temperature =[/] ").strip()
            try:
                copilot.temperature = float(v)
            except ValueError:
                console.print("  [err]✗ 需要数字[/]")
        elif idx == 5:
            v = console.input(f"  [dim]max_steps =[/] ").strip()
            try:
                copilot.max_steps = max(1, int(v))
            except ValueError:
                console.print("  [err]✗ 需要整数[/]")
        elif idx == 6:
            copilot.auto_yes = not copilot.auto_yes
        elif idx == 7:
            copilot.show_reasoning = not copilot.show_reasoning
        elif idx == 8:
            console.print(f"  [dim]可选：[/]{' / '.join(THINK_LEVELS)}")
            v = console.input(f"  [dim]think_level =[/] ").strip().lower()
            if v in THINK_LEVELS:
                copilot.think_level = v
        elif idx == 9:
            console.print(f"  [dim]可选：[/]{' / '.join(ACCESS_MODES)}")
            for m in ACCESS_MODES:
                console.print(f"    [accent]{m:<14}[/] "
                              f"[dim]{ACCESS_MODE_DESC[m]}[/]")
            v = console.input(f"  [dim]access_mode =[/] ").strip().lower()
            if v in ACCESS_MODES:
                from ...tools.sandbox import set_access_mode
                copilot.access_mode = v
                set_access_mode(v)
                console.print(f"  [ok]✓ 已切换为 {v}[/]")
        elif idx == 10:
            copilot.allow_arbitrary_shell = not copilot.allow_arbitrary_shell
        elif idx == 11:
            copilot.sandbox_terminal = not copilot.sandbox_terminal
        elif idx == 12:
            copilot._computer_policy.enabled = not \
                copilot._computer_policy.enabled
        elif idx == 13:
            copilot.enable_vision = not copilot.enable_vision
        elif idx == 14:
            console.print("  [dim]用 /tools 命令管理工具开关[/]")
            wait_for_return(console, "  [dim]按任意键继续…[/] ")
        else:
            console.print("  [err]✗ 无效设置[/]")