"""只读工具：read_file / list_files / search_in_files /
file_info / glob_files / grep_regex。"""
from __future__ import annotations

import re
import time
from pathlib import Path

from ..config import (
    MAX_BYTES, MAX_LINES, MAX_SEARCH_RESULTS,
    MAX_SEARCH_FILE_SIZE, MAX_GLOB_RESULTS,
)
from .sandbox import _as_int, _resolve_path


def _guess_binary_kind(p: Path, head: bytes) -> str:
    sigs = [
        (b"\x89PNG\r\n\x1a\n", "PNG 图片"),
        (b"\xff\xd8\xff", "JPEG 图片"),
        (b"GIF87a", "GIF 图片"),
        (b"GIF89a", "GIF 图片"),
        (b"RIFF", "RIFF 容器（可能是 WebP/AVI）"),
        (b"%PDF", "PDF 文档"),
        (b"PK\x03\x04", "ZIP 或 Office 文档"),
        (b"\x1f\x8b", "gzip 压缩"),
        (b"BZh", "bzip2 压缩"),
        (b"\xfd7zXZ", "xz 压缩"),
        (b"\x7fELF", "ELF 可执行"),
        (b"MZ", "Windows 可执行"),
        (b"SQLite format 3", "SQLite 数据库"),
    ]
    for sig, name in sigs:
        if head.startswith(sig):
            return name
    ext = p.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return "图片"
    if ext in (".mp4", ".mkv", ".mov", ".avi"):
        return "视频"
    if ext in (".mp3", ".wav", ".flac", ".ogg"):
        return "音频"
    if ext in (".zip", ".tar", ".gz", ".7z", ".rar"):
        return "压缩包"
    return "二进制文件"


def _binary_refuse(rel: str, size: int, head: bytes) -> str:
    kind = _guess_binary_kind(Path(rel), head)
    if (kind.startswith(("PNG", "JPEG", "GIF"))
            or "图片" in kind or "WebP" in kind or "BMP" in kind):
        hint = "image_info - 查看图片元数据（尺寸/格式/DPI）"
    elif "PDF" in kind:
        hint = "pdf_extract - 提取 PDF 文本"
    elif "ZIP" in kind or "Office" in kind:
        hint = "archive - 列出压缩包内容；docx/excel/pptx - 读办公文档"
    elif "SQLite" in kind:
        hint = "sqlite_tables / sqlite_schema / sqlite（SQL 查询）"
    elif "可执行" in kind or "ELF" in kind or "MZ" in kind:
        hint = "file_info 查看基本信息；hexdump 可用 bash 工具"
    elif "压缩" in kind:
        hint = "archive - op=list 查看内容"
    else:
        hint = "file_info - 查看基本信息"
    return (
        f"ERROR: 这是二进制文件（{kind}），无法作为文本读取。\n"
        f"文件: {rel}\n"
        f"大小: {size} bytes\n"
        f"前 16 字节: {head[:16].hex(' ')}\n\n"
        f"read_file 只用于纯文本。请改用专门工具：\n"
        f"  → {hint}\n\n"
        f"不要用 read_file 或 shell cat/type 硬读二进制——"
        f"内容对模型毫无意义，只会浪费上下文。"
    )


