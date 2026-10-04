"""二维码 / 条形码：生成与识别。

生成：qrcode（纯 Python，可无 Pillow）
识别：pyzbar（需要 zbar 库）
"""
from __future__ import annotations

from pathlib import Path

from .sandbox import _resolve_path


def qrcode_generate(content: str, out: str = "",
                    size: int = 10, border: int = 4,
                    error_level: str = "M", color: str = "#000000",
                    bg: str = "#ffffff",
                    root: Path | None = None) -> tuple:
    if not content:
        return "", False, "ERROR: content 不能为空"
    if root is None:
        return "", False, "ERROR: 需要 root"

    try:
        import qrcode  # noqa
    except ImportError:
        return "", False, ("ERROR: 需要 qrcode"
                            "（pip install qrcode[pil]）")

    if not out:
        safe = "".join(c if c.isalnum() else "_"
                       for c in content[:20])
        out = f"qrcode_{safe}.png"

    out_p, err = _resolve_path(root, out)
    if err:
        return "", False, err
    if out_p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg"):
        return "", False, "ERROR: 输出必须是 .png / .jpg / .svg"

    preview = (f"内容: {content[:200]}"
               + ("…" if len(content) > 200 else "") + "\n"
               f"输出: {out_p.relative_to(root)}\n"
               f"大小: {size}  边框: {border}  "
               f"纠错: {error_level}")
    return preview, True, ""


def qrcode_generate_apply(content: str, out: str, size: int,
                          border: int, error_level: str,
                          color: str, bg: str,
                          root: Path) -> str:
    try:
        import qrcode
        from qrcode.constants import (
            ERROR_CORRECT_L, ERROR_CORRECT_M,
            ERROR_CORRECT_Q, ERROR_CORRECT_H,
        )
    except ImportError:
        return "ERROR: 需要 qrcode（pip install qrcode[pil]）"

    levels = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
              "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
    lvl = levels.get((error_level or "M").upper(), ERROR_CORRECT_M)

    try:
        qr = qrcode.QRCode(
            version=None, error_correction=lvl,
            box_size=max(1, int(size)),
            border=max(0, int(border)))
        qr.add_data(content)
        qr.make(fit=True)

        out_p, _ = _resolve_path(root, out)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if out_p.suffix.lower() == ".svg":
            try:
                import qrcode.image.svg
                factory = qrcode.image.svg.SvgPathImage
                img = qr.make_image(image_factory=factory)
                img.save(str(out_p))
            except ImportError:
                return "ERROR: SVG 需要 qrcode 完整安装"
        else:
            img = qr.make_image(fill_color=color, back_color=bg)
            img.save(str(out_p))

        return (f"已生成二维码: {out_p.relative_to(root)}\n"
                f"文件大小: {out_p.stat().st_size} bytes")
    except Exception as exc:
        return f"ERROR: 生成失败: {exc}"


def qrcode_decode(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"

    try:
        from PIL import Image  # noqa
    except ImportError:
        return "ERROR: 需要 Pillow"

    try:
        from pyzbar.pyzbar import decode as _decode
    except ImportError:
        return ("ERROR: 识别二维码需要 pyzbar\n"
                "安装：pip install pyzbar\n"
                "系统依赖：\n"
                "  Windows: 自动捆绑\n"
                "  Linux: sudo apt install libzbar0\n"
                "  macOS: brew install zbar")

    try:
        im = Image.open(p)
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"

    try:
        results = _decode(im)
    except Exception as exc:
        return f"ERROR: 解码失败: {exc}"

    if not results:
        return f"{path} 中未识别到二维码/条形码"

    lines = [f"识别到 {len(results)} 个码:", ""]
    for i, r in enumerate(results, 1):
        typ = r.type
        data = r.data.decode("utf-8", errors="replace")
        rect = r.rect
        lines.append(f"[{i}] 类型: {typ}")
        lines.append(f"    内容: {data[:500]}")
        lines.append(f"    位置: {rect.width}×{rect.height} "
                     f"@ ({rect.left},{rect.top})")
        lines.append("")
    return "\n".join(lines)