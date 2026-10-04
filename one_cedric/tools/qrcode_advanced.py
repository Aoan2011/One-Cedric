"""高级二维码：艺术风格 / 渐变 / logo 嵌入 / 圆形点阵 / 批量。

依赖：qrcode（必需），Pillow（图片处理）
"""
from __future__ import annotations

import math
from pathlib import Path

from .sandbox import _resolve_path


def _deps():
    try:
        import qrcode
    except ImportError:
        return None, None, "ERROR: 需要 qrcode（pip install qrcode[pil]）"
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        return qrcode, (Image, ImageDraw, ImageFilter, ImageFont), ""
    except ImportError:
        return qrcode, None, "ERROR: 需要 Pillow（pip install Pillow）"


def _hex_to_rgb(h: str) -> tuple:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _make_qr(qrcode, content: str, error_level: str = "H",
             box_size: int = 10, border: int = 4):
    levels = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    lvl = levels.get((error_level or "H").upper(),
                      qrcode.constants.ERROR_CORRECT_H)
    qr = qrcode.QRCode(
        version=None, error_correction=lvl,
        box_size=max(2, int(box_size)), border=max(1, int(border)))
    qr.add_data(content)
    qr.make(fit=True)
    return qr


def qrcode_styled(content: str, out: str = "",
                  style: str = "rounded",
                  fg: str = "#000000", bg: str = "#ffffff",
                  gradient_end: str = "",
                  logo: str = "",
                  logo_scale: int = 22,
                  size: int = 10, border: int = 4,
                  error_level: str = "H",
                  caption: str = "",
                  caption_color: str = "#333333",
                  module_radius: float = 0.5,
                  root: Path | None = None):
    """生成风格化二维码。

    style: square / rounded / circle / dots / gradient / art
    """
    qrcode, pil, err = _deps()
    if err:
        return "", False, err
    if pil is None:
        return "", False, "ERROR: 需要 Pillow"
    if not content:
        return "", False, "ERROR: content 不能为空"
    if root is None:
        return "", False, "ERROR: 需要 root"

    if not out:
        safe = "".join(c if c.isalnum() else "_"
                       for c in content[:16])
        out = f"qr_{style}_{safe}.png"

    out_p, perr = _resolve_path(root, out)
    if perr:
        return "", False, perr

    if logo:
        lp, lerr = _resolve_path(root, logo)
        if lerr:
            return "", False, lerr
        if not lp.exists():
            return "", False, f"ERROR: logo 文件不存在: {logo}"

    if caption and not out_p.name.endswith(".png"):
        return "", False, "ERROR: caption 模式只支持 PNG"

    preview = [
        f"内容: {content[:120]}"
        + ("…" if len(content) > 120 else ""),
        f"输出: {out_p.relative_to(root)}",
        f"样式: {style}",
        f"前景: {fg}" + (f" → {gradient_end}" if gradient_end else ""),
        f"背景: {bg}",
        f"纠错: {error_level}  size: {size}  border: {border}",
    ]
    if logo:
        preview.append(f"Logo: {logo}（{logo_scale}% 大小）")
    if caption:
        preview.append(f"标题: {caption}")
    return "\n".join(preview), True, ""


