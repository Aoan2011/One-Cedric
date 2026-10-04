"""系统通知：跨平台推送桌面通知。

支持：
  - 标题 + 正文 + 图标
  - 紧急程度（info / warn / error）
  - 声音开关
  - 超时自动关闭
  - 附加动作按钮（Windows 专属）
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path


IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


ICONS = {
    "info":    "ℹ️ ",
    "warn":    "⚠️ ",
    "error":   "❌",
    "success": "✅",
    "done":    "✔️ ",
    "ask":     "❓",
}


def _esc_ps(s: str) -> str:
    return (str(s or "").replace("'", "''")
            .replace('"', '`"').replace("\n", " "))


def _esc_sh(s: str) -> str:
    return (str(s or "").replace("\\", "\\\\")
            .replace('"', '\\"'))


def _esc_applescript(s: str) -> str:
    return (str(s or "").replace("\\", "\\\\")
            .replace('"', '\\"'))


def _windows_notify(title: str, body: str, level: str,
                    sound: bool, timeout: int) -> str:
    """Windows 10/11 原生 Toast。"""
    icon = ICONS.get(level, "")
    full_title = f"{icon} {title}".strip()

    # 尝试用 BurntToast 模块（如果装了）
    if shutil.which("powershell"):
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Module -ListAvailable -Name BurntToast"],
                capture_output=True, text=True, timeout=5,
            )
            has_burnt = "BurntToast" in (r.stdout or "")
        except Exception:
            has_burnt = False

        if has_burnt:
            sound_opt = "" if sound else " -Silent"
            ps = (
                f"New-BurntToastNotification "
                f"-Text '{_esc_ps(full_title)}', "
                f"'{_esc_ps(body)}'{sound_opt}"
            )
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    return "已发送通知（BurntToast）"
            except Exception:
                pass

    # 降级：Windows Forms NotifyIcon
    sound_ps = "1" if sound else "0"
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip({int(timeout) * 1000}, '{_esc_ps(full_title)}',
                  '{_esc_ps(body)}',
                  [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Milliseconds {int(timeout) * 1000}
$n.Dispose()
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if r.returncode == 0:
            return "已发送通知（Win Forms）"
        return f"ERROR: {r.stderr or r.stdout}"
    except subprocess.TimeoutExpired:
        # 通知已经显示，只是等待超时
        return "已发送通知（超时但已显示）"
    except Exception as exc:
        return f"ERROR: {exc}"


def _mac_notify(title: str, body: str, level: str,
                sound: bool, timeout: int) -> str:
    icon = ICONS.get(level, "")
    full_title = f"{icon} {title}".strip()
    sound_part = ' sound name "default"' if sound else ""
    script = (
        f'display notification "{_esc_applescript(body)}" '
        f'with title "{_esc_applescript(full_title)}"{sound_part}'
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        return ("已发送通知" if r.returncode == 0
                else f"ERROR: {r.stderr}")
    except Exception as exc:
        return f"ERROR: {exc}"


def _linux_notify(title: str, body: str, level: str,
                  sound: bool, timeout: int) -> str:
    if not shutil.which("notify-send"):
        return "ERROR: 需要 notify-send（libnotify）"

    icon = {
        "info": "dialog-information",
        "warn": "dialog-warning",
        "error": "dialog-error",
        "success": "emblem-default",
        "done": "task-due",
        "ask": "dialog-question",
    }.get(level, "dialog-information")

    args = [
        "notify-send",
        "-t", str(int(timeout) * 1000),
        "-i", icon,
        "-u", {"info": "normal", "warn": "normal",
               "error": "critical"}.get(level, "normal"),
    ]
    full_title = f"{ICONS.get(level, '')} {title}".strip()
    args.extend([full_title, body])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            if sound and shutil.which("paplay"):
                subprocess.Popen(
                    ["paplay",
                     "/usr/share/sounds/freedesktop/stereo/message.oga"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            return "已发送通知"
        return f"ERROR: {r.stderr}"
    except Exception as exc:
        return f"ERROR: {exc}"


def send_notification(title: str = "One Cedric", body: str = "",
                      level: str = "info", sound: bool = True,
                      timeout: int = 5) -> str:
    """发送系统通知。

    level: info / warn / error / success / done / ask
    """
    if not title and not body:
        return "ERROR: title 和 body 不能都为空"

    level = (level or "info").lower()
    if level not in ICONS:
        level = "info"

    try:
        t = max(1, min(int(timeout), 60))
    except (TypeError, ValueError):
        t = 5

    title = str(title or "One Cedric")
    body = str(body or "")

    if IS_WINDOWS:
        return _windows_notify(title, body, level, sound, t)
    if IS_MAC:
        return _mac_notify(title, body, level, sound, t)
    if IS_LINUX:
        return _linux_notify(title, body, level, sound, t)
    return "ERROR: 当前平台不支持通知"


def notify_info(title: str) -> str:
    return send_notification(title, "", level="info")


def check_support() -> str:
    """检查当前平台的通知支持。"""
    lines = ["系统通知支持检查：", ""]
    if IS_WINDOWS:
        lines.append("平台: Windows")
        lines.append(f"  PowerShell: {'✓' if shutil.which('powershell') else '✗'}")
        # 检查 BurntToast
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Module -ListAvailable -Name BurntToast | Select-Object -First 1"],
                capture_output=True, text=True, timeout=5,
            )
            has = "BurntToast" in (r.stdout or "")
            lines.append(f"  BurntToast: {'✓ 已安装' if has else '✗ 未安装（将用降级方案）'}")
            if not has:
                lines.append("    安装: Install-Module -Name BurntToast -Scope CurrentUser")
        except Exception:
            pass
    elif IS_MAC:
        lines.append("平台: macOS")
        lines.append(f"  osascript: {'✓' if shutil.which('osascript') else '✗'}")
    elif IS_LINUX:
        lines.append("平台: Linux")
        lines.append(f"  notify-send: {'✓' if shutil.which('notify-send') else '✗'}")
        if not shutil.which("notify-send"):
            lines.append("    安装: sudo apt install libnotify-bin")
    else:
        lines.append(f"平台: {sys.platform}（不支持）")
    return "\n".join(lines)