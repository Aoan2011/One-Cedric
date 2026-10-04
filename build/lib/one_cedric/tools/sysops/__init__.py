"""系统操作工具：音量、亮度、主题、网络、蓝牙、打印机、更新。"""
from __future__ import annotations

from pathlib import Path

from .audio import volume_get, volume_set, volume_mute
from .display import brightness_get, brightness_set, theme_get, theme_set
from .network import wifi_status, wifi_list, wifi_connect, wifi_disconnect
from .bluetooth import bt_status, bt_toggle, bt_list
from .printer import printer_list, printer_default, printer_print
from .update import check_update


READONLY_OPS = {
    "volume_get",
    "brightness_get",
    "theme_get",
    "wifi_status", "wifi_list",
    "bt_status", "bt_list",
    "printer_list", "printer_default",
    "check_update",
}


def sysop_op(root: Path, args: dict):
    """统一入口。只读 op 返回 str，写 op 返回 (preview, is_write, err)。"""
    op = str(args.get("op", "")).lower()

    if op == "volume_get":
        return volume_get()
    if op == "brightness_get":
        return brightness_get()
    if op == "theme_get":
        return theme_get()
    if op == "wifi_status":
        return wifi_status()
    if op == "wifi_list":
        return wifi_list()
    if op == "bt_status":
        return bt_status()
    if op == "bt_list":
        return bt_list()
    if op == "printer_list":
        return printer_list()
    if op == "printer_default":
        return printer_default()
    if op == "check_update":
        return check_update()

    if op == "volume_set":
        v = args.get("value")
        return f"将设置音量为 {v}%", True, ""
    if op == "volume_mute":
        return "将静音", True, ""
    if op == "volume_unmute":
        return "将取消静音", True, ""
    if op == "brightness_set":
        v = args.get("value")
        return f"将设置亮度为 {v}%", True, ""
    if op == "theme_set":
        t = args.get("theme", "")
        return f"将切换主题为: {t}", True, ""
    if op == "wifi_connect":
        ssid = args.get("ssid", "")
        return f"将连接到 WLAN: {ssid}", True, ""
    if op == "wifi_disconnect":
        return "将断开 WLAN", True, ""
    if op == "bt_on":
        return "将开启蓝牙", True, ""
    if op == "bt_off":
        return "将关闭蓝牙", True, ""
    if op == "printer_print":
        path = args.get("path", "")
        printer = args.get("printer", "") or "默认打印机"
        return f"将打印 {path} → {printer}", True, ""

    return "", False, f"ERROR: 未知 sysop op: {op}"


def sysop_apply(root: Path, args: dict) -> str:
    """执行写操作。"""
    from ..sandbox import _resolve_path

    op = str(args.get("op", "")).lower()

    if op == "volume_set":
        return volume_set(args.get("value"))
    if op == "volume_mute":
        return volume_mute(True)
    if op == "volume_unmute":
        return volume_mute(False)
    if op == "brightness_set":
        return brightness_set(args.get("value"))
    if op == "theme_set":
        return theme_set(args.get("theme", ""))
    if op == "wifi_connect":
        return wifi_connect(args.get("ssid", ""), args.get("password", ""))
    if op == "wifi_disconnect":
        return wifi_disconnect()
    if op == "bt_on":
        return bt_toggle(True)
    if op == "bt_off":
        return bt_toggle(False)
    if op == "printer_print":
        p, err = _resolve_path(root, str(args.get("path", "")))
        if err:
            return err
        return printer_print(p, args.get("printer", "") or "")

    return f"ERROR: 未知 sysop 写 op: {op}"


__all__ = [
    "sysop_op", "sysop_apply", "READONLY_OPS",
]