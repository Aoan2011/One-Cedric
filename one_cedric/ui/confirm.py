"""统一的确认组件：全部用方向键选择 + 多选。

- confirm_yes_no   - 2 选项
- confirm_5        - 5 选项（写操作）
- confirm_choice   - N 选项通用
- confirm_input    - 文本输入
- confirm_dangerous- 危险操作（保持选中）
- confirm_multi    - 多选
"""
from __future__ import annotations

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .keys import (
    read_key, has_readchar,
    KEY_ENTER, KEY_ESC, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
)
from ..config import (
    BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, TOOL_C,
)
from .menu import selection_progress

SYNTAX_THEME = "monokai"


def _looks_like_code(body: str) -> bool:
    """启发式判断一段文本是否像代码/diff。"""
    body = body.lstrip()
    if body.startswith(("def ", "class ", "import ", "from ", "fn ",
                        "pub ", "func ", "package ", "function ",
                        "async def ", "const ", "let ", "var ", "if ")):
        return True
    if body.startswith(("---", "+++", "@@", "diff --git")):
        return True
    if "\n" in body and any(k in body for k in (" => ", "::", "->", ":= ")):
        return True
    return False


def _guess_lang(body: str) -> str:
    low = body.lstrip()
    if low.startswith(("def ", "class ", "import ", "from ", "async def ")):
        return "python"
    if low.startswith(("fn ", "pub fn ", "let mut ", "impl ")):
        return "rust"
    if low.startswith(("package ", "func ", "go func", "import (")):
        return "go"
    if low.startswith(("fn ", "function ", "const ", "let ", "var ", "async ")):
        return "javascript"
    if low.startswith(("def ", "end", "if ", "unless ")):
        return "ruby"
    return "text"


def _render_body(body) -> object:
    """body 渲染：代码/diff 自动语法高亮，普通文本原样。"""
    if body is None or body == "":
        return Text("")
    body = str(body)
    stripped = body.lstrip()

    # diff
    if stripped.startswith(("--- ", "+++ ", "@@ ", "diff --git")):
        return Syntax(body, "diff", theme=SYNTAX_THEME,
                      line_numbers=False, word_wrap=True)

    # markdown 代码块
    if body.count("```") >= 2:
        parts: list = []
        buf: list[str] = []
        lang = ""
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("```"):
                if lang:
                    parts.append(Syntax("\n".join(buf), lang or "text",
                                        theme=SYNTAX_THEME,
                                        line_numbers=False,
                                        word_wrap=True))
                    buf = []
                    lang = ""
                else:
                    lang = s[3:].strip() or "text"
                continue
            buf.append(line)
        if buf:
            parts.append(Text("\n".join(buf)))
        if not parts:
            parts.append(Text(body))
        return Group(*parts)

    # 普通代码
    if _looks_like_code(body):
        return Syntax(body, _guess_lang(body), theme=SYNTAX_THEME,
                      line_numbers=False, word_wrap=True)

    return Text(body)


def _select_options(console, title: str, body: str,
                    options: list, extra_warn: str = "",
                    default_index: int = 0,
                    hint: str = "",
                    show_dog: bool = False) -> str:
    if not options:
        return ""

    if not has_readchar():
        return _fallback_select(
            console, title, body, options, extra_warn, show_dog=show_dog
        )

    selected = default_index if 0 <= default_index < len(options) else 0

    def render():
        content = []
        if show_dog:
            content.append(Text("▐◉ᴥ◉▌  需要你的选择",
                                style="bold yellow"))
        if extra_warn:
            content.append(Text(extra_warn, style=f"bold {ERR_C}"))
        if body:
            content.append(_render_body(body))

        for i, (key, label, color, is_def) in enumerate(options):
            marker = "▸ " if i == selected else "  "
            prefix_style = f"bold {BRAND}" if i == selected else color
            label_style = "bold" if i == selected else ""
            def_tag = " [dim]★[/]" if is_def and i != selected else ""

            line = Text()
            line.append(marker, style=prefix_style)
            line.append(label, style=label_style)
            if def_tag:
                line.append("  ★", style="dim")
            content.append(line)
            if is_def and i == selected:
                content.append(Text("  当前默认", style="dim"))

        content.append(selection_progress(selected, len(options)))
        if hint:
            content.append(Text(hint, style="dim"))
        else:
            content.append(Text("↑↓←→ 选择 · Enter 确认 · Esc 取消",
                                style="dim"))
        return Panel(
            Group(*content),
            title=Text(title, style=f"bold {TOOL_C}"),
            border_style=WARN_C,
            padding=(0, 1),
        )

    with Live(
            render(), console=console, transient=True,
            auto_refresh=False, vertical_overflow="visible") as live:
        while True:
            k = read_key()

            if k in (KEY_UP, KEY_LEFT):
                selected = (selected - 1) % len(options)
                live.update(render(), refresh=True)
            elif k in (KEY_DOWN, KEY_RIGHT):
                selected = (selected + 1) % len(options)
                live.update(render(), refresh=True)
            elif k == KEY_ENTER:
                return options[selected][0]
            elif k == KEY_ESC or k == "q":
                return options[default_index][0] if options else ""
            elif k == "y":
                for key, _, _, _ in options:
                    if key in ("y", "yes"):
                        return key
            elif k == "n":
                for key, _, _, _ in options:
                    if key in ("n", "no"):
                        return key


