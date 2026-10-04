"""模型管理：列表 + 参数调节。"""
from __future__ import annotations

from pathlib import Path
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, TOOL_C
from ..keys import wait_for_return
from ..menu import selection_progress


OVERRIDE_PATH = Path.home() / ".one-cedric" / "model_overrides.toml"


def _load_overrides() -> dict:
    try:
        import tomllib
    except ImportError:
        return {}
    if not OVERRIDE_PATH.exists():
        return {}
    try:
        return tomllib.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _save_overrides(data: dict) -> bool:
    lines = ["# One Cedric 每个模型的参数覆盖", ""]
    for name, params in data.items():
        lines.append(f"[models.{name}]")
        for k, v in params.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            else:
                lines.append(f'{k} = "{_esc(v)}"')
        lines.append("")
    try:
        OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDE_PATH.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def get_model_override(model: str) -> dict:
    return _load_overrides().get(model, {})


def _fetch_models(copilot) -> list:
    try:
        import requests
        base = copilot.host.rstrip("/")
        url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
        headers = {}
        if copilot.api_key:
            headers["Authorization"] = f"Bearer {copilot.api_key}"
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code < 400:
            data = r.json()
            return [m.get("id", "?") for m in data.get("data", [])]
    except Exception:
        pass
    return []


FIELDS = [
    ("temperature", float, 0.0, 2.0, "温度：0 确定，2 随机"),
    ("top_p", float, 0.0, 1.0, "Top-p 采样"),
    ("max_tokens", int, 128, 200000, "最大输出 tokens"),
    ("frequency_penalty", float, -2.0, 2.0, "频率惩罚"),
    ("presence_penalty", float, -2.0, 2.0, "存在惩罚"),
    ("context_limit", int, 2048, 2000000, "上下文上限（估算用）"),
]


THINK_LEVELS = ["minimal", "low", "medium", "max", "xhigh", "ultra"]