def read_file(root: Path, path: str, start_line=1, end_line=None,
              encoding: str = "") -> str:
    from .encoding_detect import read_text_auto
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root))
    if not p.exists():
        return f"ERROR: 文件不存在: {rel}"
    if not p.is_file():
        return f"ERROR: 不是普通文件: {rel}"
    try:
        raw_head = p.read_bytes()[:8192]
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"
    if b"\x00" in raw_head:
        return _binary_refuse(rel, p.stat().st_size, raw_head)
    try:
        raw_head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            t = raw_head.decode("utf-8", errors="replace")
            bad = sum(1 for c in t if c == "\ufffd")
            if bad / max(1, len(t)) > 0.30:
                from .encoding_detect import detect_encoding
                info = detect_encoding(raw_head)
                if info["confidence"] < 0.5:
                    return _binary_refuse(
                        rel, p.stat().st_size, raw_head)
        except Exception:
            return _binary_refuse(rel, p.stat().st_size, raw_head)
    result = read_text_auto(p, prefer=encoding)
    if not result["ok"]:
        return f"ERROR: 读取失败: {result['error']}"
    text = result["text"]
    detected = result["encoding"]
    raw_size = result["size"]
    truncated_bytes = raw_size > MAX_BYTES
    if truncated_bytes:
        text = text[: MAX_BYTES // 2]
    lines = text.splitlines()
    if not lines:
        return f"文件: {rel}  ({detected})\n(空文件，0 行)"
    total = len(lines)
    start = max(1, _as_int(start_line, 1))
    if start > total:
        return (f"ERROR: start_line={start} 超出文件总行数 {total}"
                f"（文件: {rel}）")
    end = (total if end_line is None
           else min(_as_int(end_line, total), total))
    if end < start:
        return f"ERROR: end_line({end}) 小于 start_line({start})"
    if end - start + 1 > MAX_LINES:
        end = start + MAX_LINES - 1
    enc_note = detected
    if result["confidence"] < 0.7:
        enc_note += f" (置信度 {result['confidence']:.0%})"
    header = (f"文件: {rel}  ({enc_note})  "
              f"共 {total} 行，显示第 {start}-{end} 行")
    body = "\n".join(
        f"{i:>6}| {lines[i - 1]}" for i in range(start, end + 1))
    footer = ""
    if end < total:
        footer += (f"\n... (还有 {total - end} 行未显示，"
                   f"可用 start_line/end_line 继续读取)")
    if truncated_bytes:
        footer += (f"\n... (文件过大，已截断到前 "
                   f"{MAX_BYTES // 1000}KB)")
    return f"{header}\n{body}{footer}"


def list_files(root: Path, path=".", recursive=False) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root)) if p != root else "."
    if not p.exists():
        return f"ERROR: 目录不存在: {rel}"
    if not p.is_dir():
        return f"ERROR: 不是目录: {rel}"
    lines = []
    try:
        if recursive:
            for item in sorted(p.rglob("*")):
                if item.is_dir():
                    lines.append(
                        f"[DIR]  {item.relative_to(root)}/")
                else:
                    lines.append(
                        f"[FILE] {item.relative_to(root)}  "
                        f"({item.stat().st_size} bytes)")
        else:
            for item in sorted(p.iterdir()):
                if item.is_dir():
                    lines.append(f"[DIR]  {item.name}/")
                else:
                    lines.append(
                        f"[FILE] {item.name}  "
                        f"({item.stat().st_size} bytes)")
    except OSError as exc:
        return f"ERROR: 列出目录失败: {exc}"
    if not lines:
        return f"目录: {rel}\n(空目录)"
    return (f"目录: {rel}  (共 {len(lines)} 项)\n"
            + "\n".join(lines))


def search_in_files(root: Path, pattern: str, path=".",
                    file_pattern="*") -> str:
    if not pattern:
        return "ERROR: 搜索关键词不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root)) if p != root else "."
    if not p.exists():
        return f"ERROR: 目录不存在: {rel}"
    if not p.is_dir():
        return f"ERROR: 不是目录: {rel}"
    results = []
    files = (sorted(p.rglob(file_pattern))
             if file_pattern != "*" else sorted(p.rglob("*")))
    for f in files:
        if not f.is_file():
            continue
        try:
            if f.stat().st_size > MAX_SEARCH_FILE_SIZE:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern in line:
                results.append(
                    f"{f.relative_to(root)}:{lineno}: "
                    f"{line.strip()}")
                if len(results) >= MAX_SEARCH_RESULTS:
                    break
        if len(results) >= MAX_SEARCH_RESULTS:
            break
    if not results:
        return f"在 {rel} 下未找到包含 '{pattern}' 的内容。"
    return (f"在 {rel} 下搜索 '{pattern}'，"
            f"共找到 {len(results)} 条结果：\n"
            + "\n".join(results))


