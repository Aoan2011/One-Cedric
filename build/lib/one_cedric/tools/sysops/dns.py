"""DNS 配置管理。

Windows: Get/Set-DnsClientServerAddress（需管理员）
Linux:   resolvectl（systemd-resolved）或 nmcli
macOS:   networksetup
"""
from __future__ import annotations

import json
import re

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_IPV6 = re.compile(r"^[0-9a-fA-F:]+$")


def _is_ip(s: str) -> bool:
    if _IPV4.match(s):
        parts = s.split(".")
        return all(0 <= int(p) <= 255 for p in parts)
    if ":" in s and _IPV6.match(s):
        return True
    return False


def _win_active_interfaces() -> list[str]:
    ps = ("Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
          "Select-Object InterfaceAlias | ConvertTo-Json -Compress")
    rc, out, err = powershell(ps, timeout=15)
    if rc != 0 or not out.strip():
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [str(d.get("InterfaceAlias", "")) for d in data
                if d.get("InterfaceAlias")]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════ #
# 只读
# ═══════════════════════════════════════════════════════════════════════ #

def dns_get(interface: str = "") -> str:
    if IS_WINDOWS:
        if interface:
            ps = (f"Get-DnsClientServerAddress -InterfaceAlias '{interface}' "
                  f"| Select-Object InterfaceAlias,AddressFamily,ServerAddresses "
                  f"| Format-List")
        else:
            ps = ("Get-DnsClientServerAddress | "
                  "Where-Object {$_.ServerAddresses} | "
                  "Select-Object InterfaceAlias,AddressFamily,ServerAddresses | "
                  "Format-Table -AutoSize")
        rc, out, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}"
        if not out.strip():
            ifaces = _win_active_interfaces()
            return (f"未配置静态 DNS。可用接口：{', '.join(ifaces) or '(无)'}")

        # 附加接口列表
        ifaces = _win_active_interfaces()
        return out.strip() + ("\n\n可用接口: " + ", ".join(ifaces) if ifaces else "")

    if IS_LINUX:
        if has_cmd("resolvectl"):
            rc, out, _ = run_cmd(["resolvectl", "status"])
            return out.strip()[:3000] or "resolvectl 无输出"
        if has_cmd("nmcli"):
            rc, out, _ = run_cmd(["nmcli", "-t", "-f",
                                  "NAME,DEVICE,IP4.DNS,IP6.DNS",
                                  "device", "show"])
            return out.strip() or "nmcli 无输出"
        try:
            from pathlib import Path
            return Path("/etc/resolv.conf").read_text(encoding="utf-8")[:2000]
        except Exception as exc:
            return f"ERROR: {exc}"

    if IS_MAC:
        if has_cmd("scutil"):
            rc, out, _ = run_cmd(["scutil", "--dns"])
            return out.strip()[:3000]
        return "ERROR: 需要 scutil"

    return "ERROR: 当前平台不支持"


# ═══════════════════════════════════════════════════════════════════════ #
# 写操作
# ═══════════════════════════════════════════════════════════════════════ #

def dns_set(servers: list, interface: str = "") -> str:
    if not servers or not isinstance(servers, list):
        return "ERROR: servers 必须是非空数组"
    servers = [str(s).strip() for s in servers if str(s).strip()]
    if not servers:
        return "ERROR: 无有效服务器"

    for s in servers:
        if not _is_ip(s):
            return f"ERROR: 不是有效 IP: {s}"

    if IS_WINDOWS:
        if not interface:
            ifaces = _win_active_interfaces()
            if not ifaces:
                return "ERROR: 无法获取活动网络接口"
            interface = ifaces[0]
        ps = (f"Set-DnsClientServerAddress -InterfaceAlias '{interface}' "
              f"-ServerAddresses {','.join(servers)}")
        rc, _, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"已设置接口 {interface} 的 DNS: {', '.join(servers)}"

    if IS_LINUX:
        if has_cmd("resolvectl"):
            iface = interface or "eth0"
            args = ["resolvectl", "dns", iface] + servers
            rc, _, err = run_cmd(args)
            return (f"已设置 {iface} 的 DNS: {', '.join(servers)}"
                    if rc == 0 else f"ERROR: {err}（可能需要 root）")
        if has_cmd("nmcli"):
            if not interface:
                return "ERROR: 需要 interface（用 nmcli 时）"
            rc, _, err = run_cmd(["nmcli", "con", "mod", interface,
                                  "ipv4.dns", ",".join(servers)])
            if rc != 0:
                return f"ERROR: {err}"
            run_cmd(["nmcli", "con", "up", interface])
            return f"已设置 {interface} 的 DNS: {', '.join(servers)}"
        return "ERROR: 需要 resolvectl 或 nmcli"

    if IS_MAC:
        iface = interface or "Wi-Fi"
        rc, _, err = run_cmd(["networksetup", "-setdnsservers", iface] + servers)
        if rc != 0:
            return f"ERROR: {err}（可能需要 sudo）"
        return f"已设置 {iface} 的 DNS: {', '.join(servers)}"

    return "ERROR: 当前平台不支持"


def dns_reset(interface: str = "") -> str:
    """恢复为 DHCP 自动获取。"""
    if IS_WINDOWS:
        if not interface:
            ifaces = _win_active_interfaces()
            if not ifaces:
                return "ERROR: 无法获取活动接口"
            interface = ifaces[0]
        ps = (f"Set-DnsClientServerAddress -InterfaceAlias '{interface}' "
              f"-ResetServerAddresses")
        rc, _, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"已重置 {interface} 为自动获取"

    if IS_LINUX:
        iface = interface or "eth0"
        if has_cmd("resolvectl"):
            rc, _, err = run_cmd(["resolvectl", "revert", iface])
            return f"已重置 {iface}" if rc == 0 else f"ERROR: {err}"
        if has_cmd("nmcli"):
            if not interface:
                return "ERROR: 需要 interface"
            run_cmd(["nmcli", "con", "mod", interface, "ipv4.ignore-auto-dns", "no"])
            run_cmd(["nmcli", "con", "up", interface])
            return f"已重置 {interface}"
        return "ERROR: 需要 resolvectl 或 nmcli"

    if IS_MAC:
        iface = interface or "Wi-Fi"
        rc, _, err = run_cmd(["networksetup", "-setdnsservers", iface, "Empty"])
        return f"已重置 {iface}" if rc == 0 else f"ERROR: {err}"

    return "ERROR: 当前平台不支持"


def dns_flush() -> str:
    """清空 DNS 缓存。"""
    if IS_WINDOWS:
        rc, out, err = run_cmd(["ipconfig", "/flushdns"])
        if rc != 0:
            return f"ERROR: {err}"
        return "DNS 缓存已清空"

    if IS_LINUX:
        if has_cmd("resolvectl"):
            rc, _, _ = run_cmd(["resolvectl", "flush-caches"])
            if rc == 0:
                return "DNS 缓存已清空（resolvectl）"
        if has_cmd("systemd-resolve"):
            rc, _, _ = run_cmd(["systemd-resolve", "--flush-caches"])
            if rc == 0:
                return "DNS 缓存已清空（systemd-resolve）"
        if has_cmd("nscd"):
            rc, _, _ = run_cmd(["nscd", "-i", "hosts", "-c"])
            if rc == 0:
                return "nscd 缓存已清空"
        return "ERROR: 未找到可用的 DNS 缓存清理工具"

    if IS_MAC:
        run_cmd(["dscacheutil", "-flushcache"])
        run_cmd(["killall", "-HUP", "mDNSResponder"])
        return "DNS 缓存已清空（macOS）"

    return "ERROR: 当前平台不支持"