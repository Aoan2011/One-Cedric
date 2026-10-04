"""压缩包操作：list / info / extract / create。

支持 zip / tar.* / gz / bz2 / xz / zst / lz4 / br（单文件）。
7z / rar 需外部工具，本模块只做探测。
"""
from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from .sandbox import _as_int, _resolve_path

EXT_MAP = {
    ".zip": "zip",
    ".tar": "tar",
    ".gz": "gz",
    ".tgz": "tar.gz",
    ".bz2": "bz2",
    ".tbz2": "tar.bz2",
    ".xz": "xz",
    ".txz": "tar.xz",
    ".zst": "zst",
    ".lz4": "lz4",
    ".br": "br",
    ".7z": "7z",
    ".rar": "rar",
}

TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
                ".tar.xz", ".txz", ".tar")


def _detect_kind(path: Path) -> str:
    name = path.name.lower()
    for suf in TAR_SUFFIXES:
        if name.endswith(suf):
            if suf == ".tgz" or suf == ".tar.gz":
                return "tar.gz"
            if suf == ".tbz2" or suf == ".tar.bz2":
                return "tar.bz2"
            if suf == ".txz" or suf == ".tar.xz":
                return "tar.xz"
            return "tar"
    return EXT_MAP.get(path.suffix.lower(), "unknown")


def _list_zip(p: Path, max_items: int) -> tuple:
    try:
        with zipfile.ZipFile(p, "r") as z:
            infos = z.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        return None, f"ERROR: 不是有效 zip: {exc}"
    lines = []
    total = 0
    for info in infos[:max_items]:
        size = info.file_size
        total += size
        lines.append(f"  {size:>12}  {info.filename}")
    return {
        "count": len(infos),
        "total": total,
        "lines": lines,
        "truncated": len(infos) > max_items,
    }, ""


def _list_tar(p: Path, mode: str, max_items: int) -> tuple:
    try:
        with tarfile.open(p, mode) as t:
            members = t.getmembers()
    except (tarfile.TarError, OSError) as exc:
        return None, f"ERROR: 打开 tar 失败: {exc}"
    lines = []
    total = 0
    for m in members[:max_items]:
        size = m.size
        total += size
        kind = "D" if m.isdir() else ("L" if m.issym() else " ")
        lines.append(f"  {kind} {size:>12}  {m.name}")
    return {
        "count": len(members),
        "total": total,
        "lines": lines,
        "truncated": len(members) > max_items,
    }, ""


def archive_list(p: Path, max_items: int = 200) -> str:
    kind = _detect_kind(p)
    if kind == "zip":
        info, err = _list_zip(p, max_items)
    elif kind.startswith("tar") or kind == "tar":
        mode = "r"
        if kind == "tar.gz":
            mode = "r:gz"
        elif kind == "tar.bz2":
            mode = "r:bz2"
        elif kind == "tar.xz":
            mode = "r:xz"
        info, err = _list_tar(p, mode, max_items)
    elif kind in ("7z", "rar"):
        return (f"ERROR: {kind} 需要外部工具。\n"
                f"安装后可用 7z l / unrar l 手动查看。")
    else:
        return (f"ERROR: 不支持的格式: {p.suffix}\n"
                f"当前支持: zip / tar.* / gz / bz2 / xz / zst / lz4")
    if err:
        return err
    lines = [
        f"文件: {p.name}",
        f"格式: {kind}",
        f"条目数: {info['count']}",
        f"解压后大小: {info['total'] / (1024**2):.2f} MB",
        "",
    ]
    lines.extend(info["lines"])
    if info["truncated"]:
        lines.append(f"  ... (还有 {info['count'] - max_items} 条)")
    return "\n".join(lines)


