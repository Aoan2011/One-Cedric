"""系统级代理持久化。

Windows: HKCU 注册表 + InternetSetOption 通知刷新
Linux:   GNOME gsettings
macOS:   networksetup
"""
from __future__ import annotations

from urllib.parse import urlparse

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


# ═══════════════════════════════════════════════════════════════════════ #
# 只读
# ═══════════════════════════════════════════════════════════════════════ #

def system_proxy_get() -> str:
    if IS_WINDOWS:
        ps = ("$p = Get-ItemProperty -Path "
              "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\"
              "Internet Settings' -ErrorAction SilentlyContinue; "
              "if ($p) { "
              "Write-Output ('Enabled: ' + $p.ProxyEnable); "
              "Write-Output ('Server: ' + $p.ProxyServer); "
              "Write-Output ('Override: ' + $p.ProxyOverride) }")
        rc, out, err = powershell(ps, timeout=10)
        if rc != 0:
            return f"ERROR: {err}"
        return out.strip() or "（无配置）"

    if IS_LINUX:
        if not has_cmd("gsettings"):
            return "ERROR: 需要 gsettings（GNOME 环境）"
        rc, mode, _ = run_cmd(["gsettings", "get",
                               "org.gnome.system.proxy", "mode"])
        mode = mode.strip()
        lines = [f"模式: {mode}"]
        if mode in ("'manual'", "'auto'"):
            for schema in ("org.gnome.system.proxy.http",
                           "org.gnome.system.proxy.https",
                           "org.gnome.system.proxy.socks"):
                rc1, h, _ = run_cmd(["gsettings", "get", schema, "host"])
                rc2, p, _ = run_cmd(["gsettings", "get", schema, "port"])
                h, p = h.strip(), p.strip()
                if h and h != "''":
                    lines.append(f"  {schema.split('.')[-1]}: {h}:{p}")
            rc3, ih, _ = run_cmd(["gsettings", "get",
                                  "org.gnome.system.proxy", "ignore-hosts"])
            if ih.strip() not in ("@as []", "[]", ""):
                lines.append(f"  ignore: {ih.strip()}")
        return "\n".join(lines)

    if IS_MAC:
        lines = []
        for svc in ("Wi-Fi", "Ethernet", "Thunderbolt Ethernet"):
            for proto in ("webproxy", "securewebproxy", "socksfirewallproxy"):
                rc, out, _ = run_cmd(["networksetup", f"-get{proto}", svc])
                if rc == 0 and "Enabled: Yes" in out:
                    lines.append(f"[{svc}] {proto}:")
                    lines.append("  " + out.strip().replace("\n", "\n  "))
        return "\n".join(lines) if lines else "未启用任何系统代理"

    return "ERROR: 当前平台不支持"


# ═══════════════════════════════════════════════════════════════════════ #
# 写操作
# ═══════════════════════════════════════════════════════════════════════ #

