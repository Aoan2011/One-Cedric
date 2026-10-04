"""平台检测与通用命令执行。"""
from __future__ import annotations

import platform
import shutil
import subprocess

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def run_cmd(args: list[str], timeout: int = 15,
            shell: bool = False) -> tuple[int, str, str]:
    """执行命令，返回 (rc, stdout, stderr)。"""
    try:
        r = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, shell=shell,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return 127, "", f"命令不存在: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"命令超时（{timeout}s）"
    except OSError as exc:
        return 1, "", str(exc)


def powershell(script: str, timeout: int = 15) -> tuple[int, str, str]:
    """执行 PowerShell 脚本（仅 Windows）。"""
    if not IS_WINDOWS:
        return 1, "", "PowerShell 仅 Windows 可用"
    if not has_cmd("powershell"):
        return 127, "", "找不到 powershell"
    return run_cmd(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )


def unsupported(feature: str) -> str:
    return f"ERROR: 当前平台（{platform.system()}）不支持 {feature}"