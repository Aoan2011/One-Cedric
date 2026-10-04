"""电源管理：关机/重启/睡眠/休眠/锁屏/注销。危险操作，全部需确认。"""
from __future__ import annotations

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, powershell


def _windows_shutdown(flag: str, timeout: int = 0) -> str:
    try:
        r = subprocess.run(["shutdown", flag, "/t", str(timeout)],
                           capture_output=True, text=True, timeout=10)
    except Exception as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr or r.stdout}"
    return "已发送系统命令"


import subprocess


def power_action(action: str, delay: int = 0) -> str:
    a = (action or "").lower()
    if a not in ("shutdown", "reboot", "sleep", "hibernate", "lock", "logout"):
        return f"ERROR: 未知动作: {a}"

    if IS_WINDOWS:
        if a == "shutdown":
            return _windows_shutdown("/s", delay)
        if a == "reboot":
            return _windows_shutdown("/r", delay)
        if a == "sleep":
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Add-Type -AssemblyName System.Windows.Forms; "
                     "[System.Windows.Forms.Application]::SetSuspendState("
                     "'Suspend',$false,$false)"],
                    capture_output=True, text=True, timeout=15)
                return "已进入睡眠" if r.returncode == 0 else f"ERROR: {r.stderr}"
            except Exception as exc:
                return f"ERROR: {exc}"
        if a == "hibernate":
            try:
                r = subprocess.run(["shutdown", "/h"],
                                   capture_output=True, text=True, timeout=10)
                return "已休眠" if r.returncode == 0 else f"ERROR: {r.stderr}"
            except Exception as exc:
                return f"ERROR: {exc}"
        if a == "lock":
            try:
                r = subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"],
                                   capture_output=True, text=True, timeout=10)
                return "已锁屏" if r.returncode == 0 else f"ERROR: 锁屏失败"
            except Exception as exc:
                return f"ERROR: {exc}"
        if a == "logout":
            return "ERROR: Windows 注销需要交互，请手动执行"

    if IS_LINUX:
        cmd_map = {
            "shutdown": ["systemctl", "poweroff"],
            "reboot": ["systemctl", "reboot"],
            "sleep": ["systemctl", "suspend"],
            "hibernate": ["systemctl", "hibernate"],
            "lock": ["loginctl", "lock-session"],
            "logout": ["loginctl", "terminate-user", "$USER"],
        }
        if a == "shutdown" and has_cmd("shutdown"):
            args = ["shutdown", "-h", "now"] if delay == 0 else \
                   ["shutdown", "-h", f"+{delay}"]
            rc, _, err = run_cmd(args)
            return "已发送关机命令" if rc == 0 else f"ERROR: {err}"
        cmd = cmd_map.get(a)
        if not cmd:
            return f"ERROR: 不支持: {a}"
        rc, _, err = run_cmd(cmd)
        return f"已执行 {a}" if rc == 0 else f"ERROR: {err}（可能需要 sudo/root）"

    if IS_MAC:
        if a == "shutdown":
            rc, _, err = run_cmd(["osascript", "-e",
                                  'tell app "System Events" to shut down'])
        elif a == "reboot":
            rc, _, err = run_cmd(["osascript", "-e",
                                  'tell app "System Events" to restart'])
        elif a == "sleep":
            rc, _, err = run_cmd(["pmset", "sleepnow"])
        elif a == "lock":
            rc, _, err = run_cmd(["/System/Library/CoreServices/Menu Extras/"
                                  "User.menu/Contents/Resources/CGSession",
                                  "-suspend"])
        else:
            return f"ERROR: macOS 不支持: {a}"
        return f"已执行 {a}" if rc == 0 else f"ERROR: {err}"

    return "ERROR: 当前平台不支持"


def power_plan(action: str = "list", plan: str = "") -> str:
    """电源计划（Windows: powercfg；Linux: cpufreq）。"""
    if IS_WINDOWS:
        if action == "list":
            rc, out, err = powershell("powercfg /L")
            return out.strip() or f"ERROR: {err}"
        if action == "set":
            if not plan:
                return "ERROR: set 需要 plan（GUID 或别名 SCHEME_BALANCED 等）"
            rc, out, err = powershell(f"powercfg /S {plan}")
            return f"已切换到 {plan}" if rc == 0 else f"ERROR: {err}"
        return "ERROR: action 必须是 list 或 set"

    if IS_LINUX:
        if has_cmd("cpupower"):
            if action == "list":
                rc, out, err = run_cmd(["cpupower", "frequency-info"])
                return out.strip()
            if action == "set":
                rc, out, err = run_cmd(["cpupower", "frequency-set", "-g", plan])
                return f"已设置 governor={plan}" if rc == 0 else f"ERROR: {err}"
        return "ERROR: 需要 cpupower（Linux）"

    return "ERROR: 当前平台不支持"


def power_battery() -> str:
    if IS_LINUX:
        try:
            from pathlib import Path
            bat = Path("/sys/class/power_supply")
            if not bat.exists():
                return "未检测到电池"
            lines = []
            for d in bat.iterdir():
                if not (d / "type").exists():
                    continue
                typ = (d / "type").read_text().strip()
                if typ != "Battery":
                    continue
                cap = (d / "capacity").read_text().strip() if (d / "capacity").exists() else "?"
                status = (d / "status").read_text().strip() if (d / "status").exists() else "?"
                lines.append(f"{d.name}: {cap}%  {status}")
            return "\n".join(lines) if lines else "未检测到电池"
        except Exception as exc:
            return f"ERROR: {exc}"

    if IS_MAC:
        rc, out, _ = run_cmd(["pmset", "-g", "batt"])
        return out.strip() or "读取失败"

    if IS_WINDOWS:
        rc, out, err = powershell(
            "Get-CimInstance Win32_Battery | "
            "Select-Object EstimatedChargeRemaining,BatteryStatus | Format-Table"
        )
        return out.strip() or "未检测到电池"

    return "ERROR: 当前平台不支持"