def run_models_screen(console, copilot) -> None:
    from ..keys import (
        read_key, has_readchar, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
        KEY_ENTER, KEY_ESC,
    )

    selected = 0
    while True:
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 模型管理[/]")
        console.print(f"  [dim]当前模型: [accent]{copilot.model}[/]")
        console.print()

        with console.status(
            f"[{ACCENT}]正在获取模型列表…[/]", spinner="dots"
        ):
            models = _fetch_models(copilot)
        if not models:
            console.print(
                f"  [warn]⚠ 无法从 {copilot.host} 获取模型列表[/]"
            )
            console.print(f"  [dim]当前模型：[accent]{copilot.model}[/]")
            models = [copilot.model]

        overrides = _load_overrides()

        items = []
        for m in models:
            params = overrides.get(m, {})
            n_overrides = len(params)
            note = f"  [{ACCENT}]{n_overrides} 项自定义[/]" if n_overrides else ""
            items.append({"model": m, "display": f"{m}{note}"})
        items.append({"model": None, "display": "New model"})
        selected = min(selected, len(items) - 1)

        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}",
                    padding=(0, 1))
        tbl.add_column("", width=2)
        tbl.add_column("模型", style="bold")
        tbl.add_column("参数")
        tbl.add_column("价格 / 1M tokens")
        from ...pricing import pricing_for
        for i, it in enumerate(items):
            if it["model"] is None:
                tbl.add_row(
                    f"[{BRAND}]▸[/]" if i == selected else "",
                    f"[bold {BRAND}]＋ New model[/]" if i == selected
                    else "＋ New model",
                    "[dim]Connect another OpenAI-compatible host[/]",
                    "—",
                )
                continue
            params = overrides.get(it["model"], {})
            model_label = it["model"]
            if it["model"] == copilot.model:
                model_label += f"  [{OK_C}]当前使用[/]"
            if i == selected:
                model_label = f"[bold {BRAND}]{model_label}[/]"
            if params:
                p_str = " · ".join(f"{k}={v}" for k, v in list(params.items())[:4])
                _cached, input_price, output_price = pricing_for(it["model"])
                tbl.add_row(
                    f"[{BRAND}]▸[/]" if i == selected else "",
                    model_label,
                    f"[dim]{p_str}[/]",
                    f"${input_price:g} / ${output_price:g}",
                )
            else:
                _cached, input_price, output_price = pricing_for(it["model"])
                tbl.add_row(
                    f"[{BRAND}]▸[/]" if i == selected else "",
                    model_label,
                    "[dim]默认[/]",
                    f"${input_price:g} / ${output_price:g}",
                )

        console.print(tbl)
        console.print(selection_progress(selected, len(items)))
        console.print()
        console.print(
            f"  [dim]操作：[/][accent]↑↓[/][dim] 选择 · "
            f"[/][accent]Enter[/][dim] 选择 · "
            f"[/][accent]p[/][dim] 调参 · "
            f"[/][accent]c[/][dim] 设置价格 · "
            f"[/][accent]t[/][dim] 测试连接 · "
            f"[/][accent]r[/][dim] 刷新 · "
            f"[/][accent]q[/][dim] 返回[/]"
        )

        if not items:
            console.print("[dim]（无模型可管理）[/]")
            wait_for_return(console)
            return

        if has_readchar():
            key = read_key()
            if key in (KEY_UP, KEY_LEFT):
                selected = (selected - 1) % len(items)
                continue
            if key in (KEY_DOWN, KEY_RIGHT):
                selected = (selected + 1) % len(items)
                continue
            if key == KEY_ESC:
                return
            sel = "enter" if key == KEY_ENTER else key
        else:
            try:
                sel = console.input(
                    "  [dim]Enter 选择 · p 参数 · c 价格 · "
                    "t 测试 · r 刷新 · q 返回 >[/] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return

        if sel == "q" or sel == "":
            return
        if sel == "r":
            continue
        if sel == "t":
            _test_connection(console, copilot)
            continue
        if sel == "p":
            model = items[selected]["model"]
            if model:
                _edit_model_params(console, copilot, model)
            else:
                console.print("  [warn]请先选择一个模型。[/]")
            continue
        if sel == "c":
            model = items[selected]["model"]
            if model:
                _edit_model_pricing(console, model)
            else:
                console.print("  [warn]请先选择一个模型。[/]")
            continue
        if sel == "new":
            _add_model(console, copilot)
            continue
        if sel not in ("enter", "select"):
            model_match = next(
                (it["model"] for it in items
                 if it["model"] and it["model"].casefold() == sel.casefold()),
                None,
            )
            if model_match is not None:
                copilot.model = model_match
                console.print(f"  [ok]✓ 已切换: {model_match}[/]")
                continue

        if sel == "enter":
            selected_model = items[selected]["model"]
            if selected_model is None:
                _add_model(console, copilot)
                continue
            copilot.model = selected_model
            console.print(f"  [ok]✓ 已切换: {selected_model}[/]")
            continue

        console.print("  [err]✗ 未知操作[/]")


def _add_model(console, copilot) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ New model[/]")
    try:
        host = console.input("  [dim]Host URL =[/] ").strip().rstrip("/")
        if not host:
            return
        model = console.input("  [dim]Model ID =[/] ").strip()
        if not model:
            return
    except (EOFError, KeyboardInterrupt):
        return
    from .settings import _masked_input
    api_key = _masked_input(console, "api_key (leave blank to keep current)")
    if not api_key:
        api_key = copilot.api_key
    copilot.host = host
    copilot.api_key = api_key
    copilot.model = model
    copilot.config.setdefault("default", {}).update(
        {"host": host, "model": model, "api_key": api_key}
    )
    copilot._save_config("global")
    console.print(f"  [ok]✓ 已连接模型 {model}[/]")


def _edit_model_pricing(console, model: str) -> None:
    from ...pricing import load_user_pricing, save_user_pricing

    data = load_user_pricing()
    current = data.get(model, (0.0, 0.0, 0.0))
    console.print(
        f"  [dim]模型价格（美元 / 1M tokens）："
        f"缓存输入 {current[0]} · 输入 {current[1]} · 输出 {current[2]}[/]"
    )
    try:
        raw = console.input(
            "  [dim]请输入 缓存输入 输入 输出（空格分隔，q 取消）>[/] "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return
    if raw.lower() == "q":
        return
    try:
        values = tuple(float(value) for value in raw.split())
    except ValueError:
        console.print("  [err]✗ 价格必须是数字。[/]")
        return
    if len(values) != 3 or any(value < 0 for value in values):
        console.print("  [err]✗ 需要三个非负价格。[/]")
        return
    data[model] = values
    if save_user_pricing(data):
        console.print("  [ok]✓ 已保存价格。[/]")
    else:
        console.print("  [err]✗ 保存价格失败。[/]")


def _test_connection(console, copilot):
    console.print(f"  [dim]测试 {copilot.host} …[/]")
    try:
        import requests
        base = copilot.host.rstrip("/")
        url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
        headers = {}
        if copilot.api_key:
            headers["Authorization"] = f"Bearer {copilot.api_key}"
        with console.status(
            f"[{ACCENT}]正在连接 {copilot.host}…[/]", spinner="dots"
        ):
            r = requests.get(url, headers=headers, timeout=6)
        if r.status_code < 400:
            data = r.json()
            models = [m.get("id", "?") for m in data.get("data", [])]
            console.print(f"  [ok]✓ 连接成功，{len(models)} 个模型[/]")
        else:
            console.print(f"  [err]✗ HTTP {r.status_code}[/]")
    except Exception as exc:
        console.print(f"  [err]✗ {exc}[/]")
    wait_for_return(console, "  [dim]按任意键继续…[/] ")


def _edit_model_params(console, copilot, model: str):
    from ..keys import (
        read_key, has_readchar, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
        KEY_ENTER, KEY_ESC,
    )

    overrides = _load_overrides()
    params = dict(overrides.get(model, {}))
    selected = 0
    field_count = len(FIELDS) + 1

    while True:
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 模型参数 · {model}[/]")
        console.print()

        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}",
                    padding=(0, 1))
        tbl.add_column("", width=2)
        tbl.add_column("字段")
        tbl.add_column("当前值", style="accent")
        tbl.add_column("默认", style="dim")
        tbl.add_column("说明", style="dim")

        for i, (name, typ, lo, hi, desc) in enumerate(FIELDS):
            cur = params.get(name, "-")
            default = getattr(copilot, name, None)
            tbl.add_row(
                f"[{BRAND}]▸[/]" if i == selected else "", name,
                str(cur) if cur != "-" else "(未设置)",
                str(default) if default is not None else "-",
                desc,
            )
        tl = params.get("think_level", copilot.think_level or "medium")
        tbl.add_row(
            f"[{BRAND}]▸[/]" if selected == len(FIELDS) else "",
            "think_level",
            tl,
            copilot.think_level or "medium",
            "思考模式",
        )
        console.print(tbl)
        console.print(selection_progress(selected, field_count))
        console.print()
        console.print(
            f"  [dim]↑↓ 选择 · [/][accent]Enter[/][dim] 修改字段 · "
            f"[/][accent]r[/][dim] 重置全部 · "
            f"[/][accent]s[/][dim] 保存并返回 · "
            f"[/][accent]q[/][dim] 放弃[/]"
        )

        if has_readchar():
            key = read_key()
            if key in (KEY_UP, KEY_LEFT):
                selected = (selected - 1) % field_count
                continue
            if key in (KEY_DOWN, KEY_RIGHT):
                selected = (selected + 1) % field_count
                continue
            if key in (KEY_ESC, "q"):
                return
            ans = "edit" if key == KEY_ENTER else key.lower()
        else:
            try:
                ans = console.input(
                    "  [dim]字段名称 / enter / r / s / q >[/] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return

        if ans in ("q", ""):
            return
        if ans == "s":
            overrides[model] = params
            if _save_overrides(overrides):
                console.print(f"  [ok]✓ 已保存到 {OVERRIDE_PATH}[/]")
            else:
                console.print("  [err]✗ 保存失败[/]")
            if model == copilot.model:
                for k, v in params.items():
                    if hasattr(copilot, k):
                        setattr(copilot, k, v)
                if "think_level" in params:
                    copilot.think_level = params["think_level"]
            wait_for_return(console, "  [dim]按任意键继续…[/] ")
            return
        if ans == "r":
            params = {}
            console.print("  [dim]已重置[/]")
            continue

        if ans not in ("edit", "enter", "select"):
            field_names = [field[0] for field in FIELDS] + ["think_level"]
            if ans not in field_names:
                console.print("  [err]✗ 未知字段[/]")
                continue
            selected = field_names.index(ans)

        if selected < len(FIELDS):
            name, typ, lo, hi, _ = FIELDS[selected]
            try:
                raw = console.input(f"  [dim]{name} =[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if not raw:
                params.pop(name, None)
                continue
            try:
                v = typ(raw)
            except (TypeError, ValueError):
                console.print("  [err]✗ 类型错误[/]")
                continue
            if not (lo <= v <= hi):
                console.print(f"  [err]✗ 范围 {lo} - {hi}[/]")
                continue
            params[name] = v
            continue

        if selected == len(FIELDS):
            console.print(f"  [dim]可选：[/]{' / '.join(THINK_LEVELS)}")
            try:
                raw = console.input("  [dim]think_level =[/] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                continue
            if raw in THINK_LEVELS:
                params["think_level"] = raw
            elif not raw:
                params.pop("think_level", None)
            else:
                console.print("  [err]✗ 无效档位[/]")
            continue