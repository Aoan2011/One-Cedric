"""我的模型：用户自建的模型档案，持久化到 ~/.one-cedric/my_models.toml。

每个档案包含：名称、模型 ID、API 地址、API Key、备注，以及可选参数
（temperature / think_level / max_tokens / context_limit 等）。

- 档案与 model_overrides.toml 协同：应用档案时把参数写入对应模型的覆盖，
  请求时自动生效；连接信息（model/host/api_key）写入全局 config.toml。
- API Key 与现有 config.toml 一样以明文保存（仅存本机 ~/.one-cedric/）。
"""
from __future__ import annotations

import time
from pathlib import Path

MY_MODELS_PATH = Path.home() / ".one-cedric" / "my_models.toml"

PARAM_FIELDS = (
    "temperature", "top_p", "max_tokens", "frequency_penalty",
    "presence_penalty", "context_limit", "think_level",
)

_DEFAULT_PROFILE = {
    "temperature": 0.2,
    "think_level": "medium",
}


def _esc(s) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _fmt_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{_esc(v)}"'


def load() -> dict:
    """返回 {"active": str, "profiles": {name: profile}}。"""
    empty = {"active": "", "profiles": {}}
    from ._toml import tomllib
    if not MY_MODELS_PATH.exists():
        return empty
    try:
        raw = tomllib.loads(MY_MODELS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return empty
    profiles = dict(raw.get("profiles", {}) or {})
    out = {}
    for name, p in profiles.items():
        if not isinstance(p, dict):
            continue
        rec = {
            "name": str(name),
            "model": str(p.get("model") or ""),
            "host": str(p.get("host") or ""),
            "api_key": str(p.get("api_key") or ""),
            "note": str(p.get("note") or ""),
            "created_at": float(p.get("created_at") or 0),
        }
        for k in PARAM_FIELDS:
            if k in p and p[k] is not None:
                rec[k] = p[k]
        out[rec["name"]] = rec
    active = str(raw.get("active") or "")
    if active and active not in out:
        active = ""
    return {"active": active, "profiles": out}


def save(data: dict) -> bool:
    lines = ["# One Cedric 我的模型", "# 每个档案 = 一个可一键切换的模型连接。", ""]
    active = str(data.get("active") or "")
    if active:
        lines.append(f'active = "{_esc(active)}"')
    else:
        lines.append('active = ""')
    lines.append("")
    profiles = data.get("profiles") or {}
    for name in profiles:
        p = profiles[name]
        lines.append(f'[profiles."{_esc(name)}"]')
        for k in ("model", "host", "api_key", "note"):
            if k in p and p[k]:
                lines.append(f'{k} = "{_esc(p[k])}"')
        if p.get("created_at"):
            lines.append(f"created_at = {p['created_at']}")
        for k in PARAM_FIELDS:
            if k in p and p[k] not in (None, ""):
                lines.append(f"{k} = {_fmt_value(p[k])}")
        lines.append("")
    try:
        MY_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        MY_MODELS_PATH.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def list_profiles() -> list[dict]:
    data = load()
    return [data["profiles"][n] for n in data["profiles"]]


def get_profile(name: str) -> dict | None:
    return load()["profiles"].get(name)


def active_profile() -> dict | None:
    data = load()
    if data["active"]:
        return data["profiles"].get(data["active"])
    return None


def upsert_profile(name: str, fields: dict) -> bool:
    data = load()
    profiles = data["profiles"]
    old = profiles.get(name, {})
    merged = dict(old)
    for k, v in fields.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    merged["name"] = name
    if "created_at" not in merged:
        merged["created_at"] = time.time()
    profiles[name] = merged
    if not data["active"]:
        data["active"] = name
    return save(data)


def remove_profile(name: str) -> bool:
    data = load()
    profiles = data["profiles"]
    if name not in profiles:
        return False
    del profiles[name]
    if data["active"] == name:
        data["active"] = next(iter(profiles), "")
    return save(data)


def set_active(name: str) -> bool:
    data = load()
    if name not in data["profiles"]:
        return False
    data["active"] = name
    return save(data)


def apply_to_copilot(copilot, profile: dict) -> None:
    """把档案应用到一个 OneCedric 实例（连接 + 参数覆盖）。"""
    if profile.get("model"):
        copilot.model = str(profile["model"])
    if profile.get("host"):
        copilot.host = str(profile["host"]).rstrip("/")
    if "api_key" in profile and profile["api_key"] is not None:
        copilot.api_key = str(profile["api_key"])
    if profile.get("temperature") is not None:
        try:
            copilot.temperature = float(profile["temperature"])
        except (TypeError, ValueError):
            pass
    if profile.get("think_level"):
        copilot.think_level = str(profile["think_level"])

    # 参数覆盖写入 model_overrides.toml，请求时自动生效
    params = {k: profile[k] for k in PARAM_FIELDS
              if k in profile and profile[k] not in (None, "")}
    if params and copilot.model:
        try:
            from .ui.screens.models import (
                _load_overrides,
                _save_overrides,
            )
            overrides = _load_overrides()
            merged = dict(overrides.get(copilot.model, {}))
            merged.update(params)
            overrides[copilot.model] = merged
            _save_overrides(overrides)
        except Exception:
            pass

    # 连接信息持久化到全局配置
    try:
        copilot.config.setdefault("default", {}).update({
            "model": copilot.model, "host": copilot.host,
            "api_key": copilot.api_key or "",
            "temperature": copilot.temperature,
        })
        copilot._save_config("global")
    except Exception:
        pass


def switch_profile(copilot, name: str) -> tuple[bool, str]:
    """切换并应用档案。返回 (ok, message)。"""
    profile = get_profile(name)
    if profile is None:
        return False, f"档案不存在: {name}"
    apply_to_copilot(copilot, profile)
    set_active(name)
    return True, f"已切换到「{name}」· {profile.get('model')}"
