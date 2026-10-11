"""Windows 控制台清屏与 VT 启用。

背景
----
rich 的 Console.clear() 依赖 ANSI 转义（\\x1b[2J）。在 Windows 传统
控制台（conhost / PowerShell 5.1，未开启 VT 处理）下：
- 老版本 rich 会直接跳过 clear；
- rich 13.7+ 的 legacy 渲染器不处理 ControlType.CLEAR，清屏被静默丢弃。
结果就是各界面“再打印一遍”、内容层层叠加。

修复
----
1. enable_vt_terminal()：启动时用 SetConsoleMode 开启 VT（颜色/清屏走
   ANSI，体验最佳）；对不支持的环境静默失败，不影响启动。
2. ClearConsole(Console)：清屏时在 Windows 上直接调用控制台 API
   （FillConsoleOutputCharacter + SetConsoleCursorPosition，即 cls 的
   底层实现），完全不依赖 VT/ANSI，conhost 与 Windows Terminal 都有效；
   失败时回退到 rich 原生 clear。

兼容性说明
----------
部分 Python 构建（如 3.14.x）下 ctypes 的 c_void_p restype 转换异常：
声明返回 HANDLE 的函数会直接返回 int（而非 c_void_p 实例），导致
``handle.value`` 抛 AttributeError、整个 win32 路径被 except 吞掉后
静默失效。这里统一用 ``_as_handle()`` 把 int / c_void_p 都规整成
c_void_p 实例，确保返回值判断与参数传递在任何构建下都成立。
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

try:
    from rich.console import Console
except Exception:  # pragma: no cover
    Console = None

_ENABLED = False

# WinAPI 常量
_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def _as_handle(h):
    """把 GetStdHandle 的返回值规整为 c_void_p 实例（兼容 int 返回构建）。"""
    if h is None:
        return None
    if isinstance(h, int):
        return ctypes.c_void_p(h)
    return h


def _get_kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _get_std_handle(kernel32, handle_id):
    GetStdHandle = kernel32.GetStdHandle
    GetStdHandle.restype = wintypes.HANDLE
    GetStdHandle.argtypes = [wintypes.DWORD]
    return _as_handle(GetStdHandle(handle_id))


def enable_vt_terminal() -> bool:
    """为 stdout/stderr 启用 VT 处理。非 Windows 或已启用则直接返回。"""
    global _ENABLED
    if _ENABLED:
        return True
    if os.name != "nt":
        _ENABLED = True
        return True

    try:
        kernel32 = _get_kernel32()
        GetConsoleMode = kernel32.GetConsoleMode
        GetConsoleMode.restype = wintypes.BOOL
        GetConsoleMode.argtypes = [wintypes.HANDLE,
                                   ctypes.POINTER(wintypes.DWORD)]
        SetConsoleMode = kernel32.SetConsoleMode
        SetConsoleMode.restype = wintypes.BOOL
        SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]

        for handle_id in (_STD_OUTPUT_HANDLE, _STD_ERROR_HANDLE):
            handle = _get_std_handle(kernel32, handle_id)
            if handle is None or handle.value == -1:
                continue
            mode = wintypes.DWORD(0)
            if not GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
                continue
            SetConsoleMode(
                handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        # 启用失败不影响启动：颜色走 rich legacy 渲染，清屏走 ClearConsole
        pass

    _ENABLED = True
    return True


class _COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class _SMALL_RECT(ctypes.Structure):
    _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]


class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [("dwSize", _COORD), ("dwCursorPosition", _COORD),
                ("wAttributes", wintypes.WORD), ("srWindow", _SMALL_RECT),
                ("dwMaximumWindowSize", _COORD)]


def _clear_win32() -> bool:
    """用控制台 API 清屏（cls 的底层实现），成功返回 True。"""
    try:
        kernel32 = _get_kernel32()
        handle = _get_std_handle(kernel32, _STD_OUTPUT_HANDLE)
        if handle is None or handle.value == -1:
            return False

        GetConsoleScreenBufferInfo = kernel32.GetConsoleScreenBufferInfo
        GetConsoleScreenBufferInfo.restype = wintypes.BOOL
        GetConsoleScreenBufferInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_CONSOLE_SCREEN_BUFFER_INFO)]
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        if not GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi)):
            return False

        # 从 (0,0) 开始填充整个可见窗口的空白字符与属性
        width = max(csbi.dwSize.X, 1)
        height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
        count = int(width * max(height, 1))
        origin = _COORD(0, 0)
        written = wintypes.DWORD(0)

        FillConsoleOutputCharacterW = kernel32.FillConsoleOutputCharacterW
        FillConsoleOutputCharacterW.restype = wintypes.BOOL
        FillConsoleOutputCharacterW.argtypes = [
            wintypes.HANDLE, ctypes.c_wchar, wintypes.DWORD,
            _COORD, ctypes.POINTER(wintypes.DWORD)]
        FillConsoleOutputAttribute = kernel32.FillConsoleOutputAttribute
        FillConsoleOutputAttribute.restype = wintypes.BOOL
        FillConsoleOutputAttribute.argtypes = [
            wintypes.HANDLE, wintypes.WORD, wintypes.DWORD,
            _COORD, ctypes.POINTER(wintypes.DWORD)]

        FillConsoleOutputCharacterW(handle, " ", count, origin,
                                    ctypes.byref(written))
        FillConsoleOutputAttribute(handle, csbi.wAttributes, count,
                                   origin, ctypes.byref(written))

        SetConsoleCursorPosition = kernel32.SetConsoleCursorPosition
        SetConsoleCursorPosition.restype = wintypes.BOOL
        SetConsoleCursorPosition.argtypes = [wintypes.HANDLE, _COORD]
        SetConsoleCursorPosition(handle, origin)
        return True
    except Exception:
        return False


if Console is not None:

    class ClearConsole(Console):
        """清屏对 Windows 控制台 API 优先，其余回退 rich。"""

        def clear(self, home: bool = True) -> None:
            if os.name == "nt" and _clear_win32():
                return
            try:
                super().clear(home=home)
            except Exception:
                pass


__all__ = ["enable_vt_terminal", "clear_screen", "ClearConsole",
           "Console"]


def clear_screen(console) -> None:
    """任意环境可用的清屏入口。"""
    if hasattr(console, "clear"):
        try:
            console.clear()
        except Exception:
            pass
