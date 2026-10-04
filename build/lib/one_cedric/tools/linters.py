"""代码检查工具：ruff / mypy / black / eslint。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list, cwd: Path, timeout: int = 60):
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"超时（>{timeout}s）"
    except OSError as exc:
        return -1, "", f"执行失败: {exc}"


def _truncate(text: str, max_chars: int = 15000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (截断，原始 {len(text)} 字符)"


def ruff_check(path: str = ".", select: str = "",
               ignore: str = "", max_results=None,
               root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    if not _which("ruff"):
        return ("ERROR: 未找到 ruff。\n"
                "安装：pip install ruff")
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"
    cmd = ["ruff", "check"]
    if select:
        cmd += ["--select", select]
    if ignore:
        cmd += ["--ignore", ignore]
    cmd += ["--output-format", "concise"]
    cmd.append(str(p))
    rc, out, errout = _run(cmd, root, timeout=60)
    if rc == 0 and not out.strip():
        return f"ruff: 无问题 ✓  ({path})"
    max_r = _as_int(max_results, 100)
    if max_r <= 0:
        max_r = 100
    lines = out.splitlines()
    if len(lines) > max_r:
        lines = lines[:max_r] + [
            f"... (还有 {len(lines) - max_r} 行)"]
    header = f"ruff: {path}  (rc={rc})"
    if errout.strip():
        header += f"\n[stderr]\n{_truncate(errout, 2000)}"
    return header + "\n" + _truncate("\n".join(lines))


def mypy_check(path: str = ".", strict: bool = False,
               max_results=None,
               root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    if not _which("mypy"):
        return ("ERROR: 未找到 mypy。\n"
                "安装：pip install mypy")
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"
    cmd = ["mypy"]
    if strict:
        cmd.append("--strict")
    cmd += ["--no-color-output", "--no-error-summary"]
    cmd.append(str(p))
    rc, out, errout = _run(cmd, root, timeout=120)
    if rc == 0 and not out.strip():
        return f"mypy: 无类型错误 ✓  ({path})"
    max_r = _as_int(max_results, 100)
    if max_r <= 0:
        max_r = 100
    lines = out.splitlines()
    if len(lines) > max_r:
        lines = lines[:max_r] + [
            f"... (还有 {len(lines) - max_r} 行)"]
    header = f"mypy: {path}  (rc={rc})"
    if errout.strip():
        header += f"\n[stderr]\n{_truncate(errout, 2000)}"
    return header + "\n" + _truncate("\n".join(lines))


def black_check(path: str = ".", root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    if not _which("black"):
        return ("ERROR: 未找到 black。\n"
                "安装：pip install black")
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"
    cmd = ["black", "--check", "--diff", str(p)]
    rc, out, errout = _run(cmd, root, timeout=60)
    if rc == 0 and not out.strip():
        return f"black: 格式合规 ✓  ({path})"
    header = f"black: {path}  (rc={rc})"
    if errout.strip():
        header += f"\n[stderr]\n{_truncate(errout, 2000)}"
    return header + "\n" + _truncate(out or "(无 diff 输出)")


def eslint_check(path: str = ".", max_results=None,
                 root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    if not _which("eslint") and not _which("npx"):
        return ("ERROR: 未找到 eslint 或 npx。\n"
                "安装：npm install -g eslint")
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"
    if _which("eslint"):
        cmd = ["eslint", str(p)]
    else:
        cmd = ["npx", "--no-install", "eslint", str(p)]
    rc, out, errout = _run(cmd, root, timeout=90)
    if rc == 0 and not out.strip():
        return f"eslint: 无问题 ✓  ({path})"
    max_r = _as_int(max_results, 100)
    if max_r <= 0:
        max_r = 100
    lines = out.splitlines()
    if len(lines) > max_r:
        lines = lines[:max_r] + [
            f"... (还有 {len(lines) - max_r} 行)"]
    header = f"eslint: {path}  (rc={rc})"
    if errout.strip():
        header += f"\n[stderr]\n{_truncate(errout, 2000)}"
    return header + "\n" + _truncate("\n".join(lines))