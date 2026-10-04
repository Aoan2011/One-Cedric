"""蓝牙管理。"""
from __future__ import annotations

from ._platform import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    has_cmd, run_cmd, powershell, unsupported,
)


def _win_status() -> str:
    ps = ("Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
          "Select-Object Status,FriendlyName | Format-Table -AutoSize")
    rc, out, err = powershell(ps, timeout=20)
    if rc != 0:
        return f"ERROR: {err}"
    if not out.strip():
        return "未检测到蓝牙设备（可能没有蓝牙硬件）"
    return "蓝牙设备:\n" + out.strip()


def _win_toggle(on: bool) -> str:
    verb = "Enable" if on else "Disable"
    ps = (f"Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
          f"Where-Object {{$_.FriendlyName -notlike '*Enumerator*'}} | "
          f"{verb}-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue")
    rc, _, err = powershell(ps, timeout=30)
    if rc != 0:
        return f"ERROR: {'开启' if on else '关闭'}蓝牙失败: {err.strip()}"
    return f"已{'开启' if on else '关闭'}蓝牙（可能需要管理员权限）"


def _mac_status() -> str:
    if not has_cmd("blueutil"):
        return unsupported("蓝牙（需 brew install blueutil）")
    rc, out, err = run_cmd(["blueutil", "-p"])
    if rc != 0:
        return f"ERROR: {err}"
    return "蓝牙: 已开启" if out.strip() == "1" else "蓝牙: 已关闭"


def _mac_toggle(on: bool) -> str:
    if not has_cmd("blueutil"):
        return unsupported("蓝牙")
    rc, _, err = run_cmd(["blueutil", "-p", "1" if on else "0"])
    if rc != 0:
        return f"ERROR: {err}"
    return f"已{'开启' if on else '关闭'}蓝牙"


def _mac_list() -> str:
    if not has_cmd("blueutil"):
        return unsupported("蓝牙")
    rc, out, err = run_cmd(["blueutil", "--paired"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已配对设备:\n" + out.strip()


def _linux_status() -> str:
    if not has_cmd("bluetoothctl"):
        return unsupported("蓝牙（需 bluetoothctl）")
    rc, out, err = run_cmd(["bluetoothctl", "show"])
    if rc != 0:
        return f"ERROR: {err}"
    for line in out.splitlines():
        if "Powered" in line:
            return "蓝牙: 已开启" if "yes" in line else "蓝牙: 已关闭"
    return "蓝牙: 状态未知"


def _linux_toggle(on: bool) -> str:
    if not has_cmd("bluetoothctl"):
        return unsupported("蓝牙")
    rc, _, err = run_cmd(["bluetoothctl", "power", "on" if on else "off"])
    if rc != 0:
        return f"ERROR: {err}"
    return f"已{'开启' if on else '关闭'}蓝牙"


def _linux_list() -> str:
    if not has_cmd("bluetoothctl"):
        return unsupported("蓝牙")
    rc, out, err = run_cmd(["bluetoothctl", "paired-devices"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已配对设备:\n" + out.strip()


def bt_status() -> str:
    if IS_WINDOWS:
        return _win_status()
    if IS_MAC:
        return _mac_status()
    if IS_LINUX:
        return _linux_status()
    return unsupported("蓝牙")


def bt_toggle(on: bool) -> str:
    if IS_WINDOWS:
        return _win_toggle(on)
    if IS_MAC:
        return _mac_toggle(on)
    if IS_LINUX:
        return _linux_toggle(on)
    return unsupported("蓝牙")


def bt_list() -> str:
    if IS_WINDOWS:
        return _win_status()
    if IS_MAC:
        return _mac_list()
    if IS_LINUX:
        return _linux_list()
    return unsupported("蓝牙")