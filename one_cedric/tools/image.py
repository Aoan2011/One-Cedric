"""图片信息工具（只读）。"""
from __future__ import annotations

import struct
from pathlib import Path

from .sandbox import _resolve_path


def _sniff(head: bytes):
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(head) >= 24:
            w, h = struct.unpack(">II", head[16:24])
            return ("PNG", w, h)
        return ("PNG", 0, 0)
    if head.startswith(b"\xff\xd8\xff"):
        w, h = _jpeg_size(head)
        return ("JPEG", w, h)
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        if len(head) >= 10:
            w, h = struct.unpack("<HH", head[6:10])
            return ("GIF", w, h)
    if head.startswith(b"RIFF") and len(head) >= 16 \
            and head[8:12] == b"WEBP":
        return ("WebP", 0, 0)
    if head.startswith(b"BM") and len(head) >= 26:
        w, h = struct.unpack("<ii", head[18:26])
        return ("BMP", w, h)
    return None


def _jpeg_size(data: bytes):
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 <= len(data):
                h = (data[i + 5] << 8) | data[i + 6]
                w = (data[i + 7] << 8) | data[i + 8]
                return w, h
        seg_len = (data[i + 2] << 8) | data[i + 3]
        i += 2 + seg_len
    return 0, 0


def image_info(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"

    size = p.stat().st_size
    try:
        with open(p, "rb") as f:
            head = f.read(64)
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"

    info = _sniff(head)
    if info is None:
        try:
            from PIL import Image
            with Image.open(p) as im:
                return _fmt_pil(path, size, im)
        except ImportError:
            return (f"文件: {path}\n大小: {size} bytes\n"
                    f"格式: 未知（未安装 Pillow）")
        except Exception as exc:
            return (f"文件: {path}\n大小: {size} bytes\n"
                    f"格式: 未知（{exc}）")

    fmt, w, h = info
    lines = [f"文件: {path}", f"大小: {size} bytes", f"格式: {fmt}"]
    if w and h:
        lines.append(f"尺寸: {w} × {h}")
        lines.append(f"宽高比: {w / h:.3f}")

    try:
        from PIL import Image
        with Image.open(p) as im:
            lines.append(f"色彩模式: {im.mode}")
            if hasattr(im, "n_frames") and im.n_frames > 1:
                lines.append(f"帧数: {im.n_frames}")
            if im.info.get("dpi"):
                lines.append(f"DPI: {im.info['dpi']}")
    except Exception:
        pass

    return "\n".join(lines)


def _fmt_pil(path, size, im):
    lines = [
        f"文件: {path}",
        f"大小: {size} bytes",
        f"格式: {im.format or '?'}",
        f"尺寸: {im.size[0]} × {im.size[1]}",
        f"色彩模式: {im.mode}",
    ]
    if hasattr(im, "n_frames") and im.n_frames > 1:
        lines.append(f"帧数: {im.n_frames}")
    if im.info.get("dpi"):
        lines.append(f"DPI: {im.info['dpi']}")
    return "\n".join(lines)