def _fallback_select(console, title, body, options, extra_warn,
                     show_dog: bool = False) -> str:
    console.print()
    console.print(f"  [bold {TOOL_C}]{title}[/]")
    if extra_warn:
        console.print(f"  [bold {ERR_C}]{extra_warn}[/]")
    if show_dog:
        console.print("  [bold yellow]▐◉ᴥ◉▌[/]  [dim]需要你的选择[/]")
    if body:
        console.print(_render_body(body))
    console.print()
    default = next((key for key, _, _, is_def in options if is_def),
                   options[0][0])
    for key, label, color, is_def in options:
        def_tag = " [dim](默认)[/]" if is_def else ""
        console.print(f"  [accent]{key}[/] · {label}{def_tag}")

    while True:
        try:
            ans = console.input("  [dim]输入选项名称 >[/] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return default
        if not ans:
            return default
        if ans in ("y", "yes"):
            if any(key in ("y", "yes") for key, *_ in options):
                return next(key for key, *_ in options
                            if key in ("y", "yes"))
        if ans in ("n", "no"):
            if any(key in ("n", "no") for key, *_ in options):
                return next(key for key, *_ in options
                            if key in ("n", "no"))
        for key, label, _, _ in options:
            if ans in (key.lower(), label.lower()):
                return key
        console.print("  [dim]请输入显示的选项名称[/]")


def confirm_yes_no(console: Console, title: str, body: str = "",
                   default_yes: bool = False,
                   danger: bool = False,
                   yes_label: str = "是",
                   no_label: str = "否",
                   show_dog: bool = False) -> bool:
    if default_yes:
        options = [
            ("yes", yes_label, OK_C, True),
            ("no", no_label, ERR_C, False),
        ]
        default_idx = 0
    else:
        options = [
            ("no", no_label, ERR_C, True),
            ("yes", yes_label, OK_C, False),
        ]
        default_idx = 0

    extra = "⚠ 危险操作" if danger else ""

    result = _select_options(console, title, body, options,
                              extra_warn=extra, default_index=default_idx,
                              show_dog=show_dog)
    return result == "yes"


def ask_confirm(console, title, body="", default=False, danger=False):
    return confirm_yes_no(console, title, body,
                          default_yes=default, danger=danger)


class ConfirmResult:
    YES = "yes"
    ALWAYS = "always"
    NO = "no"
    EDIT = "edit"
    HELP = "help"


def confirm_5(console: Console, title: str, body: str,
              extra_warn: str = "",
              allow_always: bool = True,
              allow_edit: bool = True,
              show_dog: bool = False) -> str:
    options = [("yes", "执行这次", OK_C, False)]
    if allow_always:
        options.append(("always", "本会话内允许", OK_C, False))
    options.append(("no", "拒绝", ERR_C, True))
    if allow_edit:
        options.append(("edit", "用 $EDITOR 修改", ACCENT, False))
    options.append(("help", "查看帮助", DIM_C, False))

    default_idx = next((i for i, o in enumerate(options) if o[3]), 0)

    result = _select_options(console, title, body, options,
                              extra_warn=extra_warn,
                              default_index=default_idx,
                              show_dog=show_dog)
    return result or "no"


def confirm_choice(console: Console, title: str,
                   choices: list, body: str = "",
                   default: str = "",
                   show_dog: bool = False) -> str:
    if not choices:
        return ""
    normalized = []
    for i, c in enumerate(choices):
        if isinstance(c, tuple):
            if len(c) >= 3:
                normalized.append((c[0], c[1], c[2], False))
            else:
                normalized.append((c[0], c[1], "", False))
        else:
            normalized.append((str(c), str(c), "", False))

    default_idx = 0
    if default:
        for i, (k, _, _, _) in enumerate(normalized):
            if k == default:
                default_idx = i
                break
        normalized = [
            (k, l, col, k == default)
            for (k, l, col, _) in normalized
        ]

    return _select_options(console, title, body, normalized,
                            default_index=default_idx,
                            show_dog=show_dog)


def confirm_input(console: Console, title: str, body: str = "",
                  default: str = "", password: bool = False,
                  hint: str = "") -> str:
    console.print()
    console.print(f"  [bold {TOOL_C}]{title}[/]")
    if body:
        console.print(_render_body(body))
    if hint:
        console.print(f"  [dim]{hint}[/]")
    console.print()

    try:
        if password:
            import getpass
            ans = getpass.getpass("  [dim]>[/] ")
        else:
            prompt = "  [dim]>[/] "
            if default:
                prompt = f"  [dim]> [/][dim]({default}) [/]"
            ans = console.input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default
    return ans if ans else default


def confirm_dangerous(console: Console, title: str, body: str,
                      countdown: int = 5,
                      show_dog: bool = False) -> bool:
    import time
    if not has_readchar():
        return confirm_yes_no(console, title, body,
                              default_yes=False, danger=True,
                              show_dog=show_dog)

    options = [
        ("yes", "确认（保持选中 " + str(countdown) + " 秒）", OK_C, False),
        ("no", "取消", ERR_C, True),
    ]
    selected = 0
    hold_start = None

    def render():
        content = [_render_body(body)]
        if show_dog:
            content.insert(0, Text("▐◉ᴥ◉▌  需要你的选择",
                                   style="bold yellow"))
        elapsed = time.time() - hold_start if hold_start else 0
        remain = max(0, countdown - elapsed)
        for i, (key, label, color, is_def) in enumerate(options):
            marker = "▸ " if i == selected else "  "
            prefix_style = f"bold {BRAND}" if i == selected else color
            line = Text()
            line.append(marker, style=prefix_style)
            if i == 0 and selected == 0 and hold_start:
                bar_w = 20
                filled = int(elapsed / countdown * bar_w)
                bar = "█" * filled + "░" * (bar_w - filled)
                line.append(f"确认 [{bar}] {remain:.1f}s", style=OK_C)
            else:
                line.append(label, style="bold" if i == selected else "")
            content.append(line)
        content.append(selection_progress(selected, len(options)))
        content.append(Text(
            "↑↓←→ 选择 · 确认需保持选中几秒 · Esc 取消",
            style="dim",
        ))
        return Panel(
            Group(*content),
            title=Text(title, style=f"bold {ERR_C}"),
            border_style=ERR_C,
            padding=(0, 1),
        )

    with Live(
            render(), console=console, transient=True,
            auto_refresh=False, vertical_overflow="visible") as live:
        while True:
            if selected == 0 and hold_start:
                if time.time() - hold_start >= countdown:
                    return True
                live.update(render(), refresh=True)
                time.sleep(0.05)
                continue

            k = read_key()
            if k in (KEY_UP, KEY_LEFT):
                selected = (selected - 1) % len(options)
                hold_start = None
            elif k in (KEY_DOWN, KEY_RIGHT):
                selected = (selected + 1) % len(options)
                hold_start = None
            elif k == KEY_ENTER:
                if selected == 0:
                    if hold_start is None:
                        hold_start = time.time()
                else:
                    return False
            elif k == KEY_ESC or k == "q":
                return False
            live.update(render(), refresh=True)


def confirm_multi(console: Console, title: str, items: list,
                  body: str = "",
                  preselect: list | None = None,
                  min_select: int = 0,
                  max_select: int = 0,
                  filter_fn=None,
                  hint: str = "",
                  show_dog: bool = False) -> list:
    if not items:
        return []

    normalized = []
    for c in items:
        if isinstance(c, tuple):
            if len(c) >= 3:
                normalized.append((str(c[0]), str(c[1]), str(c[2])))
            elif len(c) >= 2:
                normalized.append((str(c[0]), str(c[1]), ""))
            else:
                normalized.append((str(c[0]), str(c[0]), ""))
        else:
            normalized.append((str(c), str(c), ""))

    selected_keys = set(preselect or [])
    valid_keys = {k for k, _, _ in normalized}
    selected_keys &= valid_keys

    if not has_readchar():
        return _fallback_multi(console, title, normalized,
                                selected_keys, min_select)

    cur = 0
    status_message = ""

    def render():
        content = []
        if show_dog:
            content.append(Text("▐◉ᴥ◉▌  需要你的选择",
                                style="bold yellow"))
        if body:
            content.append(Text(str(body)))
        count_line = Text(f"已选 {len(selected_keys)}", style="bold")
        if max_select:
            count_line.append(f" / 上限 {max_select}", style="dim")
        if min_select:
            count_line.append(f"  至少 {min_select}", style="dim")
        content.append(count_line)
        for i, (key, label, sub) in enumerate(normalized):
            is_cur = i == cur
            is_sel = key in selected_keys
            line = Text()
            line.append("▸ " if is_cur else "  ",
                        style=f"bold {BRAND}" if is_cur else "")
            line.append("◉" if is_sel else "○",
                        style="bold green" if is_sel else "dim")
            line.append(" ")
            line.append(label, style=f"bold {BRAND}" if is_cur else
                        ("" if is_sel else "dim"))
            content.append(line)
            if sub:
                content.append(Text(f"  {sub}", style="dim"))
        content.append(selection_progress(cur, len(normalized)))
        if status_message:
            content.append(Text(status_message, style=f"bold {WARN_C}"))
        content.append(Text(
            hint or (
                "↑↓←→ 移动 · Space 勾选 · Enter 保存 · "
                "a 全选 · n 全不选 · i 反选 · q 取消"
            ),
            style="dim",
        ))
        return Panel(Group(*content), title=Text(title, style=f"bold {TOOL_C}"),
                     border_style=BRAND, padding=(0, 1))

    with Live(
            render(), console=console, transient=True,
            auto_refresh=False, vertical_overflow="visible") as live:
        while True:
            k = read_key()
            changed = True

            if k in (KEY_UP, KEY_LEFT):
                cur = (cur - 1) % len(normalized)
                status_message = ""
            elif k in (KEY_DOWN, KEY_RIGHT):
                cur = (cur + 1) % len(normalized)
                status_message = ""
            elif k == " ":
                key = normalized[cur][0]
                if key in selected_keys:
                    selected_keys.discard(key)
                    status_message = ""
                elif max_select and len(selected_keys) >= max_select:
                    status_message = f"已达上限 {max_select}"
                else:
                    selected_keys.add(key)
                    status_message = ""
            elif k == KEY_ENTER:
                if min_select and len(selected_keys) < min_select:
                    status_message = f"至少需要选择 {min_select} 项"
                else:
                    return [
                        key for key, _, _ in normalized
                        if key in selected_keys
                    ]
            elif k == KEY_ESC or k == "q":
                return [
                    key for key, _, _ in normalized
                    if key in selected_keys
                ]
            elif k == "a":
                selected_keys = set(
                    key for key, _, _ in normalized[:max_select]
                ) if max_select else {key for key, _, _ in normalized}
                status_message = ""
            elif k == "n":
                selected_keys = set()
                status_message = ""
            elif k == "i":
                all_keys = {key for key, _, _ in normalized}
                selected_keys = all_keys - selected_keys
                if max_select and len(selected_keys) > max_select:
                    selected_keys = set(
                        list(selected_keys)[:max_select]
                    )
                status_message = ""
            else:
                changed = False
            if changed:
                live.update(render(), refresh=True)

def _fallback_multi(console, title, items, preselect, min_select) -> list:
    console.print()
    console.print(f"  [bold {TOOL_C}]{title}[/]")
    console.print()
    for key, label, sub in items:
        box = "[green]x[/]" if key in preselect else "[ ]"
        console.print(f"  {box} {label}")
        if sub:
            console.print(f"       [dim]{sub}[/]")
    console.print()
    console.print("  [dim]输入名称（逗号分隔），直接回车保留当前选择[/]")
    try:
        ans = console.input("  [dim]>[/] ").strip()
    except (EOFError, KeyboardInterrupt):
        return [k for k in preselect]
    if not ans:
        return [k for k in preselect]
    chosen = set()
    selected_names = {part.strip().casefold()
                      for part in ans.split(",") if part.strip()}
    for key, label, _sub in items:
        if key.casefold() in selected_names or label.casefold() in selected_names:
            chosen.add(key)
    if min_select and len(chosen) < min_select:
        console.print(f"  [err]至少需要 {min_select} 项[/]")
        return []
    return [k for k, _, _ in items if k in chosen]


def multi_delete(console: Console, title: str, items: list,
                 body: str = "",
                 danger: bool = True) -> list:
    warn = "⚠ 删除操作不可撤销" if danger else ""
    real_body = (body + "\n\n" if body else "") + warn
    return confirm_multi(console, title, items,
                          body=real_body, min_select=1)


def multi_toggle(console: Console, title: str, items: list,
                 body: str = "", preselect: list | None = None) -> list:
    return confirm_multi(console, title, items,
                          body=body, preselect=preselect or [])