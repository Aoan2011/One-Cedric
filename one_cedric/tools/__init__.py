"""tools 主入口（薄转发）。

职责：
  · re-export schema 常量
  · 转出 dispatch_tool 供 core 使用
  · 转出常用 helper（sandbox / normalize）

工具实现分散在各子模块，由 _dispatch.py 聚合。
"""
from __future__ import annotations

from .schema import (
    TOOLS, TOOLS_READONLY,
    READONLY_TOOL_NAMES, CACHEABLE_TOOLS, WRITE_TOOLS,
)
from .sandbox import (
    _resolve_path, _as_int,
    set_access_mode, get_access_mode,
)
from .normalize import prepare_tool_call
from ._dispatch import dispatch_tool, is_core_handled
from ..computer.tools import mouse_action, keyboard_action, window_action


__all__ = [
    "TOOLS", "TOOLS_READONLY",
    "READONLY_TOOL_NAMES", "CACHEABLE_TOOLS", "WRITE_TOOLS",
    "dispatch_tool", "is_core_handled",
    "prepare_tool_call",
    "_resolve_path", "_as_int",
    "set_access_mode", "get_access_mode",
    "mouse_action", "keyboard_action", "window_action",
]