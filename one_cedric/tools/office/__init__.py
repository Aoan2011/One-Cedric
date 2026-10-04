"""办公文档工具：Word / PDF / PPT / Excel。

每个格式一个工具，op 参数区分子操作。
读 op 直接执行，写 op 由 core 层确认。
"""
from __future__ import annotations

from .common import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    system_print, check_file,
)
from .word import docx_op
from .pdf import pdf_op
from .pptx import pptx_op
from .excel import excel_op


# 每个格式的"只读 op"清单，其他 op 都视为写操作
OFFICE_READ_OPS = {
    "docx": {"read", "extract_images", "info"},
    "pdf": {"read", "info", "extract_images", "extract_pages_list"},
    "pptx": {"read", "info", "extract_content"},
    "excel": {"read", "info", "worksheets", "formulas", "list_sheets"},
}


def office_dispatch(name: str, args: dict, root) -> str:
    """只读 op 的统一入口。写 op 由 core 处理。"""
    op = str(args.get("op", "")).lower()
    read_ops = OFFICE_READ_OPS.get(name, set())

    if op not in read_ops:
        return (
            f"ERROR: '{name}' 的 op='{op}' 是写操作，需要 core 层确认。"
            f"不应直接走 dispatch_tool。"
        )

    if name == "docx":
        return docx_op(root, args)
    if name == "pdf":
        return pdf_op(root, args)
    if name == "pptx":
        return pptx_op(root, args)
    if name == "excel":
        return excel_op(root, args)

    return f"ERROR: 未知办公工具 '{name}'。"


__all__ = [
    "docx_op", "pdf_op", "pptx_op", "excel_op",
    "office_dispatch", "OFFICE_READ_OPS",
    "IS_WINDOWS", "IS_MAC", "IS_LINUX",
    "system_print", "check_file",
]