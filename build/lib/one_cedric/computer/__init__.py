"""Computer use：截屏、鼠标、键盘、窗口控制。"""
from .backend import ComputerBackend, BackendError, get_backend, reset_backend
from .safety import SafetyPolicy, check_action
from .tools import (
    screen_capture, screen_info,
    mouse_action, keyboard_action, window_action,
    set_policy, get_policy,
)

__all__ = [
    "ComputerBackend", "BackendError", "get_backend", "reset_backend",
    "SafetyPolicy", "check_action",
    "screen_capture", "screen_info",
    "mouse_action", "keyboard_action", "window_action",
    "set_policy", "get_policy",
]
