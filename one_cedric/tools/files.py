"""文件工具：hash_file / find_duplicates。"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path

from ..config import MAX_SEARCH_FILE_SIZE
from .sandbox import _as_int, _resolve_path


def hash_file(root: Path, path: str,
              algorithm: str = "sha256") -> str:
    if not path:
        return "ERROR: path 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"
    algo = (algorithm or "sha256").lower()
    if algo not in ("md5", "sha1", "sha256", "sha512",
                    "blake2b", "blake2s", "crc32"):
        return f"ERROR: 不支持的算法: {algo}"
    try:
        size = p.stat().st_size
        if algo == "crc32":
            import zlib
            crc = 0
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    crc = zlib.crc32(chunk, crc)
            digest = f"{crc & 0xFFFFFFFF:08x}"
        else:
            h = hashlib.new(algo)
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    h.update(chunk)
            digest = h.hexdigest()
    except OSError as exc:
        return f"ERROR: 计算失败: {exc}"
    return (f"文件: {path}\n"
            f"算法: {algo}\n"
            f"大小: {size} bytes\n"
            f"哈希: {digest}")


def _partial_hash(p: Path, algo: str = "sha256",
                  chunk: int = 65536) -> str:
    """读头部 chunk 字节，用于快速预筛选。"""
    h = hashlib.new(algo)
    try:
        with open(p, "rb") as f:
            h.update(f.read(chunk))
    except OSError:
        return ""
    return h.hexdigest()


def find_duplicates(root: Path, path: str = ".",
                    min_size=None, max_groups=None) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_dir():
        return f"ERROR: 目录不存在: {path}"

    min_sz = _as_int(min_size, 1024)
    if min_sz < 0:
        min_sz = 1024
    max_gr = _as_int(max_groups, 30)
    if max_gr <= 0:
        max_gr = 30

    by_size: dict = defaultdict(list)
    total_scanned = 0
    try:
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames
                           if d not in (
                               "node_modules", "__pycache__",
                               ".git", "venv", ".venv",
                               "dist", "build", ".next",
                               "target", ".cache")]
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    if fp.is_symlink():
                        continue
                    st = fp.stat()
                    if st.st_size < min_sz:
                        continue
                    by_size[st.st_size].append(fp)
                    total_scanned += 1
                    if total_scanned > 50000:
                        break
                except OSError:
                    continue
            if total_scanned > 50000:
                break
    except OSError as exc:
        return f"ERROR: 遍历失败: {exc}"

    candidates = {sz: fps for sz, fps in by_size.items()
                  if len(fps) >= 2}
    if not candidates:
        return (f"未发现重复文件（扫描 {total_scanned} 个，"
                f"min_size={min_sz}）")

    groups: dict = defaultdict(list)
    for sz, fps in candidates.items():
        if len(fps) <= 8:
            for fp in fps:
                try:
                    h = hashlib.sha256(fp.read_bytes()).hexdigest()
                except OSError:
                    continue
                groups[(sz, h)].append(fp)
        else:
            by_partial: dict = defaultdict(list)
            for fp in fps:
                ph = _partial_hash(fp)
                if ph:
                    by_partial[ph].append(fp)
            for ph, sub in by_partial.items():
                if len(sub) < 2:
                    continue
                if len(sub) <= 8:
                    for fp in sub:
                        try:
                            h = hashlib.sha256(
                                fp.read_bytes()).hexdigest()
                        except OSError:
                            continue
                        groups[(sz, h)].append(fp)
                else:
                    by_full: dict = defaultdict(list)
                    for fp in sub:
                        try:
                            h = hashlib.sha256(
                                fp.read_bytes()).hexdigest()
                        except OSError:
                            continue
                        by_full[h].append(fp)
                    for h, ffs in by_full.items():
                        if len(ffs) >= 2:
                            groups[(sz, h)].extend(ffs)

    real_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not real_groups:
        return (f"未发现真正重复的内容（{total_scanned} 个文件，"
                f"候选 {len(candidates)} 组）")

    total_dup_files = sum(len(v) for v in real_groups.values())
    total_waste = sum(
        (len(v) - 1) * k[0] for k, v in real_groups.items())

    lines = [
        f"发现 {len(real_groups)} 组重复文件，"
        f"共 {total_dup_files} 个文件",
        f"可节省空间约 {total_waste / (1024**2):.2f} MB",
        "",
    ]

    sorted_groups = sorted(real_groups.items(),
                           key=lambda x: -x[0][0])
    for i, ((sz, h), fps) in enumerate(
            sorted_groups[:max_gr], start=1):
        lines.append(
            f"# {i}  大小 {sz / 1024:.1f} KB  "
            f"哈希 {h[:12]}…  ({len(fps)} 个)")
        for fp in fps:
            try:
                rel = fp.relative_to(root)
            except ValueError:
                rel = fp
            lines.append(f"    {rel}")
        lines.append("")
    if len(sorted_groups) > max_gr:
        lines.append(f"... 还有 {len(sorted_groups) - max_gr} 组")
    return "\n".join(lines)