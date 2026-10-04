"""pyautogui 封装。所有 GUI 操作都走这里。"""
from __future__ import annotations

import base64
import io
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_backend_lock = threading.Lock()
_backend_instance: "ComputerBackend | None" = None


class BackendError(RuntimeError):
    pass


@dataclass
class ScreenInfo:
    width: int
    height: int
    cursor_x: int
    cursor_y: int
    monitor_count: int
    primary_width: int
    primary_height: int


class ComputerBackend:
    def __init__(self):
        try:
            import pyautogui
        except ImportError as exc:
            raise BackendError(
                "需要 pyautogui。运行：pip install pyautogui Pillow"
            ) from exc

        try:
            from PIL import Image
        except ImportError as exc:
            raise BackendError("需要 Pillow。运行：pip install Pillow") from exc

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05

        self._pa = pyautogui
        self._Image = Image

    def get_screen_info(self) -> ScreenInfo:
        w, h = self._pa.size()
        cx, cy = self._pa.position()
        monitor_count = 1
        try:
            import mss
            with mss.mss() as sct:
                monitor_count = len(sct.monitors) - 1
                primary = sct.monitors[1]
                primary_w = primary["width"]
                primary_h = primary["height"]
        except Exception:
            primary_w, primary_h = w, h

        return ScreenInfo(
            width=w, height=h,
            cursor_x=cx, cursor_y=cy,
            monitor_count=max(1, monitor_count),
            primary_width=primary_w,
            primary_height=primary_h,
        )

    def capture(self, region: tuple[int, int, int, int] | None = None):
        try:
            img = self._pa.screenshot(region=region)
        except Exception as exc:
            raise BackendError(f"截屏失败: {exc}")
        return img

    def capture_png_bytes(self, region=None) -> bytes:
        img = self.capture(region)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def capture_base64(self, region=None, max_width: int = 1280) -> tuple[str, int, int]:
        img = self.capture(region)
        w, h = img.size
        if max_width and w > max_width:
            ratio = max_width / w
            img = img.resize((int(w * ratio), int(h * ratio)),
                             self._Image.LANCZOS)
            w, h = img.size
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return b64, w, h

    def move(self, x: int, y: int, duration: float = 0.2) -> None:
        try:
            self._pa.moveTo(x, y, duration=duration)
        except Exception as exc:
            raise BackendError(f"鼠标移动失败: {exc}")

    def click(self, x: int | None = None, y: int | None = None,
              button: str = "left", clicks: int = 1, interval: float = 0.1) -> None:
        try:
            if x is not None and y is not None:
                self._pa.click(x, y, clicks=clicks,
                               interval=interval, button=button)
            else:
                self._pa.click(clicks=clicks, interval=interval, button=button)
        except Exception as exc:
            raise BackendError(f"点击失败: {exc}")

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             button: str = "left", duration: float = 0.5) -> None:
        try:
            self._pa.moveTo(x1, y1, duration=0.1)
            self._pa.mouseDown(button=button)
            time.sleep(0.05)
            self._pa.moveTo(x2, y2, duration=duration)
            time.sleep(0.05)
            self._pa.mouseUp(button=button)
        except Exception as exc:
            raise BackendError(f"拖拽失败: {exc}")

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        try:
            if x is not None and y is not None:
                self._pa.moveTo(x, y, duration=0.1)
            self._pa.scroll(amount)
        except Exception as exc:
            raise BackendError(f"滚轮失败: {exc}")

    def type_text(self, text: str, interval: float = 0.02) -> None:
        if not text:
            return
        try:
            self._pa.typewrite(text, interval=interval)
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.05)
                self._pa.hotkey("ctrl", "v")
            except Exception as exc:
                raise BackendError(
                    f"输入失败（非 ASCII 需 pyperclip: pip install pyperclip）: {exc}"
                )

    def press_key(self, key: str) -> None:
        try:
            self._pa.press(key)
        except Exception as exc:
            raise BackendError(f"按键失败 {key!r}: {exc}")

    def hotkey(self, *keys: str) -> None:
        try:
            self._pa.hotkey(*keys)
        except Exception as exc:
            raise BackendError(f"快捷键失败 {keys}: {exc}")

    def list_windows(self) -> list[dict]:
        try:
            import pygetwindow as gw
        except ImportError:
            raise BackendError("需要 pygetwindow。运行：pip install pygetwindow")
        out: list[dict] = []
        try:
            for w in gw.getAllWindows():
                title = (w.title or "").strip()
                if not title:
                    continue
                out.append({
                    "title": title,
                    "x": int(w.left), "y": int(w.top),
                    "width": int(w.width), "height": int(w.height),
                    "active": bool(getattr(w, "isActive", False)),
                    "minimized": bool(getattr(w, "isMinimized", False)),
                })
        except Exception as exc:
            raise BackendError(f"枚举窗口失败: {exc}")
        return out

    def activate_window(self, title_substr: str) -> str:
        try:
            import pygetwindow as gw
        except ImportError:
            raise BackendError("需要 pygetwindow。运行：pip install pygetwindow")
        matches = [w for w in gw.getAllWindows()
                   if title_substr.lower() in (w.title or "").lower()]
        if not matches:
            raise BackendError(f"未找到标题含 {title_substr!r} 的窗口")
        w = matches[0]
        try:
            if w.isMinimized:
                w.restore()
            w.activate()
        except Exception as exc:
            raise BackendError(f"激活窗口失败: {exc}")
        return w.title or ""

    def minimize_window(self, title_substr: str) -> str:
        try:
            import pygetwindow as gw
        except ImportError:
            raise BackendError("需要 pygetwindow")
        matches = [w for w in gw.getAllWindows()
                   if title_substr.lower() in (w.title or "").lower()]
        if not matches:
            raise BackendError(f"未找到标题含 {title_substr!r} 的窗口")
        matches[0].minimize()
        return matches[0].title or ""

    def maximize_window(self, title_substr: str) -> str:
        try:
            import pygetwindow as gw
        except ImportError:
            raise BackendError("需要 pygetwindow")
        matches = [w for w in gw.getAllWindows()
                   if title_substr.lower() in (w.title or "").lower()]
        if not matches:
            raise BackendError(f"未找到标题含 {title_substr!r} 的窗口")
        matches[0].maximize()
        return matches[0].title or ""


def get_backend() -> ComputerBackend:
    global _backend_instance
    with _backend_lock:
        if _backend_instance is None:
            _backend_instance = ComputerBackend()
        return _backend_instance


def reset_backend() -> None:
    global _backend_instance
    with _backend_lock:
        _backend_instance = None