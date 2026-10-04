"""打印机管理。"""
from __future__ import annotations

from pathlib import Path

from ._platform import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    has_cmd, run_cmd, powershell, unsupported,
)


def _win_list() -> str:
    ps = ("Get-Printer -ErrorAction SilentlyContinue | "
          "Select-Object Name,DriverName,PortName,PrinterStatus | "
          "Format-Table -AutoSize")
    rc, out, err = powershell(ps)
    if rc != 0:
        return f"ERROR: {err}"
    if not out.strip():
        return "未找到打印机"
    return "打印机列表:\n" + out.strip()


def _win_default() -> str:
    ps = ("(Get-CimInstance -ClassName Win32_Printer "
          "-Filter 'Default=TRUE').Name")
    rc, out, err = powershell(ps)
    if rc != 0:
        return f"ERROR: {err}"
    if not out.strip():
        return "未设置默认打印机"
    return f"默认打印机: {out.strip()}"


def _unix_list() -> str:
    if not has_cmd("lpstat"):
        return unsupported("打印机（需 CUPS / lpstat）")
    rc, out, err = run_cmd(["lpstat", "-p", "-d"])
    if rc != 0:
        return f"ERROR: {err}"
    return "打印机:\n" + out.strip() if out.strip() else "未找到打印机"


def _unix_default() -> str:
    if not has_cmd("lpstat"):
        return unsupported("打印机")
    rc, out, err = run_cmd(["lpstat", "-d"])
    if rc != 0:
        return f"ERROR: {err}"
    return out.strip() if out.strip() else "未设置默认打印机"


def printer_list() -> str:
    if IS_WINDOWS:
        return _win_list()
    if IS_MAC or IS_LINUX:
        return _unix_list()
    return unsupported("打印机")


def printer_default() -> str:
    if IS_WINDOWS:
        return _win_default()
    if IS_MAC or IS_LINUX:
        return _unix_default()
    return unsupported("默认打印机")


def printer_print(path: Path, printer: str = "") -> str:
    if not path.exists():
        return f"ERROR: 文件不存在: {path.name}"
    if IS_WINDOWS:
        import os
        try:
            os.startfile(str(path), "print")
            return f"已发送到默认打印机: {path.name}"
        except OSError as exc:
            return f"ERROR: {exc}"
    if IS_MAC or IS_LINUX:
        if not has_cmd("lp"):
            return unsupported("打印")
        cmd = ["lp"]
        if printer:
            cmd += ["-d", printer]
        cmd.append(str(path))
        rc, _, err = run_cmd(cmd, timeout=30)
        if rc != 0:
            return f"ERROR: {err}"
        return f"已发送到打印机: {path.name}"
    return unsupported("打印")