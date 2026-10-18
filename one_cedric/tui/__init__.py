"""Shell C：Codex 风格 TUI（Textual）。

    python -m one_cedric.tui          # 真后端
    python -m one_cedric.tui --demo   # 假后端，用来看界面

与 WebUI/CLI 共用同一个内核（``one_cedric.core``），只是换了一层外壳；
四个界面并存，互不干扰。
"""
from __future__ import annotations

__all__ = ["main", "CedricTUI"]


def main(demo: bool = False) -> int:
    from .app import main as _main
    return _main(demo=demo)


def __getattr__(name: str):                # 让 `from ... import CedricTUI` 也懒加载
    if name == "CedricTUI":
        from .app import CedricTUI
        return CedricTUI
    raise AttributeError(name)