def system_proxy_set(url: str, bypass: str = "") -> str:
    """设置系统级 HTTP/HTTPS/SOCKS 代理。url 为空则清除。"""
    if not url:
        return system_proxy_clear()

    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname or ""
    port = parsed.port
    scheme = parsed.scheme or "http"
    if not host:
        return f"ERROR: 无法解析代理 URL: {url}"
    if not port:
        port = {"http": 8080, "https": 8080, "socks": 1080,
                "socks5": 1080}.get(scheme, 8080)

    if IS_WINDOWS:
        bypass_ps = (f"Set-ItemProperty -Path $path -Name ProxyOverride "
                     f"-Value '{bypass}'; ") if bypass else ""
        ps = (
            "$path = 'HKCU:\\Software\\Microsoft\\Windows\\"
            "CurrentVersion\\Internet Settings'; "
            f"Set-ItemProperty -Path $path -Name ProxyServer "
            f"-Value '{host}:{port}'; "
            "Set-ItemProperty -Path $path -Name ProxyEnable -Value 1; "
            + bypass_ps
            + "Write-Output 'OK'"
        )
        rc, _, err = powershell(ps, timeout=10)
        if rc != 0:
            return f"ERROR: {err}"
        _win_refresh_proxy()
        return (f"系统代理已设置 → {host}:{port}"
                + (f"  bypass: {bypass}" if bypass else ""))

    if IS_LINUX:
        if not has_cmd("gsettings"):
            return "ERROR: 需要 gsettings"
        cmds = [
            ["gsettings", "set", "org.gnome.system.proxy", "mode", "'manual'"],
            ["gsettings", "set", "org.gnome.system.proxy.http", "host", f"'{host}'"],
            ["gsettings", "set", "org.gnome.system.proxy.http", "port", str(port)],
            ["gsettings", "set", "org.gnome.system.proxy.https", "host", f"'{host}'"],
            ["gsettings", "set", "org.gnome.system.proxy.https", "port", str(port)],
            ["gsettings", "set", "org.gnome.system.proxy.socks", "host", f"'{host}'"],
            ["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(port)],
        ]
        for c in cmds:
            run_cmd(c)
        if bypass:
            hosts = [h.strip() for h in bypass.split(",") if h.strip()]
            quoted = "[" + ",".join(f"'{h}'" for h in hosts) + "]"
            run_cmd(["gsettings", "set", "org.gnome.system.proxy",
                     "ignore-hosts", quoted])
        return (f"系统代理已设置 → {host}:{port}"
                + (f"  bypass: {bypass}" if bypass else ""))

    if IS_MAC:
        svc = "Wi-Fi"
        rc1, _, e1 = run_cmd(["networksetup", "-setwebproxy",
                              svc, host, str(port)])
        rc2, _, e2 = run_cmd(["networksetup", "-setsecurewebproxy",
                              svc, host, str(port)])
        if rc1 != 0 or rc2 != 0:
            return (f"ERROR: {e1 or e2}（可能需要 sudo）")
        if bypass:
            bypass_list = [b.strip() for b in bypass.split(",") if b.strip()]
            run_cmd(["networksetup", "-setproxybypassdomains", svc] + bypass_list)
        return (f"系统代理已设置 → {host}:{port}（Wi-Fi）"
                + (f"  bypass: {bypass}" if bypass else ""))

    return "ERROR: 当前平台不支持"


def system_proxy_clear() -> str:
    if IS_WINDOWS:
        ps = ("$path = 'HKCU:\\Software\\Microsoft\\Windows\\"
              "CurrentVersion\\Internet Settings'; "
              "Set-ItemProperty -Path $path -Name ProxyEnable -Value 0; "
              "Remove-ItemProperty -Path $path -Name ProxyServer "
              "-ErrorAction SilentlyContinue; "
              "Remove-ItemProperty -Path $path -Name ProxyOverride "
              "-ErrorAction SilentlyContinue; "
              "Write-Output 'OK'")
        rc, _, err = powershell(ps, timeout=10)
        if rc != 0:
            return f"ERROR: {err}"
        _win_refresh_proxy()
        return "系统代理已清除"

    if IS_LINUX:
        if not has_cmd("gsettings"):
            return "ERROR: 需要 gsettings"
        run_cmd(["gsettings", "set", "org.gnome.system.proxy", "mode", "'none'"])
        return "系统代理已清除"

    if IS_MAC:
        svc = "Wi-Fi"
        run_cmd(["networksetup", "-setwebproxystate", svc, "off"])
        run_cmd(["networksetup", "-setsecurewebproxystate", svc, "off"])
        run_cmd(["networksetup", "-setsocksfirewallproxystate", svc, "off"])
        return "系统代理已清除（Wi-Fi）"

    return "ERROR: 当前平台不支持"


def _win_refresh_proxy() -> None:
    """通知 Windows 立即刷新代理配置（InternetSetOption）。"""
    ps = (
        "Add-Type -Namespace Win -Name Inet -MemberDefinition "
        "'[System.Runtime.InteropServices.DllImport(\"wininet.dll\")] "
        "public static extern bool InternetSetOption("
        "System.IntPtr h, int opt, System.IntPtr buf, int len);'; "
        "[Win.Inet]::InternetSetOption([System.IntPtr]::Zero, 39, "
        "[System.IntPtr]::Zero, 0) | Out-Null; "
        "[Win.Inet]::InternetSetOption([System.IntPtr]::Zero, 37, "
        "[System.IntPtr]::Zero, 0) | Out-Null"
    )
    try:
        powershell(ps, timeout=5)
    except Exception:
        pass