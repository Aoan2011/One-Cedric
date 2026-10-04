"""5 个 computer use 工具实现。"""
from __future__ import annotations

import base64
import time
from pathlib import Path

from .backend import BackendError, get_backend
from .safety import SafetyPolicy, SafetyCheck


_POLICY: SafetyPolicy = SafetyPolicy(enabled=False)


def set_policy(policy: SafetyPolicy) -> None:
    global _POLICY
    _POLICY = policy


def get_policy() -> SafetyPolicy:
    return _POLICY


def _err(msg: str) -> str:
    return f"ERROR: {msg}"


def screen_capture(root: Path, region: list[int] | None = None,
                   save_to: str = "", return_base64: bool = False,
                   max_width: int = 1280) -> str:
    policy = _POLICY
    if not policy.enabled:
        return _err("Computer use 未启用。")

    try:
        backend = get_backend()
    except BackendError as exc:
        return _err(str(exc))

    reg = None
    if region:
        if not isinstance(region, list) or len(region) != 4:
            return _err("region 必须是 [left, top, width, height] 四个整数。")
        try:
            reg = tuple(int(x) for x in region)
        except (TypeError, ValueError):
            return _err("region 必须是整数。")

    try:
        b64, w, h = backend.capture_base64(region=reg, max_width=max_width)
    except BackendError as exc:
        return _err(str(exc))

    out_path = ""
    if save_to:
        from ..tools.sandbox import _resolve_path
        p, err = _resolve_path(root, save_to)
        if err:
            return _err(err)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_bytes(base64.b64decode(b64))
            out_path = str(p.relative_to(root))
        except OSError as exc:
            return _err(f"保存截图失败: {exc}")
    else:
        shots = Path.home() / ".one-cedric" / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        fname = f"cap-{int(time.time()*1000)}.png"
        fp = shots / fname
        try:
            fp.write_bytes(base64.b64decode(b64))
            out_path = str(fp)
        except OSError as exc:
            return _err(f"保存截图失败: {exc}")

    header = (
        f"截图成功  {w}x{h} 像素\n"
        f"文件: {out_path}\n"
        f"（后续坐标操作基于此分辨率，左上角为 0,0）"
    )
    if return_base64:
        return f"{header}\n\n__IMAGE__:{b64}"
    return header


def screen_info(root: Path) -> str:
    policy = _POLICY
    if not policy.enabled:
        return _err("Computer use 未启用。")

    try:
        backend = get_backend()
        info = backend.get_screen_info()
    except BackendError as exc:
        return _err(str(exc))

    lines = [
        "屏幕信息",
        f"  逻辑分辨率: {info.width} x {info.height}",
        f"  主显示器: {info.primary_width} x {info.primary_height}",
        f"  显示器数: {info.monitor_count}",
        f"  当前光标: ({info.cursor_x}, {info.cursor_y})",
    ]

    try:
        wins = backend.list_windows()
        active = [w for w in wins if w.get("active")]
        if active:
            lines.append(f"  活动窗口: {active[0]['title'][:80]}")
    except Exception:
        pass

    return "\n".join(lines)


