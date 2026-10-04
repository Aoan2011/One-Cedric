"""跨平台键盘输入。

readchar 在 Windows/Linux/macOS 返回的键名不同，这里统一。
"""
from __future__ import annotations

import os
import sys

try:
    import readchar
    _HAS_READCHAR = True
except ImportError:
    _HAS_READCHAR = False

try:
    import msvcrt
except ImportError:
    msvcrt = None

KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_LEFT = "LEFT"
KEY_RIGHT = "RIGHT"
KEY_ENTER = "ENTER"
KEY_ESC = "ESC"
KEY_BACKSPACE = "BACKSPACE"
KEY_TAB = "TAB"


def _has_interactive_keys() -> bool:
    if os.name == "nt" and msvcrt is not None:
        return sys.stdin.isatty()
    return _HAS_READCHAR


def _normalize_printable_key(key: str) -> str:
    if key == "T":
        return key
    if len(key) == 1 and key.isprintable():
        return key.lower()
    return key


def _read_windows_key() -> str:
    key = msvcrt.getwch()
    if key in ("\x00", "\xe0"):
        key += msvcrt.getwch()

    special_keys = {
        "\xe0H": KEY_UP,
        "\x00H": KEY_UP,
        "\xe0P": KEY_DOWN,
        "\x00P": KEY_DOWN,
        "\xe0K": KEY_LEFT,
        "\x00K": KEY_LEFT,
        "\xe0M": KEY_RIGHT,
        "\x00M": KEY_RIGHT,
    }
    if key in special_keys:
        return special_keys[key]
    if key in ("\r", "\n"):
        return KEY_ENTER
    if key in ("\x1b", "\x03"):
        return KEY_ESC
    if key in ("\x08", "\x7f"):
        return KEY_BACKSPACE
    if key == "\t":
        return KEY_TAB
    return _normalize_printable_key(key)


def read_key() -> str:
    if os.name == "nt" and msvcrt is not None and sys.stdin.isatty():
        try:
            return _read_windows_key()
        except (EOFError, KeyboardInterrupt):
            return KEY_ESC

    if not _HAS_READCHAR:
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            return KEY_ESC
        if not line:
            return KEY_ENTER
        return line.lower()

    try:
        k = readchar.readkey()
    except (EOFError, KeyboardInterrupt):
        return KEY_ESC

    if k == readchar.key.UP:
        return KEY_UP
    if k == readchar.key.DOWN:
        return KEY_DOWN
    if k == readchar.key.LEFT:
        return KEY_LEFT
    if k == readchar.key.RIGHT:
        return KEY_RIGHT
    if k in (readchar.key.ENTER, "\r", "\n"):
        return KEY_ENTER
    if k in (readchar.key.ESC, "\x1b"):
        return KEY_ESC
    if k in (readchar.key.BACKSPACE, "\x7f", "\x08"):
        return KEY_BACKSPACE
    if k == readchar.key.TAB or k == "\t":
        return KEY_TAB

    return _normalize_printable_key(k)


def has_readchar() -> bool:
    """Whether this terminal supports single-key navigation."""
    return _has_interactive_keys()


def wait_for_return(
    console, prompt: str = "  [dim]按 Enter / Esc / q 返回…[/] "
) -> None:
    """Pause a screen without trapping keyboard users behind an Enter-only prompt."""
    if has_readchar():
        console.print(prompt, end="")
        read_key()
        return

    try:
        console.input(prompt)
    except (EOFError, KeyboardInterrupt):
        pass