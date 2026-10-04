"""防火墙管理：状态查询 + 端口规则。跨平台。

Windows: netsh advfirewall / Get-NetFirewallProfile（需管理员）
Linux:   ufw / firewalld / iptables
macOS:   pfctl / socketfilterfw
"""
from __future__ import annotations

import subprocess

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


# ═══════════════════════════════════════════════════════════════════════ #
# 只读
# ═══════════════════════════════════════════════════════════════════════ #

def firewall_status() -> str:
    if IS_WINDOWS:
        ps = ("Get-NetFirewallProfile | "
              "Select-Object Name,Enabled,DefaultInboundAction,"
              "DefaultOutboundAction | Format-Table -AutoSize")
        rc, out, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return out.strip() or "（无输出）"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, out, _ = run_cmd(["ufw", "status", "verbose"])
            return out.strip() or "ufw 未激活"
        if has_cmd("firewall-cmd"):
            rc, out, _ = run_cmd(["firewall-cmd", "--state"])
            state = out.strip() or "(状态未知)"
            rc2, out2, _ = run_cmd(["firewall-cmd", "--list-all"])
            return f"状态: {state}\n\n{out2.strip()}"
        if has_cmd("iptables"):
            rc, out, _ = run_cmd(["iptables", "-L", "-n", "--line-numbers"])
            return out.strip()[:3000] or "iptables 无规则"
        return "ERROR: 需要 ufw / firewalld / iptables"

    if IS_MAC:
        fw = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        if has_cmd(fw) or __import__("pathlib").Path(fw).exists():
            rc, out, _ = run_cmd([fw, "--getglobalstate"])
            state = out.strip() or "(未知)"
            rc2, out2, _ = run_cmd([fw, "--getstealthmode"])
            stealth = out2.strip() or ""
            return f"全局状态: {state}\n隐身模式: {stealth}"
        if has_cmd("pfctl"):
            rc, out, _ = run_cmd(["pfctl", "-s", "info"])
            return out.strip()[:1500]
        return "ERROR: 未找到 socketfilterfw / pfctl"

    return "ERROR: 当前平台不支持"


def firewall_rule_list(chain: str = "", limit: int = 60) -> str:
    try:
        n = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        n = 60

    if IS_WINDOWS:
        ps = (f"Get-NetFirewallRule -Enabled True | "
              f"Select-Object -First {n} DisplayName,Direction,Action,Profile | "
              f"Format-Table -AutoSize")
        rc, out, err = powershell(ps, timeout=20)
        return out.strip() or f"ERROR: {err}（可能需要管理员权限）"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, out, _ = run_cmd(["ufw", "status", "numbered"])
            return out.strip() or "（ufw 无规则）"
        if has_cmd("firewall-cmd"):
            rc, out, _ = run_cmd(["firewall-cmd", "--list-all"])
            return out.strip()
        if has_cmd("iptables"):
            args = ["iptables", "-L", "-n", "--line-numbers"]
            if chain:
                args.append(chain)
            rc, out, _ = run_cmd(args)
            return out.strip()[:5000] or "iptables 无规则"
        return "ERROR: 需要 ufw / firewalld / iptables"

    if IS_MAC:
        if has_cmd("pfctl"):
            rc, out, _ = run_cmd(["pfctl", "-s", "rules"], timeout=10)
            return out.strip()[:4000] or "pf 无规则"
        return "ERROR: 需要 pfctl"

    return "ERROR: 当前平台不支持"


# ═══════════════════════════════════════════════════════════════════════ #
# 写操作
# ═══════════════════════════════════════════════════════════════════════ #