def archive_info(p: Path) -> str:
    kind = _detect_kind(p)
    size = p.stat().st_size
    lines = [
        f"文件: {p.name}",
        f"路径: {p}",
        f"格式: {kind}",
        f"压缩包大小: {size} bytes ({size / 1024:.1f} KB)",
    ]
    if kind == "zip":
        try:
            with zipfile.ZipFile(p, "r") as z:
                infos = z.infolist()
                raw = sum(i.file_size for i in infos)
                comp = sum(i.compress_size for i in infos)
                ratio = (1 - comp / raw) * 100 if raw else 0
                lines.append(f"条目数: {len(infos)}")
                lines.append(f"原始大小: {raw / (1024**2):.2f} MB")
                lines.append(f"压缩后:   {comp / (1024**2):.2f} MB")
                lines.append(f"压缩率: {ratio:.1f}%")
                if infos:
                    lines.append(
                        f"最新条目: {infos[-1].filename}")
        except Exception as exc:
            lines.append(f"（读取失败: {exc}）")
    elif kind.startswith("tar"):
        mode = {"tar.gz": "r:gz", "tar.bz2": "r:bz2",
                "tar.xz": "r:xz", "tar": "r"}.get(kind, "r")
        try:
            with tarfile.open(p, mode) as t:
                members = t.getmembers()
                raw = sum(m.size for m in members)
                lines.append(f"条目数: {len(members)}")
                lines.append(f"原始大小: {raw / (1024**2):.2f} MB")
                ratio = (1 - size / raw) * 100 if raw else 0
                lines.append(f"压缩率: {ratio:.1f}%")
        except Exception as exc:
            lines.append(f"（读取失败: {exc}）")
    return "\n".join(lines)