def qrcode_styled_apply(content: str, out: str, style: str,
                        fg: str, bg: str, gradient_end: str,
                        logo: str, logo_scale: int,
                        size: int, border: int, error_level: str,
                        caption: str, caption_color: str,
                        module_radius: float, root: Path) -> str:
    qrcode, pil, err = _deps()
    if err:
        return err
    Image, ImageDraw, ImageFilter, ImageFont = pil

    qr = _make_qr(qrcode, content, error_level, size, border)
    matrix = qr.get_matrix()
    N = len(matrix)
    box = max(2, int(size))
    W = N * box
    H = N * box

    fg_rgb = _hex_to_rgb(fg)
    bg_rgb = _hex_to_rgb(bg)
    fg2_rgb = _hex_to_rgb(gradient_end) if gradient_end else fg_rgb

    style = (style or "rounded").lower()
    use_gradient = style in ("gradient", "art") or bool(gradient_end)
    use_circle = style in ("circle", "dots", "art")
    use_rounded = style in ("rounded", "art")

    logo_img = None
    if logo:
        try:
            lp, _ = _resolve_path(root, logo)
            logo_img = Image.open(lp).convert("RGBA")
        except Exception as exc:
            return f"ERROR: 加载 logo 失败: {exc}"

        scale = max(10, min(int(logo_scale), 35)) / 100.0
        max_dim = int(W * scale)
        logo_img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    canvas = Image.new("RGB", (W, H), bg_rgb)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)

    def _get_color(x: int, y: int):
        if not use_gradient:
            return fg_rgb
        t = (x + y) / (2 * max(1, N - 1))
        return _lerp(fg_rgb, fg2_rgb, max(0.0, min(1.0, t)))

    draw = ImageDraw.Draw(canvas)

    center_i = N // 2
    skip_r = 0
    if logo_img is not None:
        skip_r = math.ceil((logo_img.width / box) / 2) + 1

    for y in range(N):
        for x in range(N):
            if not matrix[y][x]:
                continue
            if logo_img is not None:
                if (abs(x - center_i) <= skip_r
                        and abs(y - center_i) <= skip_r):
                    continue
            cx0 = x * box
            cy0 = y * box
            cx1 = cx0 + box
            cy1 = cy0 + box
            color = _get_color(x, y)

            if use_circle:
                r = int(box * module_radius)
                cx = cx0 + box // 2
                cy = cy0 + box // 2
                shadow_draw.ellipse(
                    [cx - r + 1, cy - r + 1, cx + r + 1, cy + r + 1],
                    fill=(0, 0, 0, 40))
                draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                             fill=color)
            elif use_rounded:
                rad = int(box * module_radius * 0.5)
                draw.rounded_rectangle(
                    [cx0, cy0, cx1 - 1, cy1 - 1],
                    radius=rad, fill=color)
            else:
                draw.rectangle([cx0, cy0, cx1 - 1, cy1 - 1], fill=color)

    if use_circle:
        shadow = shadow.filter(ImageFilter.GaussianBlur(1.2))
        canvas = Image.alpha_composite(
            canvas.convert("RGBA"), shadow).convert("RGB")
        draw = ImageDraw.Draw(canvas)

    if logo_img is not None:
        cx = W // 2
        cy = H // 2
        lx = cx - logo_img.width // 2
        ly = cy - logo_img.height // 2
        pad = 6
        bg_box = [lx - pad, ly - pad,
                  lx + logo_img.width + pad,
                  ly + logo_img.height + pad]
        draw.rounded_rectangle(bg_box, radius=10, fill=bg_rgb)
        if logo_img.mode == "RGBA":
            canvas.paste(logo_img, (lx, ly), logo_img)
        else:
            canvas.paste(logo_img, (lx, ly))

    if caption:
        try:
            font = ImageFont.truetype("arial.ttf", max(14, box * 2))
        except Exception:
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans-Bold.ttf", max(14, box * 2))
            except Exception:
                font = ImageFont.load_default()

        cap_color = _hex_to_rgb(caption_color)
        tmp = Image.new("RGB", (1, 1))
        tmp_draw = ImageDraw.Draw(tmp)
        bbox = tmp_draw.textbbox((0, 0), caption, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        pad_top = 12
        new_h = H + th + pad_top + 12
        new_canvas = Image.new("RGB", (W, new_h), bg_rgb)
        new_canvas.paste(canvas, (0, 0))
        ndraw = ImageDraw.Draw(new_canvas)
        ndraw.text(((W - tw) // 2, H + pad_top),
                   caption, fill=cap_color, font=font)
        canvas = new_canvas

    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    try:
        canvas.save(out_p, "PNG", optimize=True)
    except Exception as exc:
        return f"ERROR: 保存失败: {exc}"

    return (f"已生成: {out_p.relative_to(root)}\n"
            f"尺寸: {canvas.width} × {canvas.height}\n"
            f"文件: {out_p.stat().st_size} bytes")


def qrcode_batch(items: list, out_dir: str = "qr_batch",
                 style: str = "rounded",
                 fg: str = "#000000", bg: str = "#ffffff",
                 gradient_end: str = "", size: int = 10,
                 error_level: str = "M",
                 root: Path | None = None):
    """批量生成二维码。

    items: [{"content": "...", "name": "..."}, ...] 或 ["text1", ...]
    """
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not items or not isinstance(items, list):
        return "", False, "ERROR: items 必须是非空数组"
    if len(items) > 200:
        return "", False, "ERROR: 单次最多 200 个"

    out_d, oerr = _resolve_path(root, out_dir)
    if oerr:
        return "", False, oerr

    normalized = []
    for i, it in enumerate(items):
        if isinstance(it, str):
            normalized.append({"content": it,
                                "name": f"qr_{i+1:03d}"})
        elif isinstance(it, dict):
            c = it.get("content") or it.get("text") or ""
            if not c:
                return "", False, f"ERROR: items[{i}] 缺少 content"
            normalized.append({
                "content": str(c),
                "name": str(it.get("name") or f"qr_{i+1:03d}"),
            })
        else:
            return "", False, f"ERROR: items[{i}] 类型错误"

    preview = [
        f"将生成 {len(normalized)} 个二维码",
        f"输出目录: {out_dir}",
        f"样式: {style}",
        "",
        "前 5 个：",
    ]
    for it in normalized[:5]:
        preview.append(f"  {it['name']}.png  ← "
                       f"{it['content'][:60]}")
    if len(normalized) > 5:
        preview.append(f"  ... 还有 {len(normalized) - 5} 个")

    return "\n".join(preview), True, ""


def qrcode_batch_apply(items: list, out_dir: str, style: str,
                       fg: str, bg: str, gradient_end: str,
                       size: int, error_level: str,
                       root: Path) -> str:
    qrcode, pil, err = _deps()
    if err:
        return err
    out_d, _ = _resolve_path(root, out_dir)
    out_d.mkdir(parents=True, exist_ok=True)

    count = 0
    errors = []
    for it in items:
        if isinstance(it, str):
            content = it
            name = f"qr_{count + 1:03d}"
        else:
            content = it.get("content") or ""
            name = it.get("name") or f"qr_{count + 1:03d}"
        try:
            qr = _make_qr(qrcode, content, error_level, size, 4)
            img = qr.make_image(fill_color=fg, back_color=bg)
            safe = "".join(c if c.isalnum() or c in "-_" else "_"
                           for c in name)[:60]
            out_p = out_d / f"{safe}.png"
            img.save(out_p, "PNG", optimize=True)
            count += 1
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    result = f"已生成 {count} 个二维码 → {out_dir}/"
    if errors:
        result += f"\n\n失败 {len(errors)} 个："
        for e in errors[:10]:
            result += f"\n  {e}"
    return result


def _esc_wifi(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace(":", "\\:")
            .replace('"', '\\"'))


def qrcode_wifi(ssid: str, password: str = "", encryption: str = "WPA",
                hidden: bool = False, style: str = "rounded",
                out: str = "", fg: str = "#000000",
                bg: str = "#ffffff", size: int = 10,
                root: Path | None = None):
    if not ssid:
        return "", False, "ERROR: ssid 不能为空"
    enc = (encryption or "WPA").upper()
    if enc not in ("WPA", "WEP", "NOPASS"):
        return "", False, ("ERROR: encryption 必须是 "
                            "WPA / WEP / NOPASS")
    if enc != "NOPASS" and not password:
        return "", False, "ERROR: 需要 password"

    if not out:
        safe = "".join(c if c.isalnum() else "_" for c in ssid)[:24]
        out = f"wifi_{safe}.png"

    content = f"WIFI:T:{enc};S:{_esc_wifi(ssid)};"
    if password:
        content += f"P:{_esc_wifi(password)};"
    if hidden:
        content += "H:true;"
    content += ";"
    return _wrap_structured(content, style, out, fg, bg, size, root,
                            label=f"Wi-Fi: {ssid} [{enc}]")


def qrcode_vcard(name: str, phone: str = "", email: str = "",
                 org: str = "", title: str = "", url: str = "",
                 address: str = "", note: str = "",
                 style: str = "rounded", out: str = "",
                 fg: str = "#000000", bg: str = "#ffffff",
                 size: int = 10, root: Path | None = None):
    if not name:
        return "", False, "ERROR: name 不能为空"
    if not out:
        safe = "".join(c if c.isalnum() else "_"
                       for c in name)[:24]
        out = f"vcard_{safe}.png"
    parts = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{name}"]
    if org:
        parts.append(f"ORG:{org}")
    if title:
        parts.append(f"TITLE:{title}")
    if phone:
        parts.append(f"TEL;TYPE=CELL:{phone}")
    if email:
        parts.append(f"EMAIL:{email}")
    if url:
        parts.append(f"URL:{url}")
    if address:
        parts.append(f"ADR:;;{address};;;;")
    if note:
        parts.append(f"NOTE:{note}")
    parts.append("END:VCARD")
    content = "\n".join(parts)
    return _wrap_structured(content, style, out, fg, bg, size, root,
                            label=f"名片: {name}")


def qrcode_email(to: str, subject: str = "", body: str = "",
                 style: str = "rounded", out: str = "",
                 fg: str = "#000000", bg: str = "#ffffff",
                 size: int = 10, root: Path | None = None):
    if not to:
        return "", False, "ERROR: to 不能为空"
    if not out:
        safe = "".join(c if c.isalnum() else "_" for c in to)[:24]
        out = f"email_{safe}.png"
    from urllib.parse import quote
    content = f"mailto:{to}"
    params = []
    if subject:
        params.append(f"subject={quote(subject)}")
    if body:
        params.append(f"body={quote(body)}")
    if params:
        content += "?" + "&".join(params)
    return _wrap_structured(content, style, out, fg, bg, size, root,
                            label=f"Email: {to}")


def qrcode_sms(phone: str, message: str = "",
               style: str = "rounded", out: str = "",
               fg: str = "#000000", bg: str = "#ffffff",
               size: int = 10, root: Path | None = None):
    if not phone:
        return "", False, "ERROR: phone 不能为空"
    if not out:
        safe = "".join(c if c.isalnum() or c == "+" else "_"
                       for c in phone)[:24]
        out = f"sms_{safe}.png"
    content = f"SMSTO:{phone}"
    if message:
        content += f":{message}"
    return _wrap_structured(content, style, out, fg, bg, size, root,
                            label=f"SMS: {phone}")


def qrcode_geo(lat: float, lng: float,
               style: str = "rounded", out: str = "",
               fg: str = "#000000", bg: str = "#ffffff",
               size: int = 10, root: Path | None = None):
    if not out:
        out = f"geo_{lat:.4f}_{lng:.4f}.png".replace("-", "n")
    content = f"geo:{lat},{lng}"
    return _wrap_structured(content, style, out, fg, bg, size, root,
                            label=f"坐标: {lat}, {lng}")


def _wrap_structured(content, style, out, fg, bg, size, root, label):
    """结构化二维码的公共入口。返回 4 元组（含 content）。"""
    qrcode, pil, err = _deps()
    if err:
        return "", False, err, ""
    if root is None:
        return "", False, "ERROR: 需要 root", ""

    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr, ""

    preview = [
        label,
        f"输出: {out_p.relative_to(root)}",
        f"样式: {style}",
        "",
        "内容预览：",
        content[:300] + ("…" if len(content) > 300 else ""),
    ]
    return "\n".join(preview), True, "", content