def firewall_toggle(action: str) -> str:
    """action: on / off。"""
    a = (action or "").lower()
    if a not in ("on", "off"):
        return "ERROR: action 必须是 on 或 off"

    if IS_WINDOWS:
        state = "True" if a == "on" else "False"
        ps = (f"Set-NetFirewallProfile -Profile Domain,Public,Private "
              f"-Enabled {state}")
        rc, _, err = powershell(ps, timeout=20)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"防火墙已{'开启' if a == 'on' else '关闭'}"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, _, err = run_cmd(["ufw", "--force", a])
            if rc != 0:
                return f"ERROR: {err}（可能需要 root）"
            return f"ufw 已{'开启' if a == 'on' else '关闭'}"
        if has_cmd("firewall-cmd"):
            verb = "start" if a == "on" else "stop"
            rc, _, err = run_cmd(["systemctl", verb, "firewalld"])
            return f"firewalld 已{verb}" if rc == 0 else f"ERROR: {err}"
        return "ERROR: 需要 ufw 或 firewalld"

    if IS_MAC:
        fw = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        arg = "--setglobalstate=1" if a == "on" else "--setglobalstate=0"
        rc, out, err = run_cmd([fw, arg], timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要 sudo）"
        return f"防火墙已{'开启' if a == 'on' else '关闭'}（macOS）"

    return "ERROR: 当前平台不支持"


def firewall_port_allow(port: int, protocol: str = "tcp") -> str:
    try:
        p = int(port)
    except (TypeError, ValueError):
        return "ERROR: port 必须是整数"
    if not 1 <= p <= 65535:
        return "ERROR: port 超出范围（1-65535）"

    proto = (protocol or "tcp").lower()
    if proto not in ("tcp", "udp"):
        return "ERROR: protocol 必须是 tcp 或 udp"

    if IS_WINDOWS:
        name = f"OneCedric_allow_{proto}_{p}"
        ps = (f"New-NetFirewallRule -DisplayName '{name}' "
              f"-Direction Inbound -Action Allow -Protocol {proto.upper()} "
              f"-LocalPort {p}")
        rc, _, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"已放行入站 {proto.upper()} 端口 {p}（规则: {name}）"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, _, err = run_cmd(["ufw", "allow", f"{p}/{proto}"])
            return f"已放行端口 {p}/{proto}" if rc == 0 else f"ERROR: {err}（可能需要 root）"
        if has_cmd("firewall-cmd"):
            rc, _, err = run_cmd(["firewall-cmd", "--permanent",
                                  f"--add-port={p}/{proto}"])
            if rc == 0:
                run_cmd(["firewall-cmd", "--reload"])
                return f"已放行端口 {p}/{proto}"
            return f"ERROR: {err}"
        return "ERROR: 需要 ufw 或 firewalld"

    if IS_MAC:
        return "ERROR: macOS 请通过系统设置或 pfctl 手动配置"

    return "ERROR: 当前平台不支持"


def firewall_port_deny(port: int, protocol: str = "tcp") -> str:
    try:
        p = int(port)
    except (TypeError, ValueError):
        return "ERROR: port 必须是整数"
    proto = (protocol or "tcp").lower()

    if IS_WINDOWS:
        name = f"OneCedric_allow_{proto}_{p}"
        ps = (f"Remove-NetFirewallRule -DisplayName '{name}' "
              f"-ErrorAction SilentlyContinue")
        rc, _, err = powershell(ps, timeout=15)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"已移除规则 {name}（若存在）"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, _, err = run_cmd(["ufw", "delete", "allow", f"{p}/{proto}"])
            return f"已移除规则" if rc == 0 else f"ERROR: {err}"
        if has_cmd("firewall-cmd"):
            rc, _, err = run_cmd(["firewall-cmd", "--permanent",
                                  f"--remove-port={p}/{proto}"])
            if rc == 0:
                run_cmd(["firewall-cmd", "--reload"])
                return f"已移除端口规则 {p}/{proto}"
            return f"ERROR: {err}"
        return "ERROR: 需要 ufw 或 firewalld"

    return "ERROR: 当前平台不支持"


def firewall_port_check(port: int, protocol: str = "tcp") -> str:
    """检查端口是否已放行（只读）。"""
    try:
        p = int(port)
    except (TypeError, ValueError):
        return "ERROR: port 必须是整数"
    proto = (protocol or "tcp").lower()

    if IS_WINDOWS:
        name = f"OneCedric_allow_{proto}_{p}"
        ps = (f"Get-NetFirewallRule -DisplayName '{name}' "
              f"-ErrorAction SilentlyContinue | "
              f"Select-Object DisplayName,Enabled,Direction,Action | Format-List")
        rc, out, _ = powershell(ps, timeout=15)
        if out.strip():
            return f"已存在规则：\n{out.strip()}"
        return f"未找到端口 {p}/{proto} 的 OneCedric 规则"

    if IS_LINUX:
        if has_cmd("ufw"):
            rc, out, _ = run_cmd(["ufw", "status", "numbered"])
            needle = f"{p}/{proto}"
            matched = [l for l in out.splitlines() if needle in l.lower()]
            return "\n".join(matched) if matched else f"未找到 {needle} 规则"
        if has_cmd("firewall-cmd"):
            rc, out, _ = run_cmd(["firewall-cmd", "--list-ports"])
            needle = f"{p}/{proto}"
            return (f"已放行 {needle}" if needle in out else
                    f"未放行 {needle}\n现有端口: {out.strip()}")

    return "ERROR: 当前平台不支持"