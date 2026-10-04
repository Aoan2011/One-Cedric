"""杂项：时区/时间同步/通知/hosts/代理/DNS/显示器/温度。"""
from __future__ import annotations

import re
from pathlib import Path

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


def timezone_get() -> str:
    if IS_WINDOWS:
        rc, out, _ = run_cmd(["tzutil", "/g"])
        return f"时区: {out.strip()}" if rc == 0 else "读取失败"
    if IS_MAC or IS_LINUX:
        rc, out, _ = run_cmd(["timedatectl"]) if has_cmd("timedatectl") else (1, "", "")
        if rc == 0:
            for line in out.splitlines():
                if "Time zone" in line:
                    return line.strip()
        try:
            tz = Path("/etc/timezone").read_text().strip()
            return f"时区: {tz}"
        except Exception:
            return "无法读取时区"
    return "ERROR: 当前平台不支持"


def timezone_set(tz: str) -> str:
    if not tz:
        return "ERROR: 需要 tz（如 Asia/Shanghai）"
    if IS_WINDOWS:
        rc, _, err = run_cmd(["tzutil", "/s", tz])
        return f"已设置时区: {tz}" if rc == 0 else f"ERROR: {err}（可能需要管理员）"
    if IS_LINUX:
        if not has_cmd("timedatectl"):
            return "ERROR: 需要 timedatectl"
        rc, _, err = run_cmd(["timedatectl", "set-timezone", tz])
        return f"已设置时区: {tz}" if rc == 0 else f"ERROR: {err}（可能需要 root）"
    if IS_MAC:
        rc, _, err = run_cmd(["systemsetup", "-settimezone", tz])
        return f"已设置时区: {tz}" if rc == 0 else f"ERROR: {err}（可能需要 sudo）"
    return "ERROR: 当前平台不支持"


def time_sync(force: bool = False) -> str:
    if IS_WINDOWS:
        if force:
            rc, _, err = powershell("w32tm /resync")
            return "已同步" if rc == 0 else f"ERROR: {err}"
        rc, out, _ = run_cmd(["w32tm", "/query", "/status"])
        return out.strip()[:1500]
    if IS_LINUX:
        if has_cmd("timedatectl"):
            if force:
                rc, _, err = run_cmd(["timedatectl", "set-ntp", "true"])
                return "已触发同步" if rc == 0 else f"ERROR: {err}"
            rc, out, _ = run_cmd(["timedatectl"])
            return out.strip()
    if IS_MAC:
        rc, _, err = run_cmd(["sntp", "-sS", "time.apple.com"]) if force \
            else (0, "", "")
        if force:
            return "已同步" if rc == 0 else f"ERROR: {err}"
        rc, out, _ = run_cmd(["systemsetup", "-getusingnetworktime"])
        return out.strip()
    return "ERROR: 当前平台不支持"


def notify(title: str = "One Cedric", body: str = "", timeout: int = 5) -> str:
    """发送系统通知。"""
    if not body:
        body = title
        title = "One Cedric"

    if IS_WINDOWS:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f"$n.ShowBalloonTip({int(timeout) * 1000}, "
            f"'{_esc(title)}', '{_esc(body)}', "
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            f"Start-Sleep -Seconds {int(timeout)}; "
            "$n.Dispose()"
        )
        rc, _, err = powershell(ps, timeout=timeout + 5)
        return "已发送通知" if rc == 0 else f"ERROR: {err}"

    if IS_MAC:
        script = f'display notification "{_esc(body)}" with title "{_esc(title)}"'
        rc, _, err = run_cmd(["osascript", "-e", script])
        return "已发送通知" if rc == 0 else f"ERROR: {err}"

    if IS_LINUX:
        if has_cmd("notify-send"):
            rc, _, err = run_cmd(["notify-send", title, body])
            return "已发送通知" if rc == 0 else f"ERROR: {err}"
        return "ERROR: 需要 notify-send（libnotify）"

    return "ERROR: 当前平台不支持"


def _esc(s: str) -> str:
    return (s or "").replace("'", "''").replace('"', '\\"')


def hosts_show() -> str:
    hosts = _hosts_path()
    if not hosts.exists():
        return "ERROR: hosts 文件不存在"
    try:
        content = hosts.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR: {exc}"

    # 解析为条目
    entries = []
    for line in content.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            entries.append((parts[0], parts[1:]))

    lines = [f"文件: {hosts}", f"条目: {len(entries)}", ""]
    for ip, names in entries:
        lines.append(f"  {ip:<20} {' '.join(names)}")
    return "\n".join(lines)


