"""系统服务管理（Windows: Get-Service；Linux: systemctl；macOS: launchctl）。"""
from __future__ import annotations

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


def services_list(filter: str = "", limit: int = 40) -> str:
    try:
        n = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        n = 40

    if IS_WINDOWS:
        ps = "Get-Service | Where-Object {$_.Status -eq 'Running'} | " \
             "Select-Object Status,Name,DisplayName | Format-Table -AutoSize"
        rc, out, err = powershell(ps, timeout=20)
        if rc != 0:
            return f"ERROR: {err}"
        lines = out.strip().splitlines()
        if filter:
            lines = [lines[0]] + [l for l in lines[1:] if filter.lower() in l.lower()]
        return "\n".join(lines[:n + 3])

    if IS_LINUX:
        if not has_cmd("systemctl"):
            return "ERROR: 需要 systemd（systemctl）"
        rc, out, err = run_cmd(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-pager", "--no-legend"], timeout=15)
        if rc != 0:
            return f"ERROR: {err}"
        lines = [l.strip() for l in out.strip().splitlines()]
        if filter:
            lines = [l for l in lines if filter.lower() in l.lower()]
        return "\n".join(lines[:n])

    if IS_MAC:
        rc, out, err = run_cmd(["launchctl", "list"], timeout=15)
        return out.strip()[:5000] if rc == 0 else f"ERROR: {err}"

    return "ERROR: 当前平台不支持"


def services_status(name: str) -> str:
    if not name:
        return "ERROR: name 不能为空"
    if IS_WINDOWS:
        rc, out, err = powershell(
            f"Get-Service -Name '{name}' | Select-Object Status,Name,DisplayName,"
            f"StartType | Format-List", timeout=15)
        return out.strip() or f"ERROR: {err or '未找到服务'}"
    if IS_LINUX:
        rc, out, err = run_cmd(["systemctl", "status", name, "--no-pager"],
                               timeout=15)
        return out.strip()[:3000] if out else f"ERROR: {err}"
    if IS_MAC:
        rc, out, _ = run_cmd(["launchctl", "list", name], timeout=15)
        return out.strip() if rc == 0 else f"未找到服务 {name}"
    return "ERROR: 当前平台不支持"


def services_action(name: str, action: str) -> str:
    """action: start / stop / restart / enable / disable。"""
    if not name:
        return "ERROR: name 不能为空"
    a = (action or "").lower()
    if a not in ("start", "stop", "restart", "enable", "disable"):
        return f"ERROR: action 必须是 start/stop/restart/enable/disable"

    if IS_WINDOWS:
        cmd_map = {
            "start": f"Start-Service -Name '{name}'",
            "stop": f"Stop-Service -Name '{name}' -Force",
            "restart": f"Restart-Service -Name '{name}' -Force",
            "enable": f"Set-Service -Name '{name}' -StartupType Automatic",
            "disable": f"Set-Service -Name '{name}' -StartupType Disabled",
        }
        rc, out, err = powershell(cmd_map[a], timeout=30)
        if rc != 0:
            return f"ERROR: {err}（可能需要管理员权限）"
        return f"已{a}服务 {name}"

    if IS_LINUX:
        cmd_map = {
            "start": ["systemctl", "start", name],
            "stop": ["systemctl", "stop", name],
            "restart": ["systemctl", "restart", name],
            "enable": ["systemctl", "enable", name],
            "disable": ["systemctl", "disable", name],
        }
        rc, out, err = run_cmd(cmd_map[a], timeout=30)
        if rc != 0:
            return f"ERROR: {err}（可能需要 root）"
        return f"已{a} {name}"

    if IS_MAC:
        if not has_cmd("brew"):
            return "ERROR: macOS 服务管理需要 brew services"
        rc, out, err = run_cmd(["brew", "services", a, name], timeout=30)
        return f"已{a} {name}" if rc == 0 else f"ERROR: {err}"

    return "ERROR: 当前平台不支持"


# ── 进程管理 ──

def process_kill(pid=None, name: str = "", force: bool = False) -> str:
    if not pid and not name:
        return "ERROR: 需要 pid 或 name"

    if IS_WINDOWS:
        if pid:
            args = ["taskkill", "/PID", str(pid)]
        else:
            args = ["taskkill", "/IM", f"{name}.exe"]
        if force:
            args.append("/F")
        try:
            import subprocess
            r = subprocess.run(args, capture_output=True, text=True, timeout=15)
            return r.stdout.strip() or r.stderr.strip()
        except Exception as exc:
            return f"ERROR: {exc}"

    # Unix
    if pid:
        rc, out, err = run_cmd(["kill", "-9" if force else "-15", str(pid)])
    else:
        rc, out, err = run_cmd(["pkill", "-9" if force else "-15", name])
    return "已发送信号" if rc == 0 else f"ERROR: {err}"


def process_priority(pid=None, name: str = "", nice: int = 0) -> str:
    try:
        n = max(-20, min(int(nice), 19))
    except (TypeError, ValueError):
        return "ERROR: nice 必须是 -20 到 19"

    if IS_WINDOWS:
        if pid:
            ps = f"(Get-Process -Id {pid}).PriorityClass = 'Normal'"
        else:
            ps = f"Get-Process -Name '{name}' | ForEach-Object {{ $_.PriorityClass = 'Normal' }}"
        rc, _, err = powershell(ps)
        return "已调整（Windows 只支持粗粒度）" if rc == 0 else f"ERROR: {err}"

    if IS_LINUX or IS_MAC:
        args = ["renice", str(n)]
        if pid:
            args += ["-p", str(pid)]
        else:
            args += ["-n", name]
        rc, out, err = run_cmd(args)
        return f"已调整 nice={n}" if rc == 0 else f"ERROR: {err}"

    return "ERROR: 当前平台不支持"