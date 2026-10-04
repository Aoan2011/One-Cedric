"""图片 OCR：pytesseract / PaddleOCR / easyocr 三方案。"""
from __future__ import annotations

import shutil
from pathlib import Path

from .sandbox import _resolve_path


def _pick_backend() -> str:
    if shutil.which("tesseract"):
        try:
            import pytesseract  # noqa
            return "tesseract"
        except ImportError:
            pass
    try:
        import paddleocr  # noqa
        return "paddleocr"
    except ImportError:
        pass
    try:
        import easyocr  # noqa
        return "easyocr"
    except ImportError:
        pass
    return ""


def ocr_available() -> str:
    backend = _pick_backend()
    if not backend:
        return ("未安装 OCR 后端。可选：\n"
                "  1. pip install pytesseract Pillow\n"
                "     + 系统安装 tesseract-ocr\n"
                "  2. pip install paddleocr（推荐中文）\n"
                "  3. pip install easyocr")
    return f"当前后端: {backend}"


def _run_tesseract(img_path: Path, lang: str) -> str:
    import pytesseract
    from PIL import Image
    with Image.open(img_path) as im:
        text = pytesseract.image_to_string(im, lang=lang)
    return text


def _run_paddleocr(img_path: Path, lang: str) -> str:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="ch" if "chi" in lang else "en",
        show_log=False)
    result = ocr.ocr(str(img_path), cls=True)
    lines = []
    for block in result or []:
        for line in block or []:
            try:
                lines.append(line[1][0])
            except (IndexError, TypeError):
                continue
    return "\n".join(lines)


def _run_easyocr(img_path: Path, lang: str) -> str:
    import easyocr
    langs = ["ch_sim", "en"] if "chi" in lang else ["en"]
    reader = easyocr.Reader(langs, verbose=False)
    result = reader.readtext(str(img_path), detail=0)
    return "\n".join(result)


def ocr_image(path: str, root: Path, lang: str = "chi_sim+eng",
              backend: str = "") -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"

    bk = backend or _pick_backend()
    if not bk:
        return ocr_available()

    try:
        if bk == "tesseract":
            text = _run_tesseract(p, lang)
        elif bk == "paddleocr":
            text = _run_paddleocr(p, lang)
        elif bk == "easyocr":
            text = _run_easyocr(p, lang)
        else:
            return f"ERROR: 未知后端: {bk}"
    except Exception as exc:
        return f"ERROR: OCR 失败({bk}): {exc}"

    text = (text or "").strip()
    if not text:
        return f"{path}: 未识别到文字"

    if len(text) > 30000:
        text = text[:30000] + f"\n... (截断，原始 {len(text)} 字符)"

    return (f"文件: {path}  后端: {bk}  语言: {lang}\n"
            f"--- 识别结果 ---\n{text}")