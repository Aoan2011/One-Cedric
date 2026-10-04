"""LSP 配置加载与默认值。"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None

from ..config import SESSION_DIRNAME

LSP_CONFIG_FILENAME = "lsp.toml"


def default_lsp_config_path() -> Path:
    return Path.home() / SESSION_DIRNAME / LSP_CONFIG_FILENAME


def default_lsp_config() -> dict:
    return {
        "servers": {
            "python": {
                "command": "pylsp",
                "args": [],
                "extensions": [".py", ".pyi"],
                "root_markers": ["pyproject.toml", "setup.py", "setup.cfg", ".git"],
                "enabled": True,
                "init_timeout": 30,
                "request_timeout": 15,
            },
            "typescript": {
                "command": "typescript-language-server",
                "args": ["--stdio"],
                "extensions": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
                "root_markers": ["package.json", "tsconfig.json", ".git"],
                "enabled": True,
                "init_timeout": 30,
                "request_timeout": 15,
            },
            "go": {
                "command": "gopls",
                "args": [],
                "extensions": [".go"],
                "root_markers": ["go.mod", ".git"],
                "enabled": True,
                "init_timeout": 30,
                "request_timeout": 15,
            },
            "rust": {
                "command": "rust-analyzer",
                "args": [],
                "extensions": [".rs"],
                "root_markers": ["Cargo.toml", ".git"],
                "enabled": True,
                "init_timeout": 60,
                "request_timeout": 20,
            },
        },
        "settings": {
            "enabled": True,
            "diagnostics_wait": 2.0,
        },
    }


def load_lsp_config(path: Path | None = None) -> dict:
    cfg = default_lsp_config()
    p = path or default_lsp_config_path()
    if not p.exists() or tomllib is None:
        return cfg
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return cfg

    servers = raw.get("servers") or {}
    for name, srv in servers.items():
        base = cfg["servers"].get(name, {})
        merged = {
            "command": srv.get("command", base.get("command", "")),
            "args": list(srv.get("args", base.get("args", []))),
            "extensions": list(srv.get("extensions", base.get("extensions", []))),
            "root_markers": list(srv.get("root_markers", base.get("root_markers", []))),
            "enabled": bool(srv.get("enabled", base.get("enabled", True))),
            "init_timeout": int(srv.get("init_timeout", base.get("init_timeout", 30))),
            "request_timeout": int(srv.get("request_timeout", base.get("request_timeout", 15))),
        }
        cfg["servers"][name] = merged

    settings = raw.get("settings") or {}
    if "enabled" in settings:
        cfg["settings"]["enabled"] = bool(settings["enabled"])
    if "diagnostics_wait" in settings:
        try:
            cfg["settings"]["diagnostics_wait"] = float(settings["diagnostics_wait"])
        except (TypeError, ValueError):
            pass

    return cfg


def dump_lsp_config(cfg: dict) -> str:
    lines = [
        "# One Cedric LSP 配置",
        "#",
        "# 每个 [servers.<name>] 段定义一个语言服务器。",
        "# 安装方式（示例）：",
        "#   Python:  pip install python-lsp-server",
        "#   TS/JS:   npm i -g typescript typescript-language-server",
        "#   Go:      go install golang.org/x/tools/gopls@latest",
        "#   Rust:    rustup component add rust-analyzer",
        "",
        "[settings]",
        f"enabled = {'true' if cfg['settings'].get('enabled', True) else 'false'}",
        f"diagnostics_wait = {cfg['settings'].get('diagnostics_wait', 2.0)}",
        "",
    ]

    for name, srv in cfg["servers"].items():
        lines.append(f"[servers.{name}]")
        lines.append(f"command = {_q(srv.get('command', ''))}")
        args = srv.get("args", [])
        lines.append(f"args = [{', '.join(_q(a) for a in args)}]")
        exts = srv.get("extensions", [])
        lines.append(f"extensions = [{', '.join(_q(e) for e in exts)}]")
        markers = srv.get("root_markers", [])
        lines.append(f"root_markers = [{', '.join(_q(m) for m in markers)}]")
        lines.append(f"enabled = {'true' if srv.get('enabled', True) else 'false'}")
        lines.append(f"init_timeout = {srv.get('init_timeout', 30)}")
        lines.append(f"request_timeout = {srv.get('request_timeout', 15)}")
        lines.append("")

    return "\n".join(lines)


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_lsp_config(path: Path, cfg: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_lsp_config(cfg), encoding="utf-8")
        return True
    except OSError:
        return False


def make_default_if_missing(path: Path | None = None) -> Path:
    p = path or default_lsp_config_path()
    if not p.exists():
        save_lsp_config(p, default_lsp_config())
    return p