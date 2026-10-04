"""图像 / OCR / 二维码 / ANSI / 视频音频 probe / PDF 元数据 handlers。"""
from __future__ import annotations

import importlib
from pathlib import Path


def _imp(name: str):
    return importlib.import_module(f".{name}", package=__package__)


def _require(args: dict, *keys: str) -> str:
    for k in keys:
        if k not in args or args[k] in ("", None):
            return f"ERROR: 缺少必需参数 {k}。"
    return ""


# ═══════════════════════════════════════════════════════════════════════ #
# 图像
# ═══════════════════════════════════════════════════════════════════════ #

def _image_info(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("image")
    return mod.image_info(args["path"], root)


def _image_process(root: Path, args: dict) -> str:
    """op=info 是只读；其他 op 由 core 层处理。"""
    err = _require(args, "op", "path")
    if err:
        return err
    op = str(args["op"]).lower()
    if op != "info":
        return (f"ERROR: image_process op='{op}' 是写操作，"
                f"不应直接走 dispatch_tool。")
    mod = _imp("image_ops")
    res = mod.image_process(
        op="info", path=args["path"], root=root)
    if isinstance(res, tuple) and len(res) >= 1:
        return res[0]
    return str(res)


def _ocr_image(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("ocr")
    return mod.ocr_image(
        args["path"], root,
        lang=args.get("lang", "chi_sim+eng"),
        backend=args.get("backend", ""))


def _ocr_status(root: Path, args: dict) -> str:
    return _imp("ocr").ocr_available()


# ═══════════════════════════════════════════════════════════════════════ #
# 二维码（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _qrcode_decode(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("qrcode_tool")
    return mod.qrcode_decode(args["path"], root)


# ═══════════════════════════════════════════════════════════════════════ #
# ANSI
# ═══════════════════════════════════════════════════════════════════════ #

def _ansi_strip(root: Path, args: dict) -> str:
    mod = _imp("ansi")
    return mod.ansi_strip(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root, keep_osc=bool(args.get("keep_osc", False)))


def _ansi_scan(root: Path, args: dict) -> str:
    mod = _imp("ansi")
    return mod.ansi_scan(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root,
        show_examples=bool(args.get("show_examples", True)))


def _ansi_to_html(root: Path, args: dict) -> str:
    mod = _imp("ansi")
    return mod.ansi_to_html(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root, dark_bg=bool(args.get("dark_bg", True)))


def _ansi_palette(root: Path, args: dict) -> str:
    return _imp("ansi").ansi_palette()


# ═══════════════════════════════════════════════════════════════════════ #
# 视频 / 音频 probe（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _video_probe(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("video")
    return mod.video_probe(args["path"], root)


def _audio_probe(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("audio")
    return mod.audio_probe(args["path"], root)


# ═══════════════════════════════════════════════════════════════════════ #
# PDF 元数据（op=get 只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _pdf_metadata(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    op = str(args.get("op", "get")).lower()
    if op != "get":
        return (f"ERROR: pdf_metadata op='{op}' 是写操作，"
                f"不应直接走 dispatch_tool。")
    mod = _imp("pdf_advanced")
    return mod.pdf_metadata_get(args["path"], root)


# ═══════════════════════════════════════════════════════════════════════ #
# 代码质量（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _ruff_check(root: Path, args: dict) -> str:
    mod = _imp("linters")
    return mod.ruff_check(
        args.get("path", "."),
        args.get("select", ""), args.get("ignore", ""),
        args.get("max_results", 100), root=root)


def _mypy_check(root: Path, args: dict) -> str:
    mod = _imp("linters")
    return mod.mypy_check(
        args.get("path", "."),
        bool(args.get("strict", False)),
        args.get("max_results", 100), root=root)


def _black_check(root: Path, args: dict) -> str:
    mod = _imp("linters")
    return mod.black_check(args.get("path", "."), root=root)


def _eslint_check(root: Path, args: dict) -> str:
    mod = _imp("linters")
    return mod.eslint_check(
        args.get("path", "."), root=root,
        max_results=args.get("max_results", 100))


# ═══════════════════════════════════════════════════════════════════════ #
# Python AST
# ═══════════════════════════════════════════════════════════════════════ #

def _py_outline(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    return _imp("ast_tools").py_outline(args["path"], root)


def _py_imports(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    return _imp("ast_tools").py_imports(
        args["path"], root,
        group=bool(args.get("group", True)))


def _py_find_def(root: Path, args: dict) -> str:
    err = _require(args, "name", "path")
    if err:
        return err
    return _imp("ast_tools").py_find_def(
        args["name"], args["path"], root)


def _py_unused_imports(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    return _imp("ast_tools").py_unused_imports(args["path"], root)


# ═══════════════════════════════════════════════════════════════════════ #
# 注册表
# ═══════════════════════════════════════════════════════════════════════ #

HANDLERS = {
    # 图像
    "image_info":         _image_info,
    "image_process":      _image_process,
    "ocr_image":          _ocr_image,
    "ocr_status":         _ocr_status,
    # 二维码
    "qrcode_decode":      _qrcode_decode,
    # ANSI
    "ansi_strip":         _ansi_strip,
    "ansi_scan":          _ansi_scan,
    "ansi_to_html":       _ansi_to_html,
    "ansi_palette":       _ansi_palette,
    # 媒体
    "video_probe":        _video_probe,
    "audio_probe":        _audio_probe,
    # PDF 元数据
    "pdf_metadata":       _pdf_metadata,
    # 代码质量
    "ruff_check":         _ruff_check,
    "mypy_check":         _mypy_check,
    "black_check":        _black_check,
    "eslint_check":       _eslint_check,
    # Python AST
    "py_outline":         _py_outline,
    "py_imports":         _py_imports,
    "py_find_def":        _py_find_def,
    "py_unused_imports":  _py_unused_imports,
}