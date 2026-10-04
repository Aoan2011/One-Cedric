"""会话 + 全局/项目配置 + 工作画像 + 工具配置 + UI 配置。"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None

from .config import (
    SESSION_DIRNAME, SESSION_SUBDIR, PROJECTS_SUBDIR, PROFILES_SUBDIR,
    CONFIG_FILENAME, DEFAULT_CONFIG,
)


def _session_dir() -> Path:
    d = Path.home() / SESSION_DIRNAME / SESSION_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _session_path(sid: str) -> Path:
    return _session_dir() / f"{sid}.json"


def save_session_file(sid: str, created_at: float, root: Path, model: str,
                      messages: list, undo_stack: list, snapshots: list,
                      compactions: list, stats: dict,
                      title: str = "", title_source: str = "",
                      audit_log: list | None = None,
                      todos: list | None = None,
                      asks: list | None = None) -> bool:
    try:
        data = {
            "id": sid, "created_at": created_at, "updated_at": time.time(),
            "root": str(root), "model": model,
            "title": title, "title_source": title_source,
            "messages": messages,
            "undo_stack": [
                {"rel": r["rel"], "old_text": r["old_text"],
                 "new_text": r["new_text"], "existed": r["existed"],
                 "tool": r["tool"], "ts": r["ts"],
                 "tag": r.get("tag", "")}
                for r in undo_stack
            ],
            "snapshots": snapshots, "compactions": compactions,
            "stats": stats, "audit_log": audit_log or [],
            "todos": todos or [], "asks": asks or [],
        }
        p = _session_path(sid)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


def load_session_file(sid: str) -> dict | None:
    p = _session_path(sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_session_files(root: Path | None = None) -> list[dict]:
    out = []
    try:
        d = _session_dir()
    except OSError:
        return out
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if root is not None and data.get("root") != str(root):
            continue
        out.append(data)
    return out


def delete_session_file(sid: str) -> None:
    try:
        _session_path(sid).unlink(missing_ok=True)
    except OSError:
        pass


def find_session_by_id_or_title(token: str) -> dict | None:
    data = load_session_file(token)
    if data:
        return data
    for s in list_session_files():
        if s.get("title") == token:
            return s
    return None


def default_config_path() -> Path:
    return Path.home() / SESSION_DIRNAME / CONFIG_FILENAME


def project_config_path(root: Path) -> Path:
    key = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path.home() / SESSION_DIRNAME / PROJECTS_SUBDIR / f"{key}.toml"


def _fresh_config() -> dict:
    return {
        "default": dict(DEFAULT_CONFIG["default"]),
        "bash": {"extra_prefixes": [], "extra_blacklist": []},
        "gateway": dict(DEFAULT_CONFIG["gateway"]),
        "amap": {"api_key": ""},
        "ui": {
            "theme": "dark",
            "acrylic": "medium",
            "think_level": "medium",
            "particle_hue1": 220,
            "particle_hue2": 270,
        },
    }


def _read_config_file(path: Path) -> dict:
    if not path or not path.exists() or tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"[warn] 配置解析失败 {path}: {exc}", file=sys.stderr)
        return {}


def _apply_config(cfg: dict, raw: dict) -> None:
    d = raw.get("default") or {}

    for k in ("model", "host", "api_key", "think_level", "language", "mode"):
        v = d.get(k)
        if isinstance(v, str):
            if k == "api_key":
                cfg["default"][k] = v
            elif k == "language":
                if v in ("zh", "en"):
                    cfg["default"][k] = v
            elif k == "mode":
                from .config import ACCESS_MODES, ACCESS_MODE_ALIASES
                m = ACCESS_MODE_ALIASES.get(v.lower(), v.lower())
                if m in ACCESS_MODES:
                    cfg["default"][k] = m
            elif v.strip():
                cfg["default"][k] = v.strip()

    for k, caster in (("temperature", float), ("max_steps", int),
                      ("compact_keep_turns", int),
                      ("auto_compact_threshold", int)):
        v = d.get(k)
        if isinstance(v, (int, float)):
            try:
                cfg["default"][k] = caster(v)
            except (TypeError, ValueError):
                pass

    for k in ("auto_yes", "show_reasoning",
              "enable_computer_use", "enable_vision",
              "allow_arbitrary_shell"):
        if isinstance(d.get(k), bool):
            cfg["default"][k] = d[k]

    b = raw.get("bash") or {}
    for key in ("extra_prefixes", "extra_blacklist"):
        extra = b.get(key)
        if isinstance(extra, list):
            existing = cfg["bash"].setdefault(key, [])
            for x in extra:
                s = str(x).strip()
                if s and s not in existing:
                    existing.append(s)

    g = raw.get("gateway") or {}
    if isinstance(g.get("enabled"), bool):
        cfg["gateway"]["enabled"] = g["enabled"]
    if isinstance(g.get("host"), str) and g["host"].strip():
        cfg["gateway"]["host"] = g["host"].strip()
    if isinstance(g.get("port"), int):
        cfg["gateway"]["port"] = g["port"]
    if isinstance(g.get("token"), str):
        cfg["gateway"]["token"] = g["token"]

    am = raw.get("amap") or {}
    if isinstance(am.get("api_key"), str):
        cfg.setdefault("amap", {})["api_key"] = am["api_key"]

    ui = raw.get("ui") or {}
    if ui:
        d_ui = cfg.setdefault("ui", {})
        for k in ("theme", "acrylic", "think_level"):
            v = ui.get(k)
            if isinstance(v, str) and v.strip():
                d_ui[k] = v.strip()
        for k in ("particle_hue1", "particle_hue2"):
            v = ui.get(k)
            if isinstance(v, int) and 0 <= v <= 360:
                d_ui[k] = v


def compose_config(global_path: Path, project_path: Path | None = None) -> dict:
    cfg = _fresh_config()
    _apply_config(cfg, _read_config_file(global_path))
    if project_path:
        _apply_config(cfg, _read_config_file(project_path))
    return cfg


def _toml_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump_config_toml(cfg: dict, root: Path | None = None) -> str:
    lines = ["# One Cedric 配置文件", "# 由程序生成，可手工编辑"]
    if root:
        lines.append(f"# 作用范围: 项目 {root}")
    else:
        lines.append("# 作用范围: 全局")
    lines.append("")

    if root:
        lines.append("[meta]")
        lines.append(f"root = {_toml_quote(str(root))}")
        lines.append("")

    lines.append("[default]")
    d = cfg.get("default", {})
    for k in ("model", "host"):
        if k in d:
            lines.append(f"{k} = {_toml_quote(str(d[k]))}")
    if "api_key" in d:
        lines.append(f"api_key = {_toml_quote(str(d['api_key']))}")
    if "think_level" in d:
        lines.append(f"think_level = {_toml_quote(str(d['think_level']))}")
    if "language" in d:
        lines.append(f"language = {_toml_quote(str(d['language']))}")
    if "mode" in d:
        lines.append(f"mode = {_toml_quote(str(d['mode']))}")
    for k in ("temperature", "max_steps",
              "compact_keep_turns", "auto_compact_threshold"):
        if k in d:
            lines.append(f"{k} = {d[k]}")
    for k in ("auto_yes", "show_reasoning", "enable_computer_use",
              "enable_vision", "allow_arbitrary_shell"):
        if k in d:
            lines.append(f"{k} = {'true' if d[k] else 'false'}")
    lines.append("")

    lines.append("[bash]")
    b = cfg.get("bash", {})
    extra = b.get("extra_prefixes", [])
    if extra:
        items = ", ".join(_toml_quote(str(x)) for x in extra)
        lines.append(f"extra_prefixes = [{items}]")
    else:
        lines.append("extra_prefixes = []")
    black = b.get("extra_blacklist", [])
    if black:
        items = ", ".join(_toml_quote(str(x)) for x in black)
        lines.append(f"extra_blacklist = [{items}]")
    else:
        lines.append("extra_blacklist = []")
    lines.append("")

    lines.append("[gateway]")
    g = cfg.get("gateway", {})
    lines.append(f"enabled = {'true' if g.get('enabled') else 'false'}")
    lines.append(f"host = {_toml_quote(str(g.get('host', '127.0.0.1')))}")
    lines.append(f"port = {int(g.get('port', 2043))}")
    lines.append(f"token = {_toml_quote(str(g.get('token', '')))}")
    lines.append("")

    lines.append("[amap]")
    am = cfg.get("amap", {})
    lines.append(f"api_key = {_toml_quote(str(am.get('api_key', '')))}")
    lines.append("")

    lines.append("[ui]")
    ui = cfg.get("ui", {})
    lines.append(f"theme = {_toml_quote(str(ui.get('theme', 'dark')))}")
    lines.append(f"acrylic = {_toml_quote(str(ui.get('acrylic', 'medium')))}")
    lines.append(f"think_level = {_toml_quote(str(ui.get('think_level', 'medium')))}")
    lines.append(f"particle_hue1 = {int(ui.get('particle_hue1', 220))}")
    lines.append(f"particle_hue2 = {int(ui.get('particle_hue2', 270))}")
    lines.append("")

    return "\n".join(lines)


def save_config_file(path: Path, cfg: dict, root: Path | None = None) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(dump_config_toml(cfg, root=root), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def profiles_dir() -> Path:
    d = Path.home() / SESSION_DIRNAME / PROFILES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_path(name: str) -> Path:
    return profiles_dir() / f"{name}.toml"


def list_profiles() -> list[dict]:
    out = []
    try:
        d = profiles_dir()
    except OSError:
        return out
    for f in sorted(d.glob("*.toml")):
        try:
            raw = tomllib.loads(f.read_text(encoding="utf-8")) if tomllib else {}
        except Exception:
            continue
        meta = raw.get("meta") or {}
        d_ = raw.get("default") or {}
        b_ = raw.get("bash") or {}
        out.append({
            "name": f.stem,
            "created_at": meta.get("created_at", 0),
            "updated_at": meta.get("updated_at", 0),
            "model": d_.get("model", ""),
            "auto_yes": bool(d_.get("auto_yes", False)),
            "preset_tag": meta.get("preset_tag", ""),
            "snapshot_granularity": d_.get("snapshot_granularity", "turn"),
            "extra_prefixes": list(b_.get("extra_prefixes", [])),
            "raw": raw,
        })
    return out


def load_profile(name: str) -> dict | None:
    p = profile_path(name)
    if not p.exists() or tomllib is None:
        return None
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_profile(name: str, cfg: dict,
                 preset_tag: str = "",
                 created_at: float | None = None) -> bool:
    if not PROFILE_NAME_RE.match(name):
        return False
    p = profile_path(name)
    if created_at is None:
        if p.exists():
            try:
                old = tomllib.loads(p.read_text(encoding="utf-8"))
                created_at = float((old.get("meta") or {}).get("created_at",
                                                                  time.time()))
            except Exception:
                created_at = time.time()
        else:
            created_at = time.time()
    lines = ["# One Cedric 工作画像", f"# 名称: {name}", "", "[meta]",
             f"created_at = {float(created_at)}",
             f"updated_at = {float(time.time())}",
             f"preset_tag = {_toml_quote(preset_tag)}", "", "[default]"]
    d = cfg.get("default", {})
    for k in ("model", "host"):
        if k in d:
            lines.append(f"{k} = {_toml_quote(str(d[k]))}")
    for k in ("temperature", "max_steps"):
        if k in d:
            lines.append(f"{k} = {d[k]}")
    if "auto_yes" in d:
        lines.append(f"auto_yes = {'true' if d['auto_yes'] else 'false'}")
    if "snapshot_granularity" in d:
        lines.append(
            f"snapshot_granularity = "
            f"{_toml_quote(str(d['snapshot_granularity']))}")
    lines.append("")
    lines.append("[bash]")
    extra = cfg.get("bash", {}).get("extra_prefixes", [])
    if extra:
        items = ", ".join(_toml_quote(str(x)) for x in extra)
        lines.append(f"extra_prefixes = [{items}]")
    else:
        lines.append("extra_prefixes = []")
    lines.append("")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


def delete_profile(name: str) -> bool:
    try:
        profile_path(name).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def apply_profile(cfg: dict, raw: dict) -> None:
    _apply_config(cfg, raw)
    d = raw.get("default") or {}
    if isinstance(d.get("snapshot_granularity"), str):
        g = d["snapshot_granularity"]
        if g in ("turn", "write"):
            cfg["default"]["snapshot_granularity"] = g


def profile_preset_tag(raw: dict) -> str:
    return str((raw.get("meta") or {}).get("preset_tag", ""))


TOOLS_CONFIG_FILENAME = "tools.toml"


def tools_config_path() -> Path:
    return Path.home() / SESSION_DIRNAME / TOOLS_CONFIG_FILENAME


def load_tools_config() -> dict:
    p = tools_config_path()
    result = {"disabled": set()}
    if not p.exists() or tomllib is None:
        return result
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return result
    dis = raw.get("disabled")
    if isinstance(dis, list):
        for x in dis:
            s = str(x).strip()
            if s:
                result["disabled"].add(s)
    return result


def save_tools_config(disabled: set) -> bool:
    p = tools_config_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# One Cedric 工具配置",
            "# disabled 里的工具不会暴露给模型",
            "",
            "disabled = [",
        ]
        for name in sorted(disabled):
            lines.append(f'    "{name}",')
        lines.append("]")
        lines.append("")
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False