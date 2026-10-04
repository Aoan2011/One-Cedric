"""PDF 高级操作：水印、压缩、提取图片、旋转、页码、元数据。

依赖：pypdf + reportlab（水印）
"""
from __future__ import annotations

import io
from pathlib import Path

from .sandbox import _resolve_path


def _pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
        return (PdfReader, PdfWriter), ""
    except ImportError:
        return None, "ERROR: 需要 pypdf（pip install pypdf）"


def pdf_watermark(path: str, out: str = "", text: str = "CONFIDENTIAL",
                  opacity: float = 0.15, font_size: int = 40,
                  angle: int = 45, color: str = "#999999",
                  root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    (R, W), err = _pypdf()
    if err:
        return "", False, err
    try:
        import reportlab  # noqa
    except ImportError:
        return "", False, "ERROR: 水印需要 reportlab（pip install reportlab）"

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_watermarked.pdf"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"水印: {text!r}\n"
            f"透明: {opacity}  大小: {font_size}  角度: {angle}"), True, ""


def pdf_watermark_apply(path, out, text, opacity, font_size, angle, color,
                        root) -> str:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor

    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        reader = PdfReader(str(p))
        writer = PdfWriter()
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    # 用第一页尺寸生成水印（简化：用 letter）
    try:
        page0 = reader.pages[0]
        w = float(page0.mediabox.width)
        h = float(page0.mediabox.height)
    except Exception:
        w, h = letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    try:
        c.setFillColor(HexColor(color or "#999999"))
    except Exception:
        c.setFillColorRGB(0.6, 0.6, 0.6)
    c.setFillAlpha(float(opacity) if opacity else 0.15)
    c.setFont("Helvetica", int(font_size) if font_size else 40)
    c.translate(w / 2, h / 2)
    c.rotate(float(angle) if angle else 45)
    c.drawCentredString(0, 0, text or "WATERMARK")
    c.save()
    buf.seek(0)

    watermark_page = PdfReader(buf).pages[0]

    try:
        for page in reader.pages:
            page.merge_page(watermark_page)
            writer.add_page(page)
        with open(out_p, "wb") as f:
            writer.write(f)
    except Exception as exc:
        return f"ERROR: 写水印失败: {exc}"

    return f"已加水印 → {out_p.relative_to(root)}"


def pdf_compress(path: str, out: str = "", quality: str = "medium",
                 root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    (R, W), err = _pypdf()
    if err:
        return "", False, err

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_compressed.pdf"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"源: {p.relative_to(root)}（{p.stat().st_size} bytes）\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"压缩级别: {quality}"), True, ""


def pdf_compress_apply(path, out, quality, root) -> str:
    from pypdf import PdfReader, PdfWriter

    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        reader = PdfReader(str(p))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
            try:
                page.compress_content_streams()
            except Exception:
                pass
        # 元数据清理
        try:
            writer.add_metadata({})
        except Exception:
            pass
        with open(out_p, "wb") as f:
            writer.write(f)
    except Exception as exc:
        return f"ERROR: 压缩失败: {exc}"

    ratio = (1 - out_p.stat().st_size / p.stat().st_size) * 100
    return (f"已压缩 → {out_p.relative_to(root)}\n"
            f"{p.stat().st_size} → {out_p.stat().st_size} bytes"
            f"（减少 {ratio:.1f}%）")


