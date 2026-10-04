"""文件系统操作：copy / move / delete / mkdir。"""
from __future__ import annotations

import shutil as _shutil
from pathlib import Path

from .sandbox import _resolve_path


def file_ops(root: Path, op: str, src: str = "", dst: str = "",
             recursive: bool = False,
             overwrite: bool = False) -> tuple:
    op = (op or "").strip().lower()
    if op not in ("copy", "move", "delete", "mkdir"):
        return "", False, f"ERROR: 不支持的 op: {op}"
    if op == "mkdir":
        if not src:
            return "", False, "ERROR: mkdir 需要 src。"
        p, err = _resolve_path(root, src)
        if err:
            return "", False, err
        if p.exists():
            return "", False, f"ERROR: 目录已存在: {src}"
        return f"将创建目录: {src}", True, ""
    if not src:
        return "", False, "ERROR: 需要 src。"
    p_src, err = _resolve_path(root, src)
    if err:
        return "", False, err
    if not p_src.exists():
        return "", False, f"ERROR: 源路径不存在: {src}"
    if op == "delete":
        if p_src.is_dir() and not recursive:
            return "", False, (f"ERROR: {src} 是目录，"
                               f"需要 recursive=true。")
        return (f"将删除: {src}"
                + ("（递归）" if recursive else "")), True, ""
    if not dst:
        return "", False, f"ERROR: {op} 需要 dst。"
    p_dst, err = _resolve_path(root, dst)
    if err:
        return "", False, err
    if p_dst.exists() and not overwrite:
        return "", False, (f"ERROR: 目标已存在: {dst}"
                           f"（如需覆盖请传 overwrite=true）")
    if p_src.is_dir() and not recursive:
        return "", False, (f"ERROR: {src} 是目录，"
                           f"需要 recursive=true。")
    action = "复制" if op == "copy" else "移动"
    return f"将{action}: {src} → {dst}", True, ""


def _execute_file_ops(root: Path, op: str, src: str = "",
                      dst: str = "", recursive: bool = False,
                      overwrite: bool = False) -> str:
    p_src, _ = _resolve_path(root, src) if src else (None, "")
    p_dst, _ = _resolve_path(root, dst) if dst else (None, "")
    try:
        if op == "mkdir":
            p_src.mkdir(parents=True, exist_ok=True)
            return f"已创建目录 {src}"
        if op == "delete":
            if p_src.is_dir():
                _shutil.rmtree(p_src)
            else:
                p_src.unlink()
            return f"已删除 {src}"
        if op == "copy":
            if p_src.is_dir():
                if p_dst.exists() and overwrite:
                    _shutil.rmtree(p_dst)
                _shutil.copytree(p_src, p_dst)
            else:
                p_dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(p_src, p_dst)
            return f"已复制 {src} → {dst}"
        if op == "move":
            p_dst.parent.mkdir(parents=True, exist_ok=True)
            if p_dst.exists() and overwrite:
                if p_dst.is_dir():
                    _shutil.rmtree(p_dst)
                else:
                    p_dst.unlink()
            _shutil.move(str(p_src), str(p_dst))
            return f"已移动 {src} → {dst}"
    except OSError as exc:
        return f"ERROR: {op} 失败: {exc}"
    return f"ERROR: 未知 op: {op}"