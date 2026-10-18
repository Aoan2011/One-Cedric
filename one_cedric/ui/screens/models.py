"""模型管理：我的模型（持久化档案）+ 远端模型 + 参数调节。"""
from __future__ import annotations

from pathlib import Path

from rich import box
from rich.table import Table

from ...config import ACCENT, BRAND, DIM_C, OK_C
from ...my_models import (
    apply_to_copilot,
    get_profile,
    list_profiles,
    remove_profile,
    switch_profile,
    upsert_profile,
)
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


THINK_LEVELS = ["minimal", "low", "medium", "high", "max", "xhigh", "ultra"]


def run_models_screen(console, copilot) -> None:
    from ..keys import (
        KEY_DOWN,
        KEY_ENTER,
        KEY_ESC,
        KEY_LEFT,
        KEY_RIGHT,
        KEY_UP,
        has_readchar,
        read_key,
    )

    selected = 0
    while True:
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ 模型管理[/]")
        console.print(f"  [dim]当前模型: [accent]{copilot.model}[/]"
                      f"  ·  [accent]{copilot.host}[/]")
        console.print()

        with console.status(
            f"[{ACCENT}]正在获取远端模型列表…[/]", spinner="dots"
        ):
            remote = _fetch_models(copilot)
        if not remote:
            console.print(
                f"  [warn]⚠ 无法从 {copilot.host} 获取远端模型[/]"
            )
            console.print(f"  [dim]当前模型：[accent]{copilot.model}[/]")
            remote = [copilot.model]

        mine = list_profiles()
        overrides = _load_overrides()

        # ── 组装列表：我的模型 → 远端 → 新增 ──
        items = []
        for p in mine:
            items.append({"kind": "mine", "profile": p})
        for m in remote:
            if any(p.get("model") == m for p in mine):
                continue
            items.append({"kind": "remote", "model": m})
        items.append({"kind": "new"})
        selected = min(selected, len(items) - 1)

        active_name = ""
        from ...my_models import load as _mm_load
        _mm = _mm_load()
        active_name = _mm.get("active", "")

        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}",
                    padding=(0, 1))
        tbl.add_column("", width=2)
        tbl.add_column("模型", style="bold")
        tbl.add_column("连接 / 参数")
        tbl.add_column("价格 / 1M tokens")

        from ...pricing import pricing_for
        if mine:
            tbl.add_row("", f"[bold {ACCENT}]▣ 我的模型[/]",
                        f"[dim]{len(mine)} 个档案[/]", "",
                        end_section=True)
            for i, it in enumerate(items):
                if it["kind"] != "mine":
                    continue
                p = it["profile"]
                model = p.get("model", "?")
                label = f"★ {p['name']}"
                if model:
                    label += f"  [dim]({model})[/]"
                if active_name == p["name"]:
                    label += f"  [{OK_C}]当前[/]"
                if i == selected:
                    label = f"[bold {BRAND}]{label}[/]"
                params = overrides.get(model, {})
                n_params = len(params)
                conn = f"[dim]{p.get('host') or '?'}[/]"
                if n_params:
                    conn += f"  ·  {n_params} 项参数"
                if p.get("note"):
                    conn += f"  ·  [dim]{p['note'][:18]}[/]"
                _cached, ip, op = pricing_for(model)
                tbl.add_row(
                    f"[{BRAND}]▸[/]" if i == selected else "",
                    label, conn,
                    f"${ip:g} / ${op:g}",
                )

        # 远端模型
        any_remote = any(it["kind"] == "remote" for it in items)
        if any_remote:
            tbl.add_row("", f"[bold {DIM_C}]◈ 远端模型[/]",
                        f"[dim]{copilot.host}[/]", "",
                        end_section=True)
            for i, it in enumerate(items):
                if it["kind"] != "remote":
                    continue
                model = it["model"]
                label = model
                if model == copilot.model:
                    label += f"  [{OK_C}]当前使用[/]"
                if i == selected:
                    label = f"[bold {BRAND}]{label}[/]"
                params = overrides.get(model, {})
                if params:
                    p_str = " · ".join(
                        f"{k}={v}" for k, v in list(params.items())[:4])
                    conn = f"[dim]{p_str}[/]"
                else:
                    conn = "[dim]默认[/]"
                _cached, ip, op = pricing_for(model)
                tbl.add_row(
                    f"[{BRAND}]▸[/]" if i == selected else "",
                    label, conn,
                    f"${ip:g} / ${op:g}",
                )

        # 新增
        tbl.add_section()
        tbl.add_row(
            f"[{BRAND}]▸[/]" if items[-1]["kind"] == "new"
            and selected == len(items) - 1 else "",
            (f"[bold {BRAND}]＋ 新增我的模型[/]"
             if selected == len(items) - 1 else "＋ 新增我的模型"),
            "[dim]保存一个模型连接档案（可持久化、一键切换）[/]",
            "—",
            end_section=True,
        )

        console.print(tbl)
        console.print(selection_progress(selected, len(items)))
        console.print()
        console.print(
            "  [dim]操作：[/][accent]↑↓[/][dim] 选择 · "
            "[/][accent]Enter[/][dim] 切换 · "
            "[/][accent]n[/][dim] 新增档案 · "
            "[/][accent]e[/][dim] 编辑档案 · "
            "[/][accent]d[/][dim] 删除 · "
            "[/][accent]p[/][dim] 调参 · "
            "[/][accent]c[/][dim] 价格 · "
            "[/][accent]t[/][dim] 测试 · "
            "[/][accent]r[/][dim] 刷新 · "
            "[/][accent]q[/][dim] 返回[/]"
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
                    "  [dim]Enter 切换 · n 新增 · e 编辑 · d 删除 · "
                    "p 参数 · c 价格 · t 测试 · r 刷新 · q 返回 >[/] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return

        if sel in ("q", ""):
            return
        if sel == "r":
            continue
        if sel == "t":
            _test_connection(console, copilot)
            continue

        cur = items[selected]
        cur_model = (cur["profile"].get("model") if cur["kind"] == "mine"
                     else cur.get("model") if cur["kind"] == "remote"
                     else None)
        cur_profile = cur.get("profile") if cur["kind"] == "mine" else None

        if sel == "n":
            _add_model(console, copilot)
            selected = 0
            continue
        if sel == "e":
            if cur_profile:
                _edit_profile(console, copilot, cur_profile["name"])
            else:
                console.print("  [warn]请先选择一个「我的模型」档案。[/]")
                wait_for_return(console, "  [dim]按任意键继续…[/] ")
            continue
        if sel == "d":
            if cur_profile:
                _delete_profile(console, copilot, cur_profile["name"])
            else:
                console.print("  [warn]请先选择一个「我的模型」档案。[/]")
                wait_for_return(console, "  [dim]按任意键继续…[/] ")
            continue
        if sel == "p":
            if cur_model:
                _edit_model_params(console, copilot, cur_model)
            else:
                console.print("  [warn]请先选择一个模型。[/]")
            continue
        if sel == "c":
            if cur_model:
                _edit_model_pricing(console, cur_model)
            else:
                console.print("  [warn]请先选择一个模型。[/]")
            continue
        if sel == "enter":
            if cur["kind"] == "mine":
                ok, msg = switch_profile(copilot, cur_profile["name"])
                console.print(f"  [{'ok' if ok else 'err'}]"
                              f"{'✓' if ok else '✗'} {msg}[/]")
            elif cur["kind"] == "remote":
                copilot.model = cur_model
                copilot.config.setdefault("default", {})["model"] = cur_model
                console.print(f"  [ok]✓ 已切换: {cur_model}[/]")
            else:
                _add_model(console, copilot)
                selected = 0
            continue

        console.print("  [err]✗ 未知操作[/]")


def _prompt_text(console, label: str, current: str = "") -> str:
    try:
        raw = console.input(f"  [dim]{label}[/] ").strip()
    except (EOFError, KeyboardInterrupt):
        return "__CANCEL__"
    if not raw and current:
        return current
    return raw


def _add_model(console, copilot) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ 新增我的模型[/]")
    console.print("  [dim]保存一个模型连接档案，之后可一键切换。[/]")
    console.print()
    try:
        host = console.input(
            "  [dim]API 地址（如 http://localhost:11434 或 "
            "https://api.deepseek.com）=[/] "
        ).strip().rstrip("/")
        if not host:
            return
        model = console.input("  [dim]模型 ID（如 deepseek-flash）=[/] ").strip()
        if not model:
            return
        from .settings import _masked_input
        api_key = _masked_input(console, "api_key（可留空）")
        note = console.input("  [dim]备注（可留空）=[/] ").strip()
        name = console.input(
            f"  [dim]档案名称（Enter 使用 {model}）=[/] ").strip() or model
    except (EOFError, KeyboardInterrupt):
        return

    if upsert_profile(name, {
        "host": host, "model": model, "api_key": api_key,
        "note": note, "created_at": 0,
    }):
        ok, msg = switch_profile(copilot, name)
        console.print(f"  [ok]✓ 已保存档案「{name}」[/]")
        console.print(f"  [{'ok' if ok else 'err'}]"
                      f"{'✓' if ok else '✗'} {msg}[/]")
    else:
        console.print("  [err]✗ 保存失败[/]")
    wait_for_return(console, "  [dim]按任意键继续…[/] ")


def _edit_profile(console, copilot, name: str) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ 编辑档案 · {name}[/]")
    console.print()
    p = get_profile(name) or {}
    fields = [
        ("host", p.get("host", "")),
        ("model", p.get("model", "")),
        ("api_key", p.get("api_key", "")),
        ("note", p.get("note", "")),
    ]
    labels = {
        "host": "API 地址", "model": "模型 ID",
        "api_key": "API Key", "note": "备注",
    }
    for key, cur in fields:
        console.print(
            f"  [dim]{labels[key]}[/]  [accent]{cur or '（空）'}[/]")
    console.print()
    console.print("  [dim]Enter 直接跳过保留原值，q 取消。[/]")
    console.print()
    updates: dict = {}
    for key, cur in fields:
        if key == "api_key":
            from .settings import _masked_input
            raw = _masked_input(console, f"{labels[key]}（Enter 保留）")
            if raw:
                updates[key] = raw
            continue
        raw = _prompt_text(console, f"{labels[key]}（Enter 保留）=", cur)
        if raw == "__CANCEL__":
            return
        if raw != cur:
            updates[key] = raw
    if not updates:
        console.print("  [dim]（无修改）[/]")
        return
    if upsert_profile(name, updates):
        console.print(f"  [ok]✓ 已更新档案「{name}」[/]")
        if get_profile(name) and get_profile(name).get("model"):
            apply_to_copilot(copilot, get_profile(name))
            console.print("  [dim]已同步到当前会话。[/]")
    else:
        console.print("  [err]✗ 保存失败[/]")
    wait_for_return(console, "  [dim]按任意键继续…[/] ")


def _delete_profile(console, copilot, name: str) -> None:
    console.print(f"  [warn]删除档案「{name}」？[/]")
    try:
        ans = console.input("  [dim]y 删除 / n 取消 >[/] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if ans != "y":
        console.print("  [dim]已取消。[/]")
        return
    if remove_profile(name):
        console.print(f"  [ok]✓ 已删除「{name}」[/]")
    else:
        console.print("  [err]✗ 删除失败[/]")
    wait_for_return(console, "  [dim]按任意键继续…[/] ")


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
        KEY_DOWN,
        KEY_ENTER,
        KEY_ESC,
        KEY_LEFT,
        KEY_RIGHT,
        KEY_UP,
        has_readchar,
        read_key,
    )

    overrides = _load_overrides()
    params = dict(overrides.get(model, {}))
    selected = 0
    field_count = len(FIELDS) + 2

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
        d_cfg = (getattr(copilot, "config", None) or {}).get("default", {})
        rm_default = str(d_cfg.get("reasoning_model", "auto") or "auto")
        rm = str(params.get("reasoning_model", rm_default))
        tbl.add_row(
            f"[{BRAND}]▸[/]" if selected == len(FIELDS) + 1 else "",
            "reasoning_model",
            rm,
            rm_default,
            "是否推理模型：auto/on/off（on 时真正发送推理参数）",
        )
        console.print(tbl)
        console.print(selection_progress(selected, field_count))
        console.print()
        console.print(
            "  [dim]↑↓ 选择 · [/][accent]Enter[/][dim] 修改字段 · "
            "[/][accent]r[/][dim] 重置全部 · "
            "[/][accent]s[/][dim] 保存并返回 · "
            "[/][accent]q[/][dim] 放弃[/]"
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
            field_names = ([field[0] for field in FIELDS]
                           + ["think_level", "reasoning_model"])
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

        if selected == len(FIELDS) + 1:
            console.print(
                "  [dim]可选：[/][accent]auto[/][dim]（按模型名判断）· "
                "[/][accent]on[/][dim]（是推理模型）· "
                "[/][accent]off[/][dim]（不是）[/]")
            try:
                raw = console.input(
                    "  [dim]reasoning_model =[/] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                continue
            if raw in ("auto", "on", "off"):
                params["reasoning_model"] = raw
            elif raw in ("true", "1", "yes"):
                params["reasoning_model"] = "on"
            elif raw in ("false", "0", "no"):
                params["reasoning_model"] = "off"
            elif not raw:
                params.pop("reasoning_model", None)
            else:
                console.print("  [err]✗ 无效取值[/]")
            continue