def file_info(root: Path, path: str) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root))
    if not p.exists():
        return f"ERROR: 文件不存在: {rel}"
    if not p.is_file():
        return f"ERROR: 不是普通文件: {rel}"
    try:
        stat = p.stat()
        size = stat.st_size
        mtime = time.strftime("%Y-%m-%d %H:%M:%S",
                              time.localtime(stat.st_mtime))
        with open(p, "rb") as f:
            head = f.read(8192)
        is_binary = b"\x00" in head
        if not is_binary:
            try:
                head.decode("utf-8")
            except UnicodeDecodeError:
                is_binary = True
        if is_binary:
            kind = _guess_binary_kind(p, head)
            return (f"文件: {rel}\n"
                    f"类型: {kind}\n"
                    f"大小: {size} bytes\n"
                    f"修改时间: {mtime}\n"
                    f"（二进制文件，不统计行数）")
        text = p.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
    except OSError as exc:
        return f"ERROR: 获取文件信息失败: {exc}"
    return (f"文件: {rel}\n"
            f"大小: {size} bytes\n"
            f"行数: {line_count}\n"
            f"修改时间: {mtime}")


def glob_files(root: Path, pattern: str, path=".",
               max_results=None) -> str:
    if not pattern or not isinstance(pattern, str):
        return "ERROR: 参数 pattern 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root)) if p != root else "."
    if not p.exists() or not p.is_dir():
        return f"ERROR: 目录不存在: {rel}"
    limit = _as_int(max_results, MAX_GLOB_RESULTS)
    if limit <= 0:
        limit = MAX_GLOB_RESULTS
    lines = []
    truncated = False
    try:
        for item in sorted(p.glob(pattern)):
            if not item.is_file():
                continue
            try:
                st = item.stat()
                r = item.relative_to(root)
                lines.append(
                    f"{r}\t{st.st_size} bytes\t"
                    f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
            except OSError:
                continue
            if len(lines) >= limit:
                truncated = True
                break
    except (OSError, ValueError) as exc:
        return f"ERROR: glob 失败: {exc}"
    if not lines:
        return f"在 {rel} 下未匹配到 {pattern!r}。"
    header = (f"匹配 {pattern!r}（{len(lines)} 项"
              + ("，已截断" if truncated else "") + "）：")
    return header + "\n" + "\n".join(lines)


def grep_regex(root: Path, pattern: str, path=".",
               file_pattern="*", case_insensitive=False,
               max_results=None) -> str:
    if not pattern:
        return "ERROR: 正则不能为空。"
    try:
        flags = re.MULTILINE | (re.IGNORECASE if case_insensitive
                                 else 0)
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return f"ERROR: 正则编译失败: {exc}"
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root)) if p != root else "."
    if not p.exists() or not p.is_dir():
        return f"ERROR: 目录不存在: {rel}"
    limit = _as_int(max_results, MAX_SEARCH_RESULTS)
    if limit <= 0:
        limit = MAX_SEARCH_RESULTS
    results = []
    files = (sorted(p.rglob(file_pattern))
             if file_pattern != "*" else sorted(p.rglob("*")))
    for f in files:
        if not f.is_file():
            continue
        try:
            if f.stat().st_size > MAX_SEARCH_FILE_SIZE:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                snippet = line.strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "…"
                results.append(
                    f"{f.relative_to(root)}:{lineno}: {snippet}")
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break
    if not results:
        return f"在 {rel} 下未匹配到正则 {pattern!r}。"
    return (f"在 {rel} 下匹配正则 {pattern!r}，"
            f"共 {len(results)} 条：\n" + "\n".join(results))