def mouse_action(root: Path, action: str,
                 x: int | None = None, y: int | None = None,
                 x1: int | None = None, y1: int | None = None,
                 x2: int | None = None, y2: int | None = None,
                 button: str = "left", clicks: int = 1,
                 amount: int = 0, duration: float = 0.3) -> str:
    policy = _POLICY
    args = {
        "action": action, "x": x, "y": y,
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "button": button, "clicks": clicks,
        "amount": amount, "duration": duration,
    }
    chk: SafetyCheck = policy.check("mouse_action", args)
    if not chk.ok:
        return _err(chk.reason)

    try:
        backend = get_backend()
    except BackendError as exc:
        return _err(str(exc))

    a = (action or "").lower()
    try:
        if a == "move":
            if x is None or y is None:
                return _err("move 需要 x 和 y。")
            backend.move(int(x), int(y), duration=float(duration))
            policy.record()
            return f"鼠标移动到 ({x}, {y})"

        if a in ("click", "left_click"):
            backend.click(int(x) if x is not None else None,
                          int(y) if y is not None else None,
                          button="left", clicks=int(clicks))
            policy.record()
            return f"左键单击 x{clicks} @ ({x}, {y})"

        if a == "right_click":
            backend.click(int(x) if x is not None else None,
                          int(y) if y is not None else None,
                          button="right", clicks=1)
            policy.record()
            return f"右键单击 @ ({x}, {y})"

        if a == "double_click":
            backend.click(int(x) if x is not None else None,
                          int(y) if y is not None else None,
                          button="left", clicks=2)
            policy.record()
            return f"双击 @ ({x}, {y})"

        if a == "drag":
            for k, v in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
                if v is None:
                    return _err(f"drag 需要 {k}。")
            backend.drag(int(x1), int(y1), int(x2), int(y2),
                         button=button, duration=float(duration))
            policy.record()
            return f"从 ({x1}, {y1}) 拖到 ({x2}, {y2})"

        if a == "scroll":
            backend.scroll(int(amount),
                           int(x) if x is not None else None,
                           int(y) if y is not None else None)
            policy.record()
            return f"滚轮 {amount} 格 @ ({x}, {y})"

        return _err(f"不支持的 action: {action}")
    except BackendError as exc:
        return _err(str(exc))


def keyboard_action(root: Path, action: str,
                    text: str = "", key: str = "",
                    keys: list[str] | None = None,
                    interval: float = 0.02) -> str:
    policy = _POLICY
    args = {"action": action, "text": text, "key": key,
            "keys": keys or [], "interval": interval}
    chk: SafetyCheck = policy.check("keyboard_action", args)
    if not chk.ok:
        return _err(chk.reason)

    try:
        backend = get_backend()
    except BackendError as exc:
        return _err(str(exc))

    a = (action or "").lower()
    try:
        if a == "type":
            if not text:
                return _err("type 需要 text。")
            backend.type_text(text, interval=float(interval))
            policy.record()
            preview = text[:50] + ("…" if len(text) > 50 else "")
            return f"已输入 {len(text)} 字符: {preview!r}"

        if a == "press":
            if not key:
                return _err("press 需要 key。")
            backend.press_key(key)
            policy.record()
            return f"按键: {key}"

        if a == "hotkey":
            if not keys or not isinstance(keys, list):
                return _err("hotkey 需要 keys 数组。")
            backend.hotkey(*[str(k) for k in keys])
            policy.record()
            return f"快捷键: {'+'.join(str(k) for k in keys)}"

        return _err(f"不支持的 action: {action}")
    except BackendError as exc:
        return _err(str(exc))


def window_action(root: Path, action: str, title: str = "") -> str:
    policy = _POLICY
    if not policy.enabled:
        return _err("Computer use 未启用。")

    try:
        backend = get_backend()
    except BackendError as exc:
        return _err(str(exc))

    a = (action or "").lower()
    try:
        if a == "list":
            wins = backend.list_windows()
            if not wins:
                return "（无可见窗口）"
            lines = [f"共 {len(wins)} 个窗口："]
            for w in wins[:40]:
                flag = " *" if w.get("active") else ""
                mn = " [min]" if w.get("minimized") else ""
                lines.append(
                    f"  {w['width']}x{w['height']} @({w['x']},{w['y']}){flag}{mn}  "
                    f"{w['title'][:70]}"
                )
            if len(wins) > 40:
                lines.append(f"  …还有 {len(wins) - 40} 个")
            return "\n".join(lines)

        if a == "activate":
            if not title:
                return _err("activate 需要 title。")
            got = backend.activate_window(title)
            policy.record()
            return f"已激活窗口: {got}"

        if a == "minimize":
            if not title:
                return _err("minimize 需要 title。")
            got = backend.minimize_window(title)
            policy.record()
            return f"已最小化: {got}"

        if a == "maximize":
            if not title:
                return _err("maximize 需要 title。")
            got = backend.maximize_window(title)
            policy.record()
            return f"已最大化: {got}"

        return _err(f"不支持的 action: {action}")
    except BackendError as exc:
        return _err(str(exc))