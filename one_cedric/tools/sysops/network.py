"""WLAN 管理。"""
from __future__ import annotations

import re

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, unsupported


def _win_wifi_status() -> str:
    rc, out, err = run_cmd(["netsh", "wlan", "show", "interfaces"])
    if rc != 0:
        return f"ERROR: {err}"
    keys = ("名称", "Name", "状态", "State", "SSID", "BSSID",
            "信号", "Signal", "接收速率", "发送速率",
            "无线电类型", "Radio type", "身份验证", "Authentication")
    lines = [l.strip() for l in out.splitlines()
             if any(k in l for k in keys)]
    if not lines:
        return "未找到 WLAN 接口（可能没有无线网卡）"
    return "WLAN 状态:\n" + "\n".join(lines[:20])


def _win_wifi_list() -> str:
    rc, out, err = run_cmd(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if rc != 0:
        return f"ERROR: {err}"
    ssids = re.findall(r"SSID\s+\d+\s*[:：]\s*(.+)", out)
    if not ssids:
        return "未找到可用 WLAN 网络"
    seen = []
    for s in ssids:
        s = s.strip()
        if s and s not in seen:
            seen.append(s)
    lines = [f"可用 WLAN（{len(seen)}）:"]
    for s in seen:
        lines.append(f"  · {s}")
    return "\n".join(lines)


def _win_wifi_connect(ssid: str, password: str = "") -> str:
    if not ssid:
        return "ERROR: 需要 ssid"
    if not password:
        rc, out, err = run_cmd(["netsh", "wlan", "connect", f"name={ssid}"],
                               timeout=30)
        if rc == 0:
            return f"已连接: {ssid}"
        return f"ERROR: 连接失败: {err.strip() or out.strip()}"

    import tempfile
    from pathlib import Path
    profile = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{ssid}</name>
  <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>auto</connectionMode>
  <MSM><security>
    <authEncryption>
      <authentication>WPA2PSK</authentication>
      <encryption>AES</encryption>
      <useOneX>false</useOneX>
    </authEncryption>
    <sharedKey>
      <keyType>passPhrase</keyType>
      <protected>false</protected>
      <keyMaterial>{password}</keyMaterial>
    </sharedKey>
  </security></MSM>
</WLANProfile>"""
    tmp = Path(tempfile.gettempdir()) / f"one_cedric_wlan_{ssid}.xml"
    try:
        tmp.write_text(profile, encoding="utf-8")
        rc, out, err = run_cmd(["netsh", "wlan", "add", "profile",
                                f"filename={tmp}"], timeout=20)
        if rc != 0:
            return f"ERROR: 添加 profile 失败: {err.strip()}"
        rc, out, err = run_cmd(["netsh", "wlan", "connect", f"name={ssid}"],
                               timeout=30)
        if rc != 0:
            return f"ERROR: 连接失败: {err.strip()}"
        return f"已连接: {ssid}"
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _win_wifi_disconnect() -> str:
    rc, _, err = run_cmd(["netsh", "wlan", "disconnect"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已断开 WLAN"


def _mac_iface() -> str:
    rc, out, _ = run_cmd(["networksetup", "-listallhardwareports"])
    if rc != 0:
        return "en0"
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort).*?Device:\s*(\w+)",
                  out, re.DOTALL)
    return m.group(1) if m else "en0"


def _mac_wifi_status() -> str:
    iface = _mac_iface()
    rc, out, err = run_cmd(["networksetup", "-getairportnetwork", iface])
    if rc != 0:
        return f"ERROR: {err}"
    return out.strip()


def _mac_wifi_list() -> str:
    rc, out, err = run_cmd([
        "/System/Library/PrivateFrameworks/Apple80211.framework/"
        "Versions/Current/Resources/airport", "-s",
    ])
    if rc == 0 and out.strip():
        return "可用 WLAN:\n" + out.strip()
    return unsupported("列出 WLAN（airport 命令在新系统中移除）")


def _mac_wifi_connect(ssid: str, password: str = "") -> str:
    iface = _mac_iface()
    cmd = ["networksetup", "-setairportnetwork", iface, ssid]
    if password:
        cmd.append(password)
    rc, _, err = run_cmd(cmd, timeout=30)
    if rc != 0:
        return f"ERROR: {err}"
    return f"已连接: {ssid}"


def _mac_wifi_disconnect() -> str:
    iface = _mac_iface()
    rc, _, err = run_cmd(["networksetup", "-setairportpower", iface, "off"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已断开 WLAN"


def _linux_wifi_status() -> str:
    if not has_cmd("nmcli"):
        return unsupported("WLAN（需 NetworkManager / nmcli）")
    rc, out, err = run_cmd(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL",
                            "device", "wifi"])
    if rc != 0:
        return f"ERROR: {err}"
    lines = ["WLAN 状态:"]
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            active = "✓" if parts[0] == "yes" else " "
            lines.append(f"  [{active}] {parts[1]} ({parts[2]}%)")
    return "\n".join(lines) if len(lines) > 1 else "未找到 WLAN"


def _linux_wifi_list() -> str:
    if not has_cmd("nmcli"):
        return unsupported("WLAN")
    rc, out, err = run_cmd(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY",
                            "device", "wifi", "list"])
    if rc != 0:
        return f"ERROR: {err}"
    lines = ["可用 WLAN:"]
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            lines.append(f"  · {parts[0]}  ({parts[1]}%  {parts[2]})")
    return "\n".join(lines)


def _linux_wifi_connect(ssid: str, password: str = "") -> str:
    if not has_cmd("nmcli"):
        return unsupported("WLAN")
    if password:
        cmd = ["nmcli", "device", "wifi", "connect", ssid, "password", password]
    else:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
    rc, _, err = run_cmd(cmd, timeout=30)
    if rc != 0:
        return f"ERROR: {err}"
    return f"已连接: {ssid}"


def _linux_wifi_disconnect() -> str:
    if not has_cmd("nmcli"):
        return unsupported("WLAN")
    rc, _, err = run_cmd(["nmcli", "device", "disconnect", "wifi"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已断开 WLAN"


def wifi_status() -> str:
    if IS_WINDOWS:
        return _win_wifi_status()
    if IS_MAC:
        return _mac_wifi_status()
    if IS_LINUX:
        return _linux_wifi_status()
    return unsupported("WLAN")


def wifi_list() -> str:
    if IS_WINDOWS:
        return _win_wifi_list()
    if IS_MAC:
        return _mac_wifi_list()
    if IS_LINUX:
        return _linux_wifi_list()
    return unsupported("WLAN")


def wifi_connect(ssid: str, password: str = "") -> str:
    if IS_WINDOWS:
        return _win_wifi_connect(ssid, password)
    if IS_MAC:
        return _mac_wifi_connect(ssid, password)
    if IS_LINUX:
        return _linux_wifi_connect(ssid, password)
    return unsupported("WLAN")


def wifi_disconnect() -> str:
    if IS_WINDOWS:
        return _win_wifi_disconnect()
    if IS_MAC:
        return _mac_wifi_disconnect()
    if IS_LINUX:
        return _linux_wifi_disconnect()
    return unsupported("WLAN")