def pdf_extract_images(path: str, out_dir: str = "",
                       root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    (R, W), err = _pypdf()
    if err:
        return "", False, err

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out_dir:
        out_dir = f"{p.stem}_images"
    od, oerr = _resolve_path(root, out_dir)
    if oerr:
        return "", False, oerr

    return (f"从 {p.relative_to(root)} 提取图片\n"
            f"输出目录: {od.relative_to(root)}"), True, ""


def pdf_extract_images_apply(path, out_dir, root) -> str:
    from pypdf import PdfReader

    p, _ = _resolve_path(root, path)
    od, _ = _resolve_path(root, out_dir)
    od.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    count = 0
    for pi, page in enumerate(reader.pages, 1):
        try:
            images = page.images
        except Exception:
            continue
        for ii, img in enumerate(images, 1):
            try:
                fname = f"page{pi:03d}_{ii:02d}_{img.name}"
                (od / fname).write_bytes(img.data)
                count += 1
            except Exception:
                continue

    if count == 0:
        return f"未在 {p.name} 中找到图片"
    return f"已提取 {count} 张图片 → {od.relative_to(root)}"


def pdf_rotate(path: str, out: str = "", angle: int = 90,
               pages: str = "all",
               root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    (R, W), err = _pypdf()
    if err:
        return "", False, err

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_rotated.pdf"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    try:
        a = int(angle)
    except (TypeError, ValueError):
        return "", False, "ERROR: angle 必须是 90 / 180 / 270"
    if a not in (90, 180, 270):
        return "", False, "ERROR: angle 必须是 90 / 180 / 270"

    return (f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"旋转: {a}°  页: {pages}"), True, ""


def pdf_rotate_apply(path, out, angle, pages, root) -> str:
    from pypdf import PdfReader, PdfWriter

    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    a = int(angle)

    try:
        reader = PdfReader(str(p))
        writer = PdfWriter()

        if pages in ("", "all", None):
            idx = range(len(reader.pages))
        else:
            idx = []
            for part in str(pages).split(","):
                part = part.strip()
                if "-" in part:
                    s, e = part.split("-", 1)
                    idx.extend(range(int(s) - 1, int(e)))
                elif part.isdigit():
                    idx.append(int(part) - 1)
            idx = set(idx)

        for i, page in enumerate(reader.pages):
            if i in (idx if not isinstance(idx, range) else set(idx)):
                page.rotate(a)
            writer.add_page(page)

        with open(out_p, "wb") as f:
            writer.write(f)
    except Exception as exc:
        return f"ERROR: 旋转失败: {exc}"
    return f"已旋转 → {out_p.relative_to(root)}"


def pdf_add_page_numbers(path: str, out: str = "",
                         position: str = "bottom-center",
                         fmt: str = "{n} / {total}",
                         font_size: int = 10,
                         root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    try:
        import reportlab  # noqa
    except ImportError:
        return "", False, "ERROR: 页码需要 reportlab"

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_numbered.pdf"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"位置: {position}  格式: {fmt!r}"), True, ""


def pdf_add_page_numbers_apply(path, out, position, fmt, font_size,
                               root) -> str:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        reader = PdfReader(str(p))
        total = len(reader.pages)
        writer = PdfWriter()

        for i, page in enumerate(reader.pages, 1):
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(w, h))
            c.setFont("Helvetica", int(font_size) or 10)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            text = (fmt or "{n} / {total}").replace("{n}", str(i)) \
                                            .replace("{total}", str(total))
            pos = (position or "bottom-center").lower()
            margin = 20
            if "top" in pos:
                y = h - margin
            else:
                y = margin
            if "left" in pos:
                c.drawString(margin, y, text)
            elif "right" in pos:
                c.drawRightString(w - margin, y, text)
            else:
                c.drawCentredString(w / 2, y, text)
            c.save()
            buf.seek(0)

            wm = PdfReader(buf).pages[0]
            page.merge_page(wm)
            writer.add_page(page)

        with open(out_p, "wb") as f:
            writer.write(f)
    except Exception as exc:
        return f"ERROR: 加页码失败: {exc}"

    return f"已加页码 → {out_p.relative_to(root)}"


def pdf_metadata(path: str, out: str = "", title: str = "",
                 author: str = "", subject: str = "", keywords: str = "",
                 root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    (R, W), err = _pypdf()
    if err:
        return "", False, err

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_meta.pdf"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    lines = [f"源: {p.relative_to(root)}",
             f"输出: {out_p.relative_to(root)}"]
    if title: lines.append(f"Title: {title}")
    if author: lines.append(f"Author: {author}")
    if subject: lines.append(f"Subject: {subject}")
    if keywords: lines.append(f"Keywords: {keywords}")
    return "\n".join(lines), True, ""


def pdf_metadata_apply(path, out, title, author, subject, keywords,
                       root) -> str:
    from pypdf import PdfReader, PdfWriter

    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        reader = PdfReader(str(p))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        meta = {}
        if title: meta["/Title"] = title
        if author: meta["/Author"] = author
        if subject: meta["/Subject"] = subject
        if keywords: meta["/Keywords"] = keywords
        if meta:
            writer.add_metadata(meta)
        with open(out_p, "wb") as f:
            writer.write(f)
    except Exception as exc:
        return f"ERROR: {exc}"
    return f"已更新元数据 → {out_p.relative_to(root)}"


def pdf_metadata_get(path: str, root: Path) -> str:
    (R, W), err = _pypdf()
    if err:
        return err
    p, perr = _resolve_path(root, path)
    if perr:
        return perr
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: {exc}"

    meta = reader.metadata or {}
    lines = [f"文件: {p.name}", f"页数: {len(reader.pages)}", "",
             "元数据:"]
    if not meta:
        lines.append("  （无）")
    for k, v in meta.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)