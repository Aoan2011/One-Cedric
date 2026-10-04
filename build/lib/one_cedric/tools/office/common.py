"""办公文档共享工具。"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def check_file(p: Path, expected_exts: tuple = ()) -> str:
    """检查文件存在且扩展名匹配。返回错误信息或空字符串。"""
    if not p.exists():
        return f"ERROR: 文件不存在: {p.name}"
    if not p.is_file():
        return f"ERROR: 不是文件: {p.name}"
    if expected_exts and p.suffix.lower() not in expected_exts:
        exts = " / ".join(expected_exts)
        return f"ERROR: 期望 {exts} 格式，实际 {p.suffix}"
    return ""


def system_print(path: Path, printer: str = "") -> str:
    """系统级打印。"""
    if not path.exists():
        return f"ERROR: 文件不存在: {path.name}"

    if IS_WINDOWS:
        try:
            os.startfile(str(path), "print")
            return f"已发送到默认打印机: {path.name}"
        except OSError as exc:
            return f"ERROR: 打印失败: {exc}"

    if IS_MAC or IS_LINUX:
        if not shutil.which("lp"):
            return "ERROR: 未找到 lp 命令，无法打印"
        cmd = ["lp"]
        if printer:
            cmd += ["-d", printer]
        cmd.append(str(path))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"ERROR: 打印失败: {exc}"
        if r.returncode != 0:
            return f"ERROR: lp 失败: {r.stderr.strip()}"
        return f"已发送到打印机: {path.name}"

    return "ERROR: 当前平台不支持系统打印"


def win32_com_available() -> tuple[bool, str]:
    """检查 win32com 是否可用。"""
    if not IS_WINDOWS:
        return False, "win32com 仅 Windows 可用"
    try:
        import win32com.client  # noqa
        return True, ""
    except ImportError:
        return False, "需要 pywin32（pip install pywin32）"


def encrypt_with_msoffcrypto(src: Path, dst: Path, password: str) -> str:
    """用 msoffcrypto-tool 加密 Office 文件（跨平台）。"""
    try:
        import msoffcrypto
        from msoffcrypto.format.ooxml import OOXMLFile
    except ImportError:
        return "ERROR: 需要 msoffcrypto-tool（pip install msoffcrypto-tool）"

    try:
        with open(src, "rb") as fin:
            office = msoffcrypto.OfficeFile(fin)
            if hasattr(office, "encrypt"):
                with open(dst, "wb") as fout:
                    office.encrypt(password, fout)
                return f"已加密: {dst.name}"
            return "ERROR: 该文件类型不支持 msoffcrypto 加密"
    except Exception as exc:
        return f"ERROR: 加密失败: {exc}"


def decrypt_with_msoffcrypto(src: Path, dst: Path, password: str) -> str:
    """用 msoffcrypto-tool 解密 Office 文件。"""
    try:
        import msoffcrypto
    except ImportError:
        return "ERROR: 需要 msoffcrypto-tool（pip install msoffcrypto-tool）"

    try:
        with open(src, "rb") as fin:
            office = msoffcrypto.OfficeFile(fin)
            office.load_key(password=password)
            with open(dst, "wb") as fout:
                office.decrypt(fout)
        return f"已解密: {dst.name}"
    except Exception as exc:
        return f"ERROR: 解密失败: {exc}"


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def resolve_out_path(root: Path, path: str) -> tuple[Path | None, str]:
    """解析输出路径并确保在沙箱内（不要求文件已存在）。"""
    from ..sandbox import _resolve_path
    return _resolve_path(root, path)