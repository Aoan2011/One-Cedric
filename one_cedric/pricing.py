"""模型价格管理：读写 + 内置默认 + provider 分组 + JSON 导入导出。

存储: ~/.one-cedric/pricing.toml
单位: 美元 / 1M tokens
"""
from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None


PRICING_PATH = Path.home() / ".one-cedric" / "pricing.toml"


# 内置价格：$/1M tokens
# 格式: model_substring -> (input_cached, input, output)
BUILTIN_PRICING = {
    "gpt-4o-mini":       (0.075,  0.15,   0.60),
    "gpt-4o":            (1.25,   2.50,  10.00),
    "gpt-4-turbo":       (5.00,  10.00,  30.00),
    "gpt-4":             (30.00, 30.00,  60.00),
    "gpt-3.5-turbo":     (0.50,   0.50,   1.50),
    "o1-mini":           (0.55,   1.10,   4.40),
    "o1":                (7.50,  15.00,  60.00),
    "o3-mini":           (0.55,   1.10,   4.40),
    "o3":                (5.00,  10.00,  40.00),
    "claude-3-opus":     (1.50,  15.00,  75.00),
    "claude-3-sonnet":   (0.30,   3.00,  15.00),
    "claude-3-haiku":    (0.03,   0.25,   1.25),
    "claude-3-5-sonnet": (0.30,   3.00,  15.00),
    "claude-3-5-haiku":  (0.10,   1.00,   5.00),
    "gemini-1.5-pro":    (0.3125, 1.25,   5.00),
    "gemini-1.5-flash":  (0.01875, 0.075, 0.30),
    "gemini-2.0-flash":  (0.025,  0.10,   0.40),
    "deepseek-chat":     (0.014,  0.14,   0.28),
    "deepseek-reasoner": (0.14,   0.55,   2.19),
    "qwen":              (0.0,    0.0,    0.0),
    "llama":             (0.0,    0.0,    0.0),
    "mistral":           (0.0,    0.0,    0.0),
}


def _path() -> Path:
    PRICING_PATH.parent.mkdir(parents=True, exist_ok=True)
    return PRICING_PATH


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def load_user_pricing() -> dict:
    p = _path()
    if not p.exists() or tomllib is None:
        return {}
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    models = raw.get("models") or {}
    out = {}
    for name, params in models.items():
        if not isinstance(params, dict):
            continue
        try:
            ic = float(params.get("input_cached", 0))
            i = float(params.get("input", 0))
            o = float(params.get("output", 0))
            out[name] = (ic, i, o)
        except (TypeError, ValueError):
            continue
    return out


def save_user_pricing(data: dict) -> bool:
    lines = [
        "# One Cedric 模型价格表",
        "# 单位: 美元 / 1M tokens",
        "# 字段: input_cached / input / output",
        "",
    ]
    for name in sorted(data.keys()):
        ic, i, o = data[name]
        lines.append(f"[models.{name}]")
        lines.append(f"input_cached = {ic}")
        lines.append(f"input = {i}")
        lines.append(f"output = {o}")
        lines.append("")
    try:
        p = _path()
        p.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def pricing_for(model: str) -> tuple:
    m = (model or "").lower()
    user = load_user_pricing()

    if m in user:
        return user[m]
    for k, v in user.items():
        if k.lower() in m:
            return v

    if m in BUILTIN_PRICING:
        return BUILTIN_PRICING[m]
    for k, v in BUILTIN_PRICING.items():
        if k in m:
            return v

    return (0.0, 0.0, 0.0)


def compute_cost(model: str, in_tok: int, out_tok: int,
                 cached_tok: int = 0) -> float:
    ic, i, o = pricing_for(model)
    cached_tok = max(0, min(int(cached_tok or 0), int(in_tok or 0)))
    uncached_in = max(0, int(in_tok or 0) - cached_tok)
    return (
        cached_tok * ic / 1_000_000 +
        uncached_in * i / 1_000_000 +
        int(out_tok or 0) * o / 1_000_000
    )


def human_price(v: float) -> str:
    if v == 0:
        return "免费"
    if v < 0.01:
        return f"${v:.5f}"
    if v < 1:
        return f"${v:.3f}"
    return f"${v:.2f}"


def format_pricing_line(model: str) -> str:
    ic, i, o = pricing_for(model)
    if ic == 0 and i == 0 and o == 0:
        return f"{model}: 免费"
    return (f"{model}: cached {human_price(ic)} / "
            f"input {human_price(i)} / output {human_price(o)}  "
            f"（/1M tokens）")


def stats() -> str:
    user = load_user_pricing()
    lines = [
        f"用户自定义: {len(user)} 个模型",
        f"内置默认: {len(BUILTIN_PRICING)} 个模型",
        f"配置文件: {PRICING_PATH}",
    ]
    if user:
        lines.append("")
        lines.append("自定义模型：")
        for name in sorted(user.keys()):
            lines.append(f"  {format_pricing_line(name)}")
    return "\n".join(lines)


