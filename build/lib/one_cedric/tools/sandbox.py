"""路径沙箱与通用小工具。"""
from __future__ import annotations

import threading
from pathlib import Path

_MODE_LOCK = threading.Lock()
_ACCESS_MODE = "workspace"

ALLOW_OUTSIDE_MODES = {"fullaccess"}


def set_access_mode(mode: str) -> None:
    global _ACCESS_MODE
    with _MODE_LOCK:
        _ACCESS_MODE = mode or "workspace"


def get_access_mode() -> str:
    with _MODE_LOCK:
        return _ACCESS_MODE


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_path(root: Path, path: str) -> tuple:
    if not path or not isinstance(path, str):
        return None, "ERROR: 参数 path 不能为空。"

    p = Path(path).expanduser()
    if not p.is_absolute():
        p = root / p

    try:
        p = p.resolve()
    except OSError as exc:
        return None, f"ERROR: 路径解析失败: {exc}"

    if get_access_mode() in ALLOW_OUTSIDE_MODES:
        return p, ""

    try:
        p.relative_to(root)
    except ValueError:
        return None, (
            f"ERROR: 拒绝访问工作目录之外的路径: {path}"
            f"（工作目录: {root}）\n"
            f"提示：/mode fullaccess 或启动时 --mode fullaccess "
            f"可放开。"
        )

    return p, ""