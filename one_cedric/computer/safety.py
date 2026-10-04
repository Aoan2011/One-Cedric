"""Computer use 安全策略。"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


MAX_ACTIONS_PER_MINUTE = 60
MAX_TYPE_CHARS = 500
MAX_DRAG_PIXELS = 1500
MAX_CLICKS = 3
MAX_SCROLL = 20


@dataclass
class SafetyCheck:
    ok: bool
    reason: str = ""
    needs_extra_confirm: bool = False
    extra_prompt: str = ""


class SafetyPolicy:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._recent: deque[float] = deque()

    def _rate_limit(self) -> tuple[bool, str]:
        now = time.time()
        cutoff = now - 60
        while self._recent and self._recent[0] < cutoff:
            self._recent.popleft()
        if len(self._recent) >= MAX_ACTIONS_PER_MINUTE:
            return False, (
                f"过去 60 秒内已执行 {len(self._recent)} 个 GUI 动作"
                f"（上限 {MAX_ACTIONS_PER_MINUTE}）。"
                f"请等一会儿再继续，或停止操作。"
            )
        return True, ""

    def _record(self) -> None:
        self._recent.append(time.time())

    def check(self, tool: str, args: dict) -> SafetyCheck:
        if not self.enabled:
            return SafetyCheck(
                ok=False,
                reason=("Computer use 未启用。请用 --enable-computer-use 启动，"
                        "或在会话里 /computer on 开启。"),
            )

        ok, why = self._rate_limit()
        if not ok:
            return SafetyCheck(ok=False, reason=why)

        if tool == "mouse_action":
            action = str(args.get("action", "")).lower()
            if action == "drag":
                x1 = int(args.get("x1", 0) or 0)
                y1 = int(args.get("y1", 0) or 0)
                x2 = int(args.get("x2", 0) or 0)
                y2 = int(args.get("y2", 0) or 0)
                dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                if dist > MAX_DRAG_PIXELS:
                    return SafetyCheck(
                        ok=True,
                        needs_extra_confirm=True,
                        extra_prompt=(f"拖拽距离 {int(dist)} 像素 "
                                      f"（> {MAX_DRAG_PIXELS}）。确认执行？"),
                    )
            if action in ("click", "double_click", "right_click"):
                clicks = int(args.get("clicks", 2 if action == "double_click" else 1) or 1)
                if clicks > MAX_CLICKS:
                    return SafetyCheck(
                        ok=True, needs_extra_confirm=True,
                        extra_prompt=f"连续点击 {clicks} 次（> {MAX_CLICKS}）。确认？",
                    )
            if action == "scroll":
                amt = abs(int(args.get("amount", 0) or 0))
                if amt > MAX_SCROLL:
                    return SafetyCheck(
                        ok=True, needs_extra_confirm=True,
                        extra_prompt=f"滚轮 {amt} 格（> {MAX_SCROLL}）。确认？",
                    )

        if tool == "keyboard_action":
            action = str(args.get("action", "")).lower()
            if action == "type":
                text = str(args.get("text", "") or "")
                if len(text) > MAX_TYPE_CHARS:
                    return SafetyCheck(
                        ok=True, needs_extra_confirm=True,
                        extra_prompt=(f"输入 {len(text)} 字符"
                                      f"（> {MAX_TYPE_CHARS}）。确认？"),
                    )
            if action == "hotkey":
                keys = args.get("keys") or []
                if not isinstance(keys, list):
                    return SafetyCheck(ok=False, reason="keys 必须是数组。")
                forbidden = {
                    ("ctrl", "alt", "delete"),
                    ("ctrl", "shift", "escape"),
                    ("alt", "f4"),
                    ("win", "l"),
                    ("cmd", "q"),
                }
                combo = tuple(sorted(str(k).lower() for k in keys))
                if combo in forbidden:
                    return SafetyCheck(
                        ok=False,
                        reason=f"快捷键 {keys} 被禁用（涉及系统级操作）。",
                    )

        return SafetyCheck(ok=True)

    def record(self) -> None:
        self._record()


def check_action(policy: SafetyPolicy, tool: str, args: dict) -> SafetyCheck:
    return policy.check(tool, args)