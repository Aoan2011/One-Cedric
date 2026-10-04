"""检查系统更新。"""
from __future__ import annotations

from ._platform import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    has_cmd, run_cmd, powershell, unsupported,
)


def _win_check() -> str:
    if has_cmd("winget"):
        rc, out, err = run_cmd(["winget", "upgrade"], timeout=60)
        if rc == 0:
            low = out.lower()
            if not out.strip() or "no installed package" in low \
                    or "没有可用" in out:
                return "系统更新: 无可用更新（winget）"
            return "可用更新（winget）:\n" + out.strip()[-3000:]

    ps = ("(New-Object -ComObject Microsoft.Update.Session)"
          ".CreateUpdateSearcher().Search('IsInstalled=0').Updates | "
          "Select-Object Title | Format-Table -AutoSize")
    rc, out, err = powershell(ps, timeout=90)
    if rc == 0 and out.strip():
        return "可用更新（Windows Update）:\n" + out.strip()
    return "未检测到更新工具（需 winget 或 Windows Update）"


def _mac_check() -> str:
    if not has_cmd("softwareupdate"):
        return unsupported("系统更新检查")
    rc, out, err = run_cmd(["softwareupdate", "-l"], timeout=60)
    if rc != 0:
        return f"ERROR: {err}"
    if "No new software available" in out:
        return "系统更新: 无可用更新"
    return "可用更新:\n" + out.strip()


def _linux_check() -> str:
    if has_cmd("apt"):
        rc, out, _ = run_cmd(["apt", "list", "--upgradable"], timeout=60)
        if rc == 0:
            lines = [l for l in out.splitlines()
                     if "/" in l and "upgradable" not in l.lower()]
            if not lines:
                return "系统更新: 无可用更新（apt）"
            return f"可用更新（{len(lines)} 个，前 30）:\n" + "\n".join(lines[:30])
    if has_cmd("dnf"):
        rc, out, _ = run_cmd(["dnf", "check-update"], timeout=60)
        if rc == 0:
            return "系统更新: 无可用更新（dnf）"
        if rc == 100 and out.strip():
            return "可用更新（dnf）:\n" + out.strip()[:3000]
    if has_cmd("pacman"):
        rc, out, _ = run_cmd(["pacman", "-Qu"], timeout=30)
        if rc == 0:
            if not out.strip():
                return "系统更新: 无可用更新（pacman）"
            return "可用更新（pacman）:\n" + out.strip()[:3000]
    return unsupported("系统更新检查")


def check_update() -> str:
    if IS_WINDOWS:
        return _win_check()
    if IS_MAC:
        return _mac_check()
    if IS_LINUX:
        return _linux_check()
    return unsupported("系统更新")