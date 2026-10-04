"""亮度和深色模式。"""
from __future__ import annotations

import re

from ._platform import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    has_cmd, run_cmd, powershell, unsupported,
)


def _win_brightness_get() -> str:
    if not has_cmd("powershell"):
        return "ERROR: 需要 PowerShell"
    ps = ("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
          "-ErrorAction SilentlyContinue).CurrentBrightness")
    rc, out, err = powershell(ps)
    if rc != 0 or not out.strip():
        return "ERROR: 读取亮度失败（显示器可能不支持亮度调节）"
    try:
        return f"亮度: {int(out.strip())}%"
    except ValueError:
        return f"亮度: {out.strip()}"


def _win_brightness_set(value: int) -> str:
    ps = (f"(Get-CimInstance -Namespace root/WMI "
          f"-ClassName WmiMonitorBrightnessMethods "
          f"-ErrorAction SilentlyContinue).WmiSetBrightness(1, {value})")
    rc, out, err = powershell(ps)
    if rc != 0:
        return f"ERROR: 设置亮度失败: {err.strip()}"
    return f"已设置亮度: {value}%"


def _mac_brightness_get() -> str:
    if has_cmd("brightness"):
        rc, out, _ = run_cmd(["brightness", "-l"])
        if rc == 0:
            return f"亮度信息:\n{out.strip()}"
    return unsupported("读取亮度（需 brew install brightness）")


def _mac_brightness_set(value: int) -> str:
    if has_cmd("brightness"):
        v = value / 100.0
        rc, _, err = run_cmd(["brightness", str(v)])
        if rc == 0:
            return f"已设置亮度: {value}%"
        return f"ERROR: {err}"
    return unsupported("设置亮度（需 brew install brightness）")


def _linux_brightness_get() -> str:
    if has_cmd("brightnessctl"):
        rc, out, _ = run_cmd(["brightnessctl", "get"])
        rc2, out2, _ = run_cmd(["brightnessctl", "max"])
        if rc == 0 and rc2 == 0:
            try:
                pct = int(int(out.strip()) / int(out2.strip()) * 100)
                return f"亮度: {pct}%（{out.strip()}/{out2.strip()}）"
            except Exception:
                return f"亮度: {out.strip()}/{out2.strip()}"
    if has_cmd("xrandr"):
        rc, out, _ = run_cmd(["xrandr", "--verbose"])
        if rc == 0:
            m = re.search(r"Brightness:\s*([\d.]+)", out)
            if m:
                return f"亮度: {float(m.group(1)) * 100:.0f}%"
    return unsupported("读取亮度（需 brightnessctl）")


def _linux_brightness_set(value: int) -> str:
    if has_cmd("brightnessctl"):
        rc, _, _ = run_cmd(["brightnessctl", "set", f"{value}%"])
        if rc == 0:
            return f"已设置亮度: {value}%"
    return unsupported("设置亮度")


def brightness_get() -> str:
    if IS_WINDOWS:
        return _win_brightness_get()
    if IS_MAC:
        return _mac_brightness_get()
    if IS_LINUX:
        return _linux_brightness_get()
    return unsupported("亮度")


def brightness_set(value) -> str:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "ERROR: value 必须是 0-100 的整数"
    if not 0 <= v <= 100:
        return "ERROR: 亮度必须在 0-100"
    if IS_WINDOWS:
        return _win_brightness_set(v)
    if IS_MAC:
        return _mac_brightness_set(v)
    if IS_LINUX:
        return _linux_brightness_set(v)
    return unsupported("亮度")


def _win_theme_get() -> str:
    try:
        import winreg
    except ImportError:
        return "ERROR: winreg 仅 Windows 可用"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "主题: 深色" if val == 0 else "主题: 浅色"
    except Exception as exc:
        return f"ERROR: 读取主题失败: {exc}"


def _win_theme_set(theme: str) -> str:
    try:
        import winreg
    except ImportError:
        return "ERROR: winreg 仅 Windows 可用"
    val = 0 if theme == "dark" else 1
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, val)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, val)
        winreg.CloseKey(key)
        return f"已设置主题: {'深色' if val == 0 else '浅色'}"
    except Exception as exc:
        return f"ERROR: 设置主题失败: {exc}"


def _mac_theme_get() -> str:
    rc, out, _ = run_cmd(["defaults", "read", "-g", "AppleInterfaceStyle"])
    if rc == 0 and "Dark" in out:
        return "主题: 深色"
    return "主题: 浅色"


def _mac_theme_set(theme: str) -> str:
    b = "true" if theme == "dark" else "false"
    rc, _, err = run_cmd([
        "osascript", "-e",
        f'tell application "System Events" to tell appearance preferences '
        f'to set dark mode to {b}',
    ])
    if rc != 0:
        return f"ERROR: {err}"
    return f"已设置主题: {'深色' if theme == 'dark' else '浅色'}"


def _linux_theme_get() -> str:
    if not has_cmd("gsettings"):
        return unsupported("读取主题（需 gsettings）")
    rc, out, _ = run_cmd(["gsettings", "get",
                          "org.gnome.desktop.interface", "color-scheme"])
    if rc == 0 and "dark" in out.lower():
        return "主题: 深色"
    return "主题: 浅色"


def _linux_theme_set(theme: str) -> str:
    if not has_cmd("gsettings"):
        return unsupported("设置主题")
    scheme = "'prefer-dark'" if theme == "dark" else "'default'"
    rc, _, err = run_cmd(["gsettings", "set",
                          "org.gnome.desktop.interface", "color-scheme", scheme])
    if rc != 0:
        return f"ERROR: {err}"
    return f"已设置主题: {'深色' if theme == 'dark' else '浅色'}"


def theme_get() -> str:
    if IS_WINDOWS:
        return _win_theme_get()
    if IS_MAC:
        return _mac_theme_get()
    if IS_LINUX:
        return _linux_theme_get()
    return unsupported("主题")


def theme_set(theme: str) -> str:
    theme = (theme or "").lower()
    if theme not in ("dark", "light"):
        return "ERROR: theme 必须是 'dark' 或 'light'"
    if IS_WINDOWS:
        return _win_theme_set(theme)
    if IS_MAC:
        return _mac_theme_set(theme)
    if IS_LINUX:
        return _linux_theme_set(theme)
    return unsupported("主题")