"""PDF 操作：pypdf + pdf2image + pytesseract。"""
from __future__ import annotations

from pathlib import Path

from ..sandbox import _resolve_path
from .common import check_file, format_size, system_print


def _pdf_read(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: 需要 pypdf（pip install pypdf）"

    path = str(args.get("path", ""))
    start = args.get("start_page")
    end = args.get("end_page")

    p, err = _resolve_path(root, path)
    if err:
        return err
    err = check_file(p, (".pdf",))
    if err:
        return err

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    total = len(reader.pages)
    s = max(1, int(start)) if start else 1
    e = min(int(end), total) if end else total
    if s > e:
        return f"ERROR: start_page({s}) 大于 end_page({e})"

    lines = [f"文件: {p.name}",
             f"总页数: {total}",
             f"提取: 第 {s}-{e} 页",
             ""]

    for i in range(s - 1, e):
        try:
            txt = reader.pages[i].extract_text() or ""
        except Exception as exc:
            txt = f"[提取失败: {exc}]"
        lines.append(f"--- 第 {i+1} 页 ---")
        lines.append(txt.strip()[:3000])
        lines.append("")

    return "\n".join(lines)


def _pdf_info(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    p, err = _resolve_path(root, path)
    if err:
        return err
    err = check_file(p, (".pdf",))
    if err:
        return err

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    meta = reader.metadata or {}
    stat = p.stat()
    import time
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))

    lines = [f"文件: {p.name}",
             f"页数: {len(reader.pages)}",
             f"大小: {format_size(stat.st_size)}",
             f"修改时间: {mtime}",
             f"加密: {'是' if reader.is_encrypted else '否'}"]
    if meta:
        lines.append("元数据:")
        for k, v in meta.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _pdf_extract_images(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    out_dir = str(args.get("out_dir", "") or "")

    p, err = _resolve_path(root, path)
    if err:
        return err
    err = check_file(p, (".pdf",))
    if err:
        return err

    if not out_dir:
        out_dir = f"{p.stem}_images"
    od, err = _resolve_path(root, out_dir)
    if err:
        return err

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    od.mkdir(parents=True, exist_ok=True)
    count = 0
    for pi, page in enumerate(reader.pages):
        try:
            images = page.images
        except Exception:
            continue
        for ii, img in enumerate(images):
            try:
                fname = f"p{pi+1}_{ii+1}_{img.name}"
                (od / fname).write_bytes(img.data)
                count += 1
            except Exception:
                continue

    if count == 0:
        return f"未找到嵌入图片: {p.name}"
    return f"已提取 {count} 张图片到 {od.relative_to(root)}"


def _pdf_extract_pages_list(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    p, err = _resolve_path(root, path)
    if err:
        return err
    err = check_file(p, (".pdf",))
    if err:
        return err

    reader = PdfReader(str(p))
    lines = [f"文件: {p.name}", f"共 {len(reader.pages)} 页", ""]
    for i, page in enumerate(reader.pages, 1):
        try:
            box = page.mediabox
            w = float(box.width)
            h = float(box.height)
            size = f"{w:.0f}×{h:.0f}"
        except Exception:
            size = "?"
        try:
            txt = page.extract_text() or ""
            preview = txt.strip().splitlines()[0][:60] if txt.strip() else "(无文本)"
        except Exception:
            preview = "?"
        lines.append(f"p{i:>3}  {size}  {preview}")
    return "\n".join(lines)


def _pdf_merge(root: Path, args: dict):
    files = args.get("files") or []
    out = str(args.get("out", "") or "")
    if not files or not isinstance(files, list):
        return "", False, "ERROR: merge 需要 files 列表"
    if not out:
        return "", False, "ERROR: merge 需要 out"
    preview = f"将合并 {len(files)} 个 PDF → {out}\n  " + "\n  ".join(files[:5])
    if len(files) > 5:
        preview += f"\n  ... 还有 {len(files) - 5} 个"
    return preview, True, ""


def _pdf_merge_apply(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfWriter
    except ImportError:
        return "ERROR: 需要 pypdf"

    files = args.get("files") or []
    out = str(args.get("out", ""))
    out_p, err = _resolve_path(root, out)
    if err:
        return err

    writer = PdfWriter()
    for f in files:
        fp, err = _resolve_path(root, str(f))
        if err:
            return err
        if not fp.exists():
            return f"ERROR: 文件不存在: {f}"
        try:
            writer.append(str(fp))
        except Exception as exc:
            return f"ERROR: 合并 {f} 失败: {exc}"

    try:
        with open(out_p, "wb") as fout:
            writer.write(fout)
    except Exception as exc:
        return f"ERROR: 保存失败: {exc}"
    return f"已合并 {len(files)} 个 PDF → {out}"


def _pdf_split(root: Path, args: dict):
    path = str(args.get("path", ""))
    pages = str(args.get("pages", "") or "")
    out_dir = str(args.get("out_dir", "") or "")
    if not pages:
        return "", False, "ERROR: split 需要 pages（如 '1-3,5,7-9'）"
    if not out_dir:
        return "", False, "ERROR: split 需要 out_dir"
    return f"将拆分 {path} 的第 {pages} 页 → {out_dir}/", True, ""


def _parse_pages(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return out


def _pdf_split_apply(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    pages = str(args.get("pages", ""))
    out_dir = str(args.get("out_dir", ""))

    p, err = _resolve_path(root, path)
    if err:
        return err
    od, err = _resolve_path(root, out_dir)
    if err:
        return err
    od.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    try:
        idxs = _parse_pages(pages)
    except Exception as exc:
        return f"ERROR: 解析 pages 失败: {exc}"

    count = 0
    for i in idxs:
        if i < 0 or i >= len(reader.pages):
            continue
        writer = PdfWriter()
        writer.add_page(reader.pages[i])
        out_file = od / f"{p.stem}_p{i+1}.pdf"
        with open(out_file, "wb") as fout:
            writer.write(fout)
        count += 1
    return f"已拆分 {count} 页到 {od.relative_to(root)}"


def _pdf_encrypt(root: Path, args: dict):
    path = str(args.get("path", ""))
    password = str(args.get("password", "") or "")
    out = str(args.get("out", "") or "")
    if not password:
        return "", False, "ERROR: encrypt 需要 password"
    if not out:
        return "", False, "ERROR: encrypt 需要 out"
    return f"将加密 {path} → {out}", True, ""


def _pdf_encrypt_apply(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    password = str(args.get("password", ""))
    out = str(args.get("out", ""))

    p, err = _resolve_path(root, path)
    if err:
        return err
    out_p, err = _resolve_path(root, out)
    if err:
        return err

    try:
        reader = PdfReader(str(p))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)
        with open(out_p, "wb") as fout:
            writer.write(fout)
        return f"已加密: {out}"
    except Exception as exc:
        return f"ERROR: 加密失败: {exc}"


def _pdf_decrypt(root: Path, args: dict):
    path = str(args.get("path", ""))
    password = str(args.get("password", "") or "")
    out = str(args.get("out", "") or "")
    if not password:
        return "", False, "ERROR: decrypt 需要 password"
    if not out:
        return "", False, "ERROR: decrypt 需要 out"
    return f"将解密 {path} → {out}", True, ""


def _pdf_decrypt_apply(root: Path, args: dict) -> str:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return "ERROR: 需要 pypdf"

    path = str(args.get("path", ""))
    password = str(args.get("password", ""))
    out = str(args.get("out", ""))

    p, err = _resolve_path(root, path)
    if err:
        return err
    out_p, err = _resolve_path(root, out)
    if err:
        return err

    try:
        reader = PdfReader(str(p))
        if reader.is_encrypted:
            reader.decrypt(password)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(out_p, "wb") as fout:
            writer.write(fout)
        return f"已解密: {out}"
    except Exception as exc:
        return f"ERROR: 解密失败: {exc}"


def _pdf_print(root: Path, args: dict):
    path = str(args.get("path", ""))
    printer = str(args.get("printer", "") or "")
    p, err = _resolve_path(root, path)
    if err:
        return "", False, err
    err = check_file(p, (".pdf",))
    if err:
        return "", False, err
    preview = f"将打印 {p.name}"
    if printer:
        preview += f"  → {printer}"
    return preview, True, ""


def _pdf_print_apply(root: Path, args: dict) -> str:
    path = str(args.get("path", ""))
    printer = str(args.get("printer", "") or "")
    p, err = _resolve_path(root, path)
    if err:
        return err
    return system_print(p, printer)


def _pdf_ocr(root: Path, args: dict):
    path = str(args.get("path", ""))
    start = args.get("start_page")
    end = args.get("end_page")
    lang = str(args.get("lang", "chi_sim+eng") or "chi_sim+eng")
    return f"将对 {path} 做 OCR（第 {start or 1}-{end or '末'} 页，语言 {lang}）", True, ""


def _pdf_ocr_apply(root: Path, args: dict) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return "ERROR: 需要 pdf2image + pytesseract + Pillow"

    path = str(args.get("path", ""))
    start = args.get("start_page")
    end = args.get("end_page")
    lang = str(args.get("lang", "chi_sim+eng"))

    p, err = _resolve_path(root, path)
    if err:
        return err

    try:
        first = int(start) if start else 1
        last = int(end) if end else None
        kwargs = {"first_page": first, "dpi": 200}
        if last:
            kwargs["last_page"] = last
        images = convert_from_path(str(p), **kwargs)
    except Exception as exc:
        return f"ERROR: PDF 转图片失败: {exc}"

    lines = [f"OCR: {p.name}（{len(images)} 页）", ""]
    for i, img in enumerate(images, first):
        try:
            txt = pytesseract.image_to_string(img, lang=lang)
        except Exception as exc:
            txt = f"[OCR 失败: {exc}]"
        lines.append(f"--- 第 {i} 页 ---")
        lines.append(txt.strip()[:2000])
        lines.append("")
    return "\n".join(lines)


def pdf_op(root: Path, args: dict):
    op = str(args.get("op", "")).lower()

    if op == "read":
        return _pdf_read(root, args)
    if op == "info":
        return _pdf_info(root, args)
    if op == "extract_images":
        return _pdf_extract_images(root, args)
    if op == "extract_pages_list":
        return _pdf_extract_pages_list(root, args)

    if op == "merge":
        return _pdf_merge(root, args)
    if op == "split":
        return _pdf_split(root, args)
    if op == "encrypt":
        return _pdf_encrypt(root, args)
    if op == "decrypt":
        return _pdf_decrypt(root, args)
    if op == "print":
        return _pdf_print(root, args)
    if op == "ocr":
        return _pdf_ocr(root, args)

    return "", False, f"ERROR: 未知 op: {op}"


def pdf_apply(root: Path, args: dict) -> str:
    op = str(args.get("op", "")).lower()
    if op == "merge":
        return _pdf_merge_apply(root, args)
    if op == "split":
        return _pdf_split_apply(root, args)
    if op == "encrypt":
        return _pdf_encrypt_apply(root, args)
    if op == "decrypt":
        return _pdf_decrypt_apply(root, args)
    if op == "print":
        return _pdf_print_apply(root, args)
    if op == "ocr":
        return _pdf_ocr_apply(root, args)
    return f"ERROR: 未知写 op: {op}"