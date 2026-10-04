"""PDF 提取（文本）。"""
from __future__ import annotations

from pathlib import Path

from ..config import MAX_PDF_CHARS, MAX_PDF_PAGES
from .sandbox import _as_int, _resolve_path


def _pdf_backend():
    try:
        import pypdf  # noqa
        return "pypdf"
    except ImportError:
        pass
    try:
        import PyPDF2  # noqa
        return "PyPDF2"
    except ImportError:
        return None


def pdf_extract(root: Path, path: str,
                start_page=None, end_page=None,
                max_chars=None) -> str:
    if not path:
        return "ERROR: path 不能为空。"
    backend = _pdf_backend()
    if backend is None:
        return ("ERROR: 未安装 pypdf。\n"
                "运行：pip install pypdf")
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"
    if p.suffix.lower() != ".pdf":
        return f"ERROR: 不是 PDF 文件: {path}"

    try:
        if backend == "pypdf":
            from pypdf import PdfReader
        else:
            from PyPDF2 import PdfReader
    except ImportError as exc:
        return f"ERROR: 导入失败: {exc}"

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开 PDF 失败: {exc}"

    try:
        n_pages = len(reader.pages)
    except Exception:
        n_pages = 0

    if n_pages == 0:
        return f"文件: {path}\n(空 PDF)"

    sp = _as_int(start_page, 1)
    if sp < 1:
        sp = 1
    if sp > n_pages:
        return f"ERROR: start_page={sp} 超出范围（共 {n_pages} 页）"
    ep = _as_int(end_page, min(n_pages, sp + MAX_PDF_PAGES - 1))
    if ep < sp:
        ep = sp
    if ep > n_pages:
        ep = n_pages
    max_pages = MAX_PDF_PAGES
    if ep - sp + 1 > max_pages:
        ep = sp + max_pages - 1

    char_limit = _as_int(max_chars, MAX_PDF_CHARS)
    if char_limit <= 0:
        char_limit = MAX_PDF_CHARS

    pages_text: list = []
    total_chars = 0
    for idx in range(sp - 1, ep):
        try:
            text = reader.pages[idx].extract_text() or ""
        except Exception as exc:
            text = f"[提取失败: {exc}]"
        pages_text.append((idx + 1, text))
        total_chars += len(text)

    lines = [
        f"文件: {path}",
        f"总页数: {n_pages}",
        f"提取范围: {sp}-{ep}",
        f"提取字符: {total_chars}",
        "",
    ]
    out_len = 0
    for pno, text in pages_text:
        block = f"\n===== 第 {pno} 页 =====\n{text}"
        if out_len + len(block) > char_limit:
            remaining = char_limit - out_len
            if remaining > 200:
                lines.append(block[:remaining])
                lines.append(f"\n... (截断，还有更多内容)")
            break
        lines.append(block)
        out_len += len(block)
    return "\n".join(lines)