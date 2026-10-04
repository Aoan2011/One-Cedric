"""系统信息扩展工具。"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def pip_list(filter: str = "", outdated: bool = False) -> str:
    if outdated:
        cmd = [sys.executable, "-m", "pip", "list", "--outdated",
               "--format", "columns"]
    else:
        cmd = [sys.executable, "-m", "pip", "list", "--format", "columns"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: 执行失败: {exc}"

    if r.returncode != 0:
        return f"ERROR: pip 返回 {r.returncode}: {r.stderr[:500]}"

    out = r.stdout
    if filter:
        lines = out.splitlines()
        filtered = [lines[0]] + [l for l in lines[1:] if filter.lower() in l.lower()]
        out = "\n".join(filtered)

    return out.strip()


def pip_show(package: str) -> str:
    if not package:
        return "ERROR: package 不能为空"
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "show", package],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: 未找到包 '{package}'"
    return r.stdout.strip()


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def disk_tree(path: str = ".", root: Path | None = None, max_depth: int = 3,
              min_size: int = 0, top: int = 30) -> str:
    if root is None:
        return "ERROR: 需要 root"
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_dir():
        return f"ERROR: 目录不存在: {path}"

    try:
        depth = max(1, min(int(max_depth), 8))
        min_sz = max(0, _as_int(min_size, 0))
        limit = max(1, min(_as_int(top, 30), 200))
    except (TypeError, ValueError):
        depth, min_sz, limit = 3, 0, 30

    sizes: list[tuple[Path, int]] = []

    def _walk(d: Path, level: int):
        if level > depth:
            return
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            return
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    _walk(e, level + 1)
                elif e.is_file():
                    sz = e.stat().st_size
                    if sz >= min_sz:
                        sizes.append((e, sz))
            except (OSError, PermissionError):
                continue

    _walk(p, 1)
    sizes.sort(key=lambda x: -x[1])
    total = sum(sz for _, sz in sizes)

    lines = [f"目录: {path}", f"总计 {len(sizes)} 个文件 · {_human(total)}", ""]
    lines.append(f"Top {min(limit, len(sizes))}:")
    for f, sz in sizes[:limit]:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        lines.append(f"  {_human(sz):>10}  {rel}")

    if len(sizes) > limit:
        lines.append(f"  ... 还有 {len(sizes) - limit} 个文件")

    by_ext: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f, sz in sizes:
        ext = f.suffix.lower() or "(无扩展名)"
        by_ext[ext][0] += 1
        by_ext[ext][1] += sz

    if by_ext:
        lines.append("")
        lines.append("按扩展名:")
        for ext, (n, sz) in sorted(by_ext.items(), key=lambda x: -x[1][1])[:15]:
            lines.append(f"  {ext:<15} {n:>5} 个  {_human(sz):>10}")

    return "\n".join(lines)