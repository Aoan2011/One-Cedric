"""开发辅助：diff_files。"""
from __future__ import annotations

import difflib
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def diff_files(root: Path, a: str, b: str,
               context=None) -> str:
    if not a or not b:
        return "ERROR: 需要 a 和 b 两个文件路径。"
    pa, err = _resolve_path(root, a)
    if err:
        return err
    pb, err = _resolve_path(root, b)
    if err:
        return err
    if not pa.exists() or not pa.is_file():
        return f"ERROR: 文件不存在: {a}"
    if not pb.exists() or not pb.is_file():
        return f"ERROR: 文件不存在: {b}"
    try:
        ta = pa.read_text(encoding="utf-8", errors="replace").splitlines()
        tb = pb.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"

    ctx = _as_int(context, 3)
    if ctx < 0:
        ctx = 3

    diff = list(difflib.unified_diff(
        ta, tb,
        fromfile=a, tofile=b,
        lineterm="", n=ctx))

    if not diff:
        return f"两个文件完全相同 ✓\n  {a}\n  {b}"

    added = sum(1 for l in diff
                if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff
                  if l.startswith("-") and not l.startswith("---"))

    header = (f"文件差异: {a}  →  {b}\n"
              f"  +{added} 行  -{removed} 行  "
              f"(共 {len(diff)} 行 diff)\n")

    body = "\n".join(diff)
    if len(body) > 18000:
        body = body[:18000] + "\n... (diff 过长，已截断)"
    return header + "\n" + body