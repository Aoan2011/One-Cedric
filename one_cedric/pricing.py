"""模型价格管理：读写 + 内置默认 + provider 分组 + JSON 导入导出 + 峰谷价格。

存储: ~/.one-cedric/pricing.toml
单位: 美元 / 1M tokens

峰谷价格: 同一文件的 ``[peak]`` 段描述「谷价时段」（如 DeepSeek 官方
错峰优惠：UTC 16:30–00:30，deepseek-chat 五折、deepseek-reasoner
2.5 折）；``compute_cost`` 会按当下的时刻自动乘上对应折扣。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
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


#: 峰谷价格默认配置。窗口/时区/折扣取自 DeepSeek 官方错峰优惠：
#: UTC 16:30–00:30 为谷价，deepseek-chat 五折、deepseek-reasoner 2.5 折。
#: 其他模型不受影响（default_discount = 1.0 表示不打折）。
DEFAULT_PEAK = {
    "enabled": True,
    "windows": "16:30-00:30",
    "tz": "UTC",
    "default_discount": 1.0,
    "discounts": {
        "deepseek-chat": 0.5,
        "deepseek-reasoner": 0.25,
    },
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


def save_user_pricing(data: dict, peak=None) -> bool:
    """写回 pricing.toml。``peak=None`` 时原样保留已有的 ``[peak]`` 段。"""
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
    if peak is None:
        peak = _peak_table()
    if peak:
        _dump_peak(lines, peak)
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
                 cached_tok: int = 0, at=None) -> float:
    """按 ``at``（默认此刻）计价；谷价时段自动乘上峰谷折扣。"""
    ic, i, o = pricing_for(model)
    cached_tok = max(0, min(int(cached_tok or 0), int(in_tok or 0)))
    uncached_in = max(0, int(in_tok or 0) - cached_tok)
    cost = (
        cached_tok * ic / 1_000_000 +
        uncached_in * i / 1_000_000 +
        int(out_tok or 0) * o / 1_000_000
    )
    if cost > 0:
        try:
            cost *= peak_state(model, at)["discount"]
        except Exception:
            pass
    return cost


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
    text = (f"{model}: cached {human_price(ic)} / "
            f"input {human_price(i)} / output {human_price(o)}  "
            f"（/1M tokens）")
    cfg = load_peak_config()
    if cfg.get("enabled"):
        rate = peak_rate(model, cfg)
        if rate != 1.0:
            text += f"  · 谷价 ×{rate:g}"
    return text


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
# 峰谷价格（错峰折扣）
# ═══════════════════════════════════════════════════════════════════════ #

#: "16:30-00:30"，分隔符可以用 - ~ ～ —；支持写多个（逗号/空格隔开）
_WINDOW_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*[-\u007e\uff5e\u2014]\s*(\d{1,2}):(\d{2})")
#: "+8" / "UTC+8" / "-05:30"
_TZ_RE = re.compile(r"^(?:utc|gmt)?\s*([+-])\s*(\d{1,2})(?::(\d{2}))?$")
#: TOML 裸键（模型名含点号等特殊字符时改用引号包裹）
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(name: str) -> str:
    s = str(name)
    return s if _KEY_RE.match(s) else f'"{_esc(s)}"'


def _peak_table() -> dict:
    """读 pricing.toml 里的原始 ``[peak]`` 段（不存在则空 dict）。"""
    p = _path()
    if not p.exists() or tomllib is None:
        return {}
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    peak = raw.get("peak")
    return peak if isinstance(peak, dict) else {}


def _dump_peak(lines: list, peak: dict) -> None:
    """把 ``[peak]`` 段写进 tomli 风格的行列表。"""
    lines.append("[peak]")
    if isinstance(peak.get("enabled"), bool):
        lines.append(f"enabled = {str(peak['enabled']).lower()}")
    if isinstance(peak.get("windows"), str):
        lines.append(f'windows = "{_esc(peak["windows"])}"')
    if isinstance(peak.get("tz"), str):
        lines.append(f'tz = "{_esc(peak["tz"])}"')
    value = peak.get("default_discount")
    if isinstance(value, (int, float)):
        lines.append(f"default_discount = {float(value):g}")
    discounts = peak.get("discounts")
    if isinstance(discounts, dict) and discounts:
        lines.append("")
        lines.append("[peak.discounts]")
        for name in sorted(discounts.keys()):
            try:
                mult = float(discounts[name])
            except (TypeError, ValueError):
                continue
            lines.append(f"{_toml_key(str(name))} = {mult:g}")
    lines.append("")


def load_peak_config() -> dict:
    """内置默认 + 用户 ``[peak]`` 合并后的配置。"""
    raw = _peak_table()
    cfg = {
        "enabled": DEFAULT_PEAK["enabled"],
        "windows": DEFAULT_PEAK["windows"],
        "tz": DEFAULT_PEAK["tz"],
        "default_discount": DEFAULT_PEAK["default_discount"],
        "discounts": dict(DEFAULT_PEAK["discounts"]),
    }
    if isinstance(raw.get("enabled"), bool):
        cfg["enabled"] = raw["enabled"]
    if isinstance(raw.get("windows"), str):
        cfg["windows"] = raw["windows"]
    if isinstance(raw.get("tz"), str):
        cfg["tz"] = raw["tz"]
    try:
        if raw.get("default_discount") is not None:
            cfg["default_discount"] = float(raw["default_discount"])
    except (TypeError, ValueError):
        pass
    raw_discounts = raw.get("discounts")
    if isinstance(raw_discounts, dict):
        for name, value in raw_discounts.items():
            try:
                cfg["discounts"][str(name)] = float(value)
            except (TypeError, ValueError):
                continue
    return cfg


def save_peak_config(cfg: dict) -> bool:
    """把（已归一化的）峰谷配置写回 ``[peak]``；``[models]`` 原样保留。"""
    return save_user_pricing(load_user_pricing(), peak=cfg)


def parse_tz(spec: str):
    """时区描述 → UTC 偏移小时数；``"local"``/空 返回 None（用本机时区）。"""
    s = (spec or "").strip().lower()
    if s in ("", "local"):
        return None
    if s in ("utc", "gmt", "z", "+0", "+00", "+00:00"):
        return 0.0
    match = _TZ_RE.match(s)
    if not match:
        return None
    sign, hours = match.group(1), int(match.group(2))
    minutes = int(match.group(3) or 0)
    value = hours + minutes / 60
    return -value if sign == "-" else value


def parse_windows(spec: str) -> list:
    """``"16:30-00:30"`` 之类 → [(990, 30)]（当天分钟数，跨午夜 start > end）。"""
    out = []
    for match in _WINDOW_RE.finditer(spec or ""):
        h1, m1, h2, m2 = (int(g) for g in match.groups())
        if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
            continue
        start = min(h1 * 60 + m1, 1440)
        end = min(h2 * 60 + m2, 1440)
        if start == end:
            continue
        out.append((start, end))
    return out


def _fmt_minute(value: int) -> str:
    value = int(value) % 1440
    return f"{value // 60:02d}:{value % 60:02d}"


def windows_text(windows: list) -> str:
    """[(990, 30)] → ``"16:30-00:30"``。"""
    return " ".join(f"{_fmt_minute(s)}-{_fmt_minute(e)}" for s, e in windows)


def local_windows_text(windows: list, tz: str) -> str:
    """把（用 ``tz`` 表达的）窗口换算成本机时间，便于对照。"""
    offset = parse_tz(tz)
    if offset is None:
        return ""
    local = datetime.now().astimezone().utcoffset()
    delta = int(round((local.total_seconds() / 3600 if local else 0)
                      - offset) * 60)
    if delta == 0:
        return ""
    return " ".join(
        f"{_fmt_minute(s + delta)}-{_fmt_minute(e + delta)}"
        for s, e in windows)


def _minute_in_windows(minute: int, windows: list) -> bool:
    for start, end in windows:
        if start < end:
            if start <= minute < end:
                return True
        elif minute >= start or minute < end:  # 跨午夜
            return True
    return False


def _seconds_until_flip(minute: int, seconds: float, windows: list) -> int:
    """距离「谷价 ↔ 峰价」下一次切换的秒数。"""
    delay = 1440.0
    for start, end in windows:
        if start < end:
            delta = ((end - minute) if start <= minute < end
                     else (start - minute) % 1440)
        else:
            inside = minute >= start or minute < end
            delta = ((end - minute) % 1440) if inside \
                else (start - minute) % 1440
        if delta < delay:
            delay = delta
    return max(0, int(delay * 60 - seconds))


def _now_minute(at, tz_hours) -> tuple:
    """(当天分钟数, 秒内小数)；``at`` 为 None 时取此刻。

    ``tz_hours`` 为 None 表示用本机时区（``at`` 带时区时先转本机）；
    否则按 UTC 偏移换算（``at`` 为 naive 时按 UTC 解释）。
    """
    moment = at or datetime.now()
    if tz_hours is None:
        if moment.tzinfo is not None:
            moment = moment.astimezone()
        return (moment.hour * 60 + moment.minute,
                moment.second + moment.microsecond / 1e6)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    utc = moment.astimezone(timezone.utc)
    total = (utc.hour * 60 + utc.minute + round(tz_hours * 60)) % 1440
    return total, utc.second + utc.microsecond / 1e6


def peak_rate(model: str, cfg: dict | None = None) -> float:
    """模型在谷价时段的价率（1.0 = 无差价）；按最长子串匹配。"""
    cfg = cfg if cfg is not None else load_peak_config()
    m = (model or "").lower()
    try:
        best_rate = float(cfg.get("default_discount") or 1.0)
    except (TypeError, ValueError):
        best_rate = 1.0
    best_key = ""
    for name, value in (cfg.get("discounts") or {}).items():
        key = str(name).lower()
        if not key:
            continue
        try:
            rate = float(value)
        except (TypeError, ValueError):
            continue
        if key == m:
            return rate
        if m and key in m and len(key) > len(best_key):
            best_key, best_rate = key, rate
    return best_rate


def peak_state(model: str = "", at=None) -> dict:
    """当前峰谷状态（底栏与 ``/peak`` 共用）。

    字段: ``enabled`` 总开关 · ``supported`` 当前模型有差价（底栏据此显示）
    · ``offpeak`` 是否谷价时段 · ``rate`` 谷价倍率 · ``discount`` 当前生效
    倍率（谷内 = rate，峰内 = 1.0）· ``seconds_to_change`` 距切换秒数。
    """
    cfg = load_peak_config()
    windows = parse_windows(cfg.get("windows", ""))
    rate = peak_rate(model, cfg)
    state = {
        "enabled": bool(cfg.get("enabled")),
        "supported": False,
        "offpeak": False,
        "rate": rate,
        "discount": 1.0,
        "tz": cfg.get("tz", "UTC"),
        "windows": windows,
        "seconds_to_change": None,
    }
    if not (state["enabled"] and windows):
        return state
    minute, seconds = _now_minute(at, parse_tz(state["tz"]))
    offpeak = _minute_in_windows(minute, windows)
    state["offpeak"] = offpeak
    state["supported"] = rate != 1.0
    state["discount"] = rate if offpeak else 1.0
    state["seconds_to_change"] = _seconds_until_flip(minute, seconds, windows)
    return state


def format_duration(seconds) -> str:
    """秒 → ``3h12m`` / ``45m`` / ``30s``。"""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return ""
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def apply_peak_preset(name: str) -> tuple:
    """应用内置峰谷预设：``deepseek``（官方错峰）或 ``off``（关闭）。"""
    key = (name or "").strip().lower()
    cfg = load_peak_config()
    if key in ("deepseek", "ds", "deepseek-off-peak"):
        cfg["enabled"] = True
        cfg["windows"] = DEFAULT_PEAK["windows"]
        cfg["tz"] = DEFAULT_PEAK["tz"]
        discounts = dict(cfg.get("discounts") or {})
        discounts.update(DEFAULT_PEAK["discounts"])
        cfg["discounts"] = discounts
        if save_peak_config(cfg):
            return True, "已启用 DeepSeek 错峰预设（UTC 16:30-00:30）"
        return False, "保存失败"
    if key in ("off", "none", "clear"):
        cfg["enabled"] = False
        if save_peak_config(cfg):
            return True, "已关闭峰谷价格"
        return False, "保存失败"
    return False, f"未知预设：{name}（可用 deepseek | off）"


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
    import datetime as _dt
    import json as _json
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