def _hosts_path() -> Path:
    if IS_WINDOWS:
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")


def proxy_get() -> str:
    if IS_WINDOWS:
        rc, out, _ = powershell(
            "Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\"
            "CurrentVersion\\Internet Settings' | "
            "Select-Object ProxyEnable,ProxyServer,ProxyOverride"
        )
        return out.strip()
    if IS_MAC or IS_LINUX:
        import os
        keys = ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "no_proxy", "NO_PROXY", "all_proxy"]
        lines = []
        for k in keys:
            v = os.environ.get(k)
            if v:
                lines.append(f"{k}={v}")
        return "\n".join(lines) if lines else "未设置环境变量代理"
    return "ERROR: 当前平台不支持"


def proxy_set(url: str) -> str:
    """设置 http_proxy/https_proxy 环境变量（仅当前进程）。"""
    import os
    if not url:
        for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            os.environ.pop(k, None)
        return "已清除代理环境变量"
    for k in ("http_proxy", "https_proxy"):
        os.environ[k] = url
    return f"已设置 http_proxy/https_proxy={url}（仅当前进程）"


def monitors_list() -> str:
    """列出显示器信息。"""
    if IS_WINDOWS:
        ps = ("Add-Type -AssemblyName System.Windows.Forms; "
              "[System.Windows.Forms.Screen]::AllScreens | "
              "Select-Object DeviceName,Bounds,Primary | Format-List")
        rc, out, err = powershell(ps)
        return out.strip() or f"ERROR: {err}"
    if IS_LINUX:
        if has_cmd("xrandr"):
            rc, out, _ = run_cmd(["xrandr", "--listmonitors"])
            return out.strip()
        if has_cmd("wlr-randr"):
            rc, out, _ = run_cmd(["wlr-randr"])
            return out.strip()
        return "ERROR: 需要 xrandr 或 wlr-randr"
    if IS_MAC:
        rc, out, _ = run_cmd(["system_profiler", "SPDisplaysDataType"], timeout=20)
        return out.strip()[:2000]
    return "ERROR: 当前平台不支持"


def temperature() -> str:
    """读取 CPU 温度（尽力而为）。"""
    if IS_LINUX:
        try:
            from pathlib import Path
            tz = Path("/sys/class/thermal")
            if tz.exists():
                lines = []
                for d in sorted(tz.glob("thermal_zone*")):
                    try:
                        temp = int((d / "temp").read_text().strip()) / 1000
                        typ = (d / "type").read_text().strip() if (d / "type").exists() else d.name
                        lines.append(f"{typ}: {temp:.1f}°C")
                    except Exception:
                        continue
                if lines:
                    return "\n".join(lines)
        except Exception:
            pass
        if has_cmd("sensors"):
            rc, out, _ = run_cmd(["sensors"])
            return out.strip()[:2000]
        return "ERROR: 无法读取温度（需要 lm-sensors）"

    if IS_MAC:
        if has_cmd("osx-cpu-temp"):
            rc, out, _ = run_cmd(["osx-cpu-temp"])
            return out.strip()
        return "ERROR: 需要 osx-cpu-temp（brew install osx-cpu-temp）"

    if IS_WINDOWS:
        ps = ("Get-CimInstance -Namespace root/WMI "
              "-ClassName MSAcpi_ThermalZoneTemperature "
              "-ErrorAction SilentlyContinue | "
              "ForEach-Object { [math]::Round(($_.CurrentTemperature / 10 - 273.15), 1) }")
        rc, out, err = powershell(ps)
        return out.strip() or "未检测到温度传感器（可能需管理员权限）"

    return "ERROR: 当前平台不支持"


def clipboard_history_check() -> str:
    """检查各平台剪贴板历史工具。"""
    info = []
    if IS_WINDOWS:
        info.append("Windows 剪贴板历史：Win+V")
        info.append("（需要在「设置 → 系统 → 剪贴板」中开启）")
    elif IS_MAC:
        info.append("macOS 剪贴板历史需第三方工具，如 Maccy / Paste")
    elif IS_LINUX:
        if has_cmd("cliphist"):
            info.append("检测到 cliphist（Wayland）")
        elif has_cmd("greenclip"):
            info.append("检测到 greenclip（X11）")
        else:
            info.append("推荐安装 cliphist（Wayland）或 greenclip（X11）")
    return "\n".join(info)