def archive_extract(p: Path, dst: Path,
                    overwrite: bool = False) -> str:
    if dst.exists():
        if not overwrite:
            if any(dst.iterdir()):
                return (f"ERROR: 目标目录非空: {dst}\n"
                        f"传 overwrite=true 覆盖。")
        elif dst.is_file():
            return f"ERROR: 目标是文件: {dst}"
    dst.mkdir(parents=True, exist_ok=True)
    kind = _detect_kind(p)
    try:
        if kind == "zip":
            with zipfile.ZipFile(p, "r") as z:
                for name in z.namelist():
                    if _is_unsafe(name):
                        return f"ERROR: 不安全的路径: {name}"
                z.extractall(str(dst))
        elif kind.startswith("tar"):
            mode = {"tar.gz": "r:gz", "tar.bz2": "r:bz2",
                    "tar.xz": "r:xz", "tar": "r"}.get(kind, "r")
            with tarfile.open(p, mode) as t:
                for m in t.getmembers():
                    if _is_unsafe(m.name):
                        return f"ERROR: 不安全的路径: {m.name}"
                t.extractall(str(dst))
        elif kind in ("gz", "bz2", "xz"):
            import gzip
            import bz2
            import lzma
            stem = p.name.rsplit(".", 1)[0]
            out = dst / stem
            opener = {"gz": gzip.open, "bz2": bz2.open,
                      "xz": lzma.open}[kind]
            with opener(p, "rb") as fin, open(out, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            return f"已解压 → {out}"
        elif kind == "zst":
            return ("ERROR: zst 需要 zstandard 库。\n"
                    "pip install zstandard")
        else:
            return f"ERROR: 不支持解压格式: {kind}"
    except Exception as exc:
        return f"ERROR: 解压失败: {exc}"
    return f"已解压 → {dst}"


def _is_unsafe(name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def _create_zip(sources: list, out: Path,
                compression: str = "deflate") -> str:
    comp = {"store": zipfile.ZIP_STORED,
            "deflate": zipfile.ZIP_DEFLATED,
            "bzip2": zipfile.ZIP_BZIP2,
            "lzma": zipfile.ZIP_LZMA}.get(
                compression, zipfile.ZIP_DEFLATED)
    try:
        with zipfile.ZipFile(out, "w", compression=comp) as z:
            for src in sources:
                if src.is_dir():
                    for f in src.rglob("*"):
                        if f.is_file():
                            z.write(f, f.relative_to(src.parent))
                elif src.is_file():
                    z.write(src, src.name)
    except Exception as exc:
        return f"ERROR: 打包失败: {exc}"
    return f"已创建 → {out}"


def _create_tar(sources: list, out: Path,
                kind: str = "gz") -> str:
    mode = {"gz": "w:gz", "bz2": "w:bz2", "xz": "w:xz",
            "none": "w"}.get(kind, "w:gz")
    try:
        with tarfile.open(out, mode) as t:
            for src in sources:
                if src.is_dir():
                    t.add(src, arcname=src.name)
                elif src.is_file():
                    t.add(src, arcname=src.name)
    except Exception as exc:
        return f"ERROR: 打包失败: {exc}"
    return f"已创建 → {out}"


def archive_create(sources: list, out: str,
                   compression: str = "deflate",
                   root: Path | None = None) -> tuple:
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not sources:
        return "", False, "ERROR: sources 不能为空"
    if not out:
        return "", False, "ERROR: out 不能为空"
    resolved_srcs = []
    for s in sources:
        ps, err = _resolve_path(root, s)
        if err:
            return "", False, err
        if not ps.exists():
            return "", False, f"ERROR: 源不存在: {s}"
        resolved_srcs.append(ps)
    out_p, err = _resolve_path(root, out)
    if err:
        return "", False, err
    if out_p.exists():
        return "", False, (f"ERROR: 输出已存在: {out}\n"
                           f"换一个路径或先删除。")
    kind = _detect_kind(out_p)
    if kind == "zip":
        if compression not in ("store", "deflate", "bzip2", "lzma"):
            compression = "deflate"
    elif kind in ("tar.gz", "tar.bz2", "tar.xz", "tar"):
        if compression not in ("gz", "bz2", "xz", "none"):
            compression = {"tar.gz": "gz", "tar.bz2": "bz2",
                           "tar.xz": "xz", "tar": "none"}[kind]
    else:
        return "", False, (f"ERROR: 不支持的输出格式: {out_p.suffix}\n"
                           f"支持: .zip .tar .tar.gz .tgz "
                           f".tar.bz2 .tar.xz")
    lines = [f"将创建压缩包: {out}",
             f"格式: {kind}",
             f"包含 {len(sources)} 个源:"]
    for s in sources[:20]:
        lines.append(f"  {s}")
    if len(sources) > 20:
        lines.append(f"  ... 还有 {len(sources) - 20} 个")
    return "\n".join(lines), True, ""


def archive_create_apply(sources, out, compression, root) -> str:
    resolved_srcs = []
    for s in sources:
        ps, _ = _resolve_path(root, s)
        resolved_srcs.append(ps)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    kind = _detect_kind(out_p)
    if kind == "zip":
        return _create_zip(resolved_srcs, out_p, compression)
    if kind.startswith("tar"):
        return _create_tar(resolved_srcs, out_p, compression)
    return f"ERROR: 不支持的格式: {out_p.suffix}"


def archive_op(root: Path, op: str, archive: str = "",
               dst: str = "", srcs: list | None = None,
               compression: str = "deflate",
               overwrite: bool = False) -> tuple:
    """统一入口。返回 (预览, 是否写操作, 错误)。"""
    op = (op or "").strip().lower()
    if op not in ("list", "info", "extract", "create"):
        return "", False, f"ERROR: 不支持的 op: {op}"
    if op in ("list", "info", "extract"):
        if not archive:
            return "", False, "ERROR: 需要 archive 参数"
        p, err = _resolve_path(root, archive)
        if err:
            return "", False, err
        if not p.exists() or not p.is_file():
            return "", False, f"ERROR: 文件不存在: {archive}"
        if op == "list":
            return archive_list(p), False, ""
        if op == "info":
            return archive_info(p), False, ""
        dst_p, err = _resolve_path(root, dst or ".")
        if err:
            return "", False, err
        return "", True, ""
    if op == "create":
        return archive_create(
            sources=srcs or [], out=archive,
            compression=compression, root=root)
    return "", False, f"ERROR: 不支持 op: {op}"