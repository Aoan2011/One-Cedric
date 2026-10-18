"""CLI 统一 Console：``ClearConsole`` + Nerd Font 状态字形。

为什么需要它
============

core / cli / ui.screens 里有几百处 ``console.print("[ok]✓ …")`` 这样的
状态行。与其逐处改写，不如在 Console 这一层做一次替换：打印字符串时把
``]✓`` / ``]✗`` / ``]⚠`` / ``]⊘`` / ``]◆`` 这类字形换成 Nerd Font 码点
（见 ``icons.process_markup``）。只匹配紧跟 Rich 标记的字形，正文里的
同样字符不受影响；``ONE_CEDRIC_NERD_FONT=0`` 或 ``[ui].nerd_font=false``
时整个替换是恒等操作，视觉与旧版完全一致。

TUI 的 kernel 命令捕获输出也用这个类，弹层里的 ``✓`` / ``✗`` 因此同样
会被换掉。
"""
from __future__ import annotations

from ..winvt import ClearConsole
from . import icons


class CedricConsole(ClearConsole):
    """打印前把状态字形换成 Nerd Font 字形的 Rich Console。"""

    def print(self, *objects, **kwargs):
        if icons.enabled():
            objects = tuple(
                icons.process_markup(obj) if isinstance(obj, str) else obj
                for obj in objects
            )
        return super().print(*objects, **kwargs)


__all__ = ["CedricConsole"]
