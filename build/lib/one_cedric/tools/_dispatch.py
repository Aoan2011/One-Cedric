"""dispatch_tool：合并所有 handler 注册表并按工具名分发。

设计：
  · 每个 _handlers_xxx 模块导出一个 `HANDLERS` dict：
      {"tool_name": callable(root: Path, args: dict) -> str}
  · 本模块把所有 dict 合并后查表
  · 未注册的工具 → 若属于 WRITE_TOOLS，返回"需要 core 层确认"
  · 完全未知 → 报错
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from .schema import WRITE_TOOLS


_HANDLERS: dict[str, Callable[[Path, dict], str]] = {}


def _merge(module_name: str) -> None:
    try:
        mod = importlib.import_module(
            f".{module_name}", package=__package__)
    except ImportError as exc:
        # 未实现不致命：只影响该模块的工具
        print(f"[tools] 跳过 {module_name}（{exc}）")
        return
    h = getattr(mod, "HANDLERS", None)
    if not isinstance(h, dict):
        return
    for k, v in h.items():
        if k in _HANDLERS:
            # 后注册的覆盖前面的（一般不会发生）
            pass
        _HANDLERS[k] = v


_merge("_handlers_readonly")
_merge("_handlers_text")
_merge("_handlers_media")
_merge("_handlers_agent")
_merge("_handlers_extra")


def is_core_handled(name: str) -> bool:
    """工具是否由 core 层处理（写操作 / 需要确认 / 需要 state）。"""
    if name in WRITE_TOOLS:
        return True
    # 少部分"只读但需要 core state"的工具
    if name in ("spawn_agent", "multi_review", "ask_user",
                "dream_run", "cost_export"):
        return True
    return False


def dispatch_tool(name: str, args: dict, root: Path) -> str:
    """执行工具。写操作不经过这里（core 层先确认）。

    返回工具的执行结果字符串。
    """
    if not isinstance(args, dict):
        args = {}

    from ..integrations import is_external_tool, call_external_tool
    if is_external_tool(name):
        return call_external_tool(name, args)

    fn = _HANDLERS.get(name)
    if fn is not None:
        try:
            return fn(root, args)
        except TypeError as exc:
            return (f"ERROR: 工具 '{name}' 参数不匹配: {exc}")
        except Exception as exc:
            return (f"ERROR: 工具 '{name}' 执行失败: "
                    f"{type(exc).__name__}: {exc}")

    if is_core_handled(name):
        return (f"ERROR: 工具 '{name}' 是写操作或需要 core state，"
                f"不应直接走 dispatch_tool。")

    return f"ERROR: 未知工具 '{name}'（未在 dispatch 表里注册）。"