def import_builtin(model: str) -> bool:
    m = (model or "").lower()
    found = None
    if m in BUILTIN_PRICING:
        found = m
    else:
        for k in BUILTIN_PRICING:
            if k in m:
                found = k
                break
    if not found:
        return False
    user = load_user_pricing()
    user[found] = BUILTIN_PRICING[found]
    return save_user_pricing(user)


def import_all_builtin() -> int:
    user = load_user_pricing()
    n = 0
    for k, v in BUILTIN_PRICING.items():
        if k not in user:
            user[k] = v
            n += 1
    if n > 0:
        save_user_pricing(user)
    return n


# ═══════════════════════════════════════════════════════════════════════ #
# Provider 分组
# ═══════════════════════════════════════════════════════════════════════ #

PROVIDER_PATTERNS = [
    ("openai", ["gpt-", "o1", "o3", "o4", "text-davinci", "davinci",
                "chatgpt"]),
    ("anthropic", ["claude"]),
    ("google", ["gemini", "palm", "bison"]),
    ("deepseek", ["deepseek"]),
    ("qwen", ["qwen", "tongyi"]),
    ("meta", ["llama", "llama2", "llama3"]),
    ("mistral", ["mistral", "mixtral", "codestral"]),
    ("cohere", ["command-", "cohere"]),
    ("xai", ["grok"]),
    ("local", ["ollama", "llama.cpp", "vllm"]),
]


def provider_of(model: str) -> str:
    m = (model or "").lower()
    for prov, pats in PROVIDER_PATTERNS:
        for p in pats:
            if m.startswith(p) or p in m:
                return prov
    return "other"


def group_by_provider(data: dict) -> dict:
    groups: dict = {}
    for name, val in data.items():
        prov = provider_of(name)
        groups.setdefault(prov, {})[name] = val
    return groups


def format_grouped_pricing(data: dict) -> str:
    if not data:
        return "（无数据）"
    groups = group_by_provider(data)
    lines = []
    for prov in sorted(groups.keys()):
        models = groups[prov]
        lines.append(f"【{prov}】（{len(models)}）")
        for name in sorted(models.keys()):
            ic, i, o = models[name]
            if ic == 0 and i == 0 and o == 0:
                lines.append(f"  {name:<32} 免费")
            else:
                lines.append(
                    f"  {name:<32} "
                    f"cached {human_price(ic):>9} / "
                    f"in {human_price(i):>9} / "
                    f"out {human_price(o):>9}"
                )
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════ #
# JSON 导入 / 导出
# ═══════════════════════════════════════════════════════════════════════ #

def export_json(path: str = "") -> tuple:
    import json as _json
    import datetime as _dt
    user = load_user_pricing()
    if not user:
        return False, "无自定义价格可导出", 0
    payload = {
        "version": 1,
        "exported_at": _dt.datetime.now().isoformat(),
        "unit": "USD per 1M tokens",
        "fields": ["input_cached", "input", "output"],
        "models": {
            name: {
                "input_cached": v[0],
                "input": v[1],
                "output": v[2],
                "provider": provider_of(name),
            }
            for name, v in user.items()
        },
    }
    if not path:
        path = str(Path.cwd() / "cedric-pricing.json")
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    except OSError as exc:
        return False, str(exc), 0
    return True, str(out), len(user)


def import_json(path: str, mode: str = "merge") -> tuple:
    import json as _json
    if not path:
        return False, "需要 path", 0

    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return False, f"文件不存在: {path}", 0

    try:
        raw = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"解析失败: {exc}", 0

    if isinstance(raw, dict) and "models" in raw \
            and isinstance(raw["models"], dict):
        src = raw["models"]
    elif isinstance(raw, dict):
        src = raw
    else:
        return False, "JSON 顶层必须是对象", 0

    parsed: dict = {}
    for name, params in src.items():
        if not isinstance(params, dict):
            continue
        try:
            ic = float(params.get("input_cached", 0))
            i = float(params.get("input", 0))
            o = float(params.get("output", 0))
            parsed[name] = (ic, i, o)
        except (TypeError, ValueError):
            continue

    if not parsed:
        return False, "没有可导入的有效数据", 0

    if mode == "replace":
        save_user_pricing(parsed)
        return True, f"已替换为 {len(parsed)} 个模型", len(parsed)

    user = load_user_pricing()
    added = 0
    updated = 0
    for name, val in parsed.items():
        if name in user:
            if user[name] != val:
                user[name] = val
                updated += 1
        else:
            user[name] = val
            added += 1
    save_user_pricing(user)
    msg = f"合并完成：新增 {added}，更新 {updated}"
    return True, msg, added + updated


def builtin_export_json(path: str = "") -> tuple:
    import json as _json
    payload = {
        "version": 1,
        "source": "builtin",
        "unit": "USD per 1M tokens",
        "models": {
            name: {
                "input_cached": v[0],
                "input": v[1],
                "output": v[2],
                "provider": provider_of(name),
            }
            for name, v in BUILTIN_PRICING.items()
        },
    }
    if not path:
        path = str(Path.cwd() / "cedric-pricing-builtin.json")
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    except OSError as exc:
        return False, str(exc), 0
    return True, str(out), len(BUILTIN_PRICING)