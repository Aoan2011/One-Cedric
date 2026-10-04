"""微信 PC 版 UI 自动化（Windows only）。

依赖: pyautogui, pygetwindow, pyperclip, Pillow
限制: 需要微信已登录且窗口可见。
朋友圈: 需要手动打开朋友圈窗口，脚本只做定位+截图+OCR。
"""
from __future__ import annotations

import platform
import time
from pathlib import Path

from .sandbox import _resolve_path


IS_WINDOWS = platform.system() == "Windows"


def _deps():
    if not IS_WINDOWS:
        return None, "微信工具仅支持 Windows"
    try:
        import pyautogui  # noqa
        import pygetwindow as gw
        import pyperclip
        return (pyautogui, gw, pyperclip), ""
    except ImportError as exc:
        return None, (f"需要: pyautogui pygetwindow pyperclip\n"
                       f"pip install pyautogui pygetwindow pyperclip\n"
                       f"错误: {exc}")


def wechat_status() -> str:
    deps, err = _deps()
    if err:
        return err
    pg, gw, _ = deps

    windows = []
    for w in gw.getAllWindows():
        t = w.title or ""
        if "微信" in t or "WeChat" in t or t == "Weixin":
            windows.append({
                "title": t,
                "left": w.left, "top": w.top,
                "width": w.width, "height": w.height,
                "visible": w.visible, "minimized": w.isMinimized,
                "active": w.isActive,
            })

    if not windows:
        return "未找到微信窗口（请确保微信 PC 版已登录并打开）"

    lines = [f"找到 {len(windows)} 个微信窗口：", ""]
    for i, w in enumerate(windows, 1):
        lines.append(f"[{i}] {w['title']}")
        lines.append(f"    位置 ({w['left']},{w['top']}) "
                     f"大小 {w['width']}×{w['height']}")
        lines.append(f"    可见: {w['visible']}  最小化: {w['minimized']}  "
                     f"激活: {w['active']}")
    return "\n".join(lines)


def _focus_wechat():
    deps, err = _deps()
    if err:
        return None, err
    pg, gw, _ = deps

    for w in gw.getAllWindows():
        t = w.title or ""
        if "微信" in t or "WeChat" in t:
            try:
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.4)
                return w, ""
            except Exception as exc:
                return None, f"无法激活窗口: {exc}"
    return None, "未找到微信窗口"


def wechat_send(contact: str, message: str) -> str:
    """给指定联系人发消息。"""
    deps, err = _deps()
    if err:
        return err
    pg, gw, pyperclip = deps

    w, ferr = _focus_wechat()
    if ferr:
        return f"ERROR: {ferr}"

    time.sleep(0.3)

    # Ctrl+F 打开搜索
    pg.hotkey("ctrl", "f")
    time.sleep(0.6)
    pyperclip.copy(contact)
    pg.hotkey("ctrl", "v")
    time.sleep(0.8)
    pg.press("enter")
    time.sleep(0.5)

    # 输入消息
    pyperclip.copy(message)
    pg.hotkey("ctrl", "v")
    time.sleep(0.3)
    pg.press("enter")
    time.sleep(0.3)

    return f"已发送给 '{contact}': {message[:60]}"


def wechat_read_recent(contact: str = "", count: int = 10) -> str:
    """读取与某联系人的最近消息（截图 + OCR）。"""
    deps, err = _deps()
    if err:
        return err
    pg, gw, _ = deps

    from .ocr import ocr_image

    w, ferr = _focus_wechat()
    if ferr:
        return f"ERROR: {ferr}"

    if contact:
        pg.hotkey("ctrl", "f")
        time.sleep(0.6)
        import pyperclip
        pyperclip.copy(contact)
        pg.hotkey("ctrl", "v")
        time.sleep(0.8)
        pg.press("enter")
        time.sleep(0.6)

    # 截图
    tmp = Path.cwd() / ".cedric_wechat_tmp.png"
    try:
        shot = pg.screenshot(region=(w.left, w.top, w.width, w.height))
        shot.save(tmp)
    except Exception as exc:
        return f"ERROR: 截图失败: {exc}"

    # OCR
    try:
        text = ocr_image(str(tmp), Path.cwd(), lang="chi_sim+eng")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    return (f"与 '{contact or '(当前)'}' 的聊天截图 OCR：\n"
            f"{text[:3000]}")


def wechat_moments_read() -> str:
    """读取朋友圈（需要用户手动打开朋友圈窗口）。"""
    deps, err = _deps()
    if err:
        return err
    pg, gw, _ = deps

    from .ocr import ocr_image

    # 找朋友圈窗口
    target = None
    for w in gw.getAllWindows():
        t = w.title or ""
        if "朋友圈" in t:
            target = w
            break

    if not target:
        return ("ERROR: 未找到朋友圈窗口。\n"
                "请手动点击微信左侧「朋友圈」按钮打开。")

    try:
        target.activate()
        time.sleep(0.4)
    except Exception:
        pass

    tmp = Path.cwd() / ".cedric_moments_tmp.png"
    try:
        shot = pg.screenshot(
            region=(target.left, target.top, target.width, target.height))
        shot.save(tmp)
    except Exception as exc:
        return f"ERROR: 截图失败: {exc}"

    try:
        text = ocr_image(str(tmp), Path.cwd(), lang="chi_sim+eng")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    return f"朋友圈截图 OCR：\n{text[:5000]}"


def wechat_moments_post(text: str, images: list | None = None) -> str:
    """发朋友圈。需要朋友圈窗口已打开。"""
    deps, err = _deps()
    if err:
        return err
    pg, gw, pyperclip = deps

    target = None
    for w in gw.getAllWindows():
        if "朋友圈" in (w.title or ""):
            target = w
            break
    if not target:
        return "ERROR: 需要先打开朋友圈窗口"

    try:
        target.activate()
        time.sleep(0.5)
    except Exception:
        pass

    # 模拟点击"发表"按钮（位置依赖窗口大小，非常脆弱）
    # 简单策略：用键盘快捷键，微信朋友圈没有默认快捷键
    # 保守做法：只粘贴到剪贴板 + 提示用户手动
    pyperclip.copy(text)
    return ("已复制内容到剪贴板。\n"
            "⚠ 朋友圈自动发布非常脆弱，请在朋友圈窗口手动：\n"
            "  1. 点击右上角「相机」\n"
            "  2. 粘贴文字（Ctrl+V）\n"
            "  3. 点击「发表」\n\n"
            f"内容预览：{text[:100]}")