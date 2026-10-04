"""图像处理：缩放/裁剪/格式转换/水印/压缩/旋转/拼接。

依赖：Pillow
"""
from __future__ import annotations

from pathlib import Path

from .sandbox import _as_int, _resolve_path

SUPPORTED_IN = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
                ".tiff", ".tif", ".ico", ".ppm"}
SUPPORTED_OUT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                 ".webp": "WEBP", ".bmp": "BMP", ".gif": "GIF",
                 ".tiff": "TIFF", ".ico": "ICO"}


def _pil():
    try:
        from PIL import Image
        return Image, ""
    except ImportError:
        return None, "ERROR: 需要 Pillow（pip install Pillow）"


def image_process(op: str, path: str, out: str = "",
                  width=None, height=None,
                  percent=None, quality=None,
                  box: list | None = None,
                  angle=None, flip: str = "",
                  text: str = "", position: str = "br",
                  font_size=None, color: str = "",
                  to_format: str = "",
                  root: Path | None = None):
    """统一入口。返回 (preview, is_write, error)。

    op=info 直接返回字符串。
    """
    if root is None:
        return "", False, "ERROR: 需要 root"
    Image, err = _pil()
    if err:
        return "", False, err

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    op = (op or "").lower()

    if op == "info":
        return _info(Image, p), False, ""

    if op not in ("resize", "crop", "convert", "rotate", "flip",
                  "watermark", "compress", "thumbnail"):
        return "", False, f"ERROR: 未知 op: {op}"

    if not out:
        stem = p.stem
        suffix = p.suffix
        if op == "convert" and to_format:
            ext = to_format.lower()
            if not ext.startswith("."):
                ext = "." + ext
            suffix = ext if ext in SUPPORTED_OUT else suffix
        elif op == "compress":
            suffix = ".jpg" if p.suffix.lower() not in (".jpg", ".jpeg") \
                else p.suffix
        else:
            suffix = p.suffix
        out = f"{stem}_{op}{suffix}"

    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    preview = [f"源: {p.relative_to(root)}",
               f"输出: {out_p.relative_to(root)}",
               f"操作: {op}"]
    if op == "resize" and (width or height or percent):
        preview.append(f"尺寸: {width or 'auto'}×{height or 'auto'}"
                       + (f"  缩放 {percent}%" if percent else ""))
    elif op == "crop" and box:
        preview.append(f"裁剪区: {box}")
    elif op == "convert" and to_format:
        preview.append(f"格式: → {to_format}")
    elif op == "rotate" and angle is not None:
        preview.append(f"角度: {angle}°")
    elif op == "flip" and flip:
        preview.append(f"方向: {flip}")
    elif op == "watermark" and text:
        preview.append(f"水印: {text!r} 位置={position}")
    elif op == "compress" and quality:
        preview.append(f"质量: {quality}%")

    return "\n".join(preview), True, ""


def image_apply(op: str, path: str, out: str, width=None, height=None,
                percent=None, quality=None, box: list | None = None,
                angle=None, flip: str = "", text: str = "",
                position: str = "br", font_size=None, color: str = "",
                to_format: str = "", root: Path | None = None) -> str:
    Image, err = _pil()
    if err:
        return err
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        im = Image.open(p)
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    try:
        if op == "resize":
            im = _do_resize(im, width, height, percent)
        elif op == "thumbnail":
            max_dim = _as_int(width, 200)
            im.thumbnail((max_dim, max_dim))
        elif op == "crop":
            if not box or len(box) != 4:
                return "ERROR: crop 需要 box=[left,top,right,bottom]"
            im = im.crop(tuple(int(x) for x in box))
        elif op == "rotate":
            im = im.rotate(float(angle or 90), expand=True)
        elif op == "flip":
            if flip == "h":
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            elif flip == "v":
                im = im.transpose(Image.FLIP_TOP_BOTTOM)
            else:
                return "ERROR: flip 必须是 h 或 v"
        elif op == "watermark":
            if not text:
                return "ERROR: watermark 需要 text"
            im = _do_watermark(im, text, position, font_size, color)
        elif op == "compress":
            im = im.convert("RGB")
        elif op == "convert":
            pass

        out_p.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {}
        ext = out_p.suffix.lower()
        fmt = SUPPORTED_OUT.get(ext)
        if not fmt:
            return f"ERROR: 不支持的输出格式: {ext}"

        if fmt == "JPEG":
            im = im.convert("RGB")
            q = _as_int(quality, 85)
            save_kwargs["quality"] = max(1, min(q, 100))
            save_kwargs["optimize"] = True
        elif fmt == "WEBP":
            q = _as_int(quality, 85)
            save_kwargs["quality"] = max(1, min(q, 100))
        elif fmt == "PNG":
            save_kwargs["optimize"] = True
        elif fmt == "GIF":
            save_kwargs["optimize"] = True

        im.save(out_p, format=fmt, **save_kwargs)
    except Exception as exc:
        return f"ERROR: 处理失败: {exc}"

    size_in = p.stat().st_size
    size_out = out_p.stat().st_size
    ratio = (1 - size_out / size_in) * 100 if size_in else 0
    return (f"已生成 {out_p.relative_to(root)}\n"
            f"{size_in} → {size_out} bytes（"
            f"{'减少' if ratio > 0 else '增加'} {abs(ratio):.1f}%）")


def _do_resize(im, width, height, percent):
    from PIL import Image
    if percent:
        w, h = im.size
        ratio = float(percent) / 100
        return im.resize(
            (max(1, int(w * ratio)), max(1, int(h * ratio))),
            Image.LANCZOS)
    w0, h0 = im.size
    if width and height:
        return im.resize((int(width), int(height)), Image.LANCZOS)
    if width:
        ratio = int(width) / w0
        return im.resize((int(width), max(1, int(h0 * ratio))),
                         Image.LANCZOS)
    if height:
        ratio = int(height) / h0
        return im.resize((max(1, int(w0 * ratio)), int(height)),
                         Image.LANCZOS)
    return im


def _do_watermark(im, text: str, position: str, font_size, color: str):
    from PIL import Image, ImageDraw, ImageFont
    im = im.convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    fs = _as_int(font_size, max(16, min(im.size) // 20))
    try:
        font = ImageFont.truetype("arial.ttf", fs)
    except Exception:
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fs)
        except Exception:
            font = ImageFont.load_default()

    fill = color or "#ffffff88"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    W, H = im.size
    margin = 20
    pos = (position or "br").lower()
    if pos == "tl":
        x, y = margin, margin
    elif pos == "tr":
        x, y = W - tw - margin, margin
    elif pos == "bl":
        x, y = margin, H - th - margin
    elif pos == "center":
        x, y = (W - tw) // 2, (H - th) // 2
    else:
        x, y = W - tw - margin, H - th - margin

    draw.text((x, y), text, font=font, fill=fill)
    return Image.alpha_composite(im, overlay)


def _info(Image, p: Path) -> str:
    try:
        im = Image.open(p)
    except Exception as exc:
        return f"ERROR: {exc}"
    lines = [
        f"路径: {p.name}",
        f"格式: {im.format or '?'}",
        f"尺寸: {im.size[0]} × {im.size[1]}",
        f"模式: {im.mode}",
    ]
    if hasattr(im, "n_frames") and im.n_frames > 1:
        lines.append(f"帧数: {im.n_frames}")
    if im.info.get("dpi"):
        lines.append(f"DPI: {im.info['dpi']}")
    lines.append(f"文件大小: {p.stat().st_size} bytes")
    return "\n".join(lines)