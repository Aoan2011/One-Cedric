"""文件编码检测：多库降级 + BOM 识别 + 常见编码嗅探。"""
from __future__ import annotations

import codecs
from pathlib import Path


BOM_SIGNATURES = [
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
]

COMMON_ENCODINGS = [
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
    "big5",
    "shift_jis",
    "euc-jp",
    "euc-kr",
    "iso-8859-1",
    "windows-1252",
    "cp1251",
    "koi8-r",
]


def _check_bom(raw: bytes) -> tuple:
    for bom, enc in BOM_SIGNATURES:
        if raw.startswith(bom):
            return enc, len(bom)
    return None, 0


def _try_decode(raw: bytes, enc: str) -> tuple:
    try:
        text = raw.decode(enc, errors="strict")
        return text, True
    except (UnicodeDecodeError, LookupError):
        return "", False


def _use_chardet(raw: bytes) -> tuple:
    try:
        import charset_normalizer as cn
        result = cn.from_bytes(raw).best()
        if result:
            return result.encoding or "utf-8", result.chaos
    except ImportError:
        pass
    try:
        import chardet
        result = chardet.detect(raw[:50000])
        enc = result.get("encoding") or "utf-8"
        conf = result.get("confidence", 0)
        if enc.lower() == "ascii":
            enc = "utf-8"
        return enc, conf
    except ImportError:
        return "", 0.0


def _cjk_ratio(text: str, sample_size: int = 2000) -> float:
    s = text[:sample_size]
    if not s:
        return 0.0
    cjk = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    return cjk / len(s)


def _replacement_ratio(text: str) -> float:
    if not text:
        return 0.0
    return text.count("\ufffd") / len(text)


def detect_encoding(raw: bytes, prefer: str = "") -> dict:
    if not raw:
        return {
            "encoding": "utf-8", "confidence": 1.0,
            "method": "empty", "bom": False,
            "bom_offset": 0, "candidates": [],
        }
    bom_enc, offset = _check_bom(raw)
    if bom_enc:
        return {
            "encoding": bom_enc, "confidence": 1.0,
            "method": "bom", "bom": True,
            "bom_offset": offset,
            "candidates": [(bom_enc, 1.0)],
        }
    sample = raw[:50000]
    if prefer:
        text, ok = _try_decode(sample, prefer)
        if ok and _replacement_ratio(text) < 0.01:
            return {
                "encoding": prefer, "confidence": 0.9,
                "method": "user-prefer", "bom": False,
                "bom_offset": 0, "candidates": [(prefer, 0.9)],
            }
    try:
        sample.decode("utf-8", errors="strict")
        return {
            "encoding": "utf-8", "confidence": 0.99,
            "method": "strict", "bom": False,
            "bom_offset": 0, "candidates": [("utf-8", 0.99)],
        }
    except UnicodeDecodeError:
        pass
    enc, conf = _use_chardet(sample)
    if enc and conf > 0.5:
        text, ok = _try_decode(sample, enc)
        if ok and _replacement_ratio(text) < 0.05:
            return {
                "encoding": enc, "confidence": conf,
                "method": "chardet", "bom": False,
                "bom_offset": 0, "candidates": [(enc, conf)],
            }
    candidates = []
    for e in COMMON_ENCODINGS:
        text, ok = _try_decode(sample, e)
        if not ok:
            continue
        repl = _replacement_ratio(text)
        score = (1 - repl)
        if e in ("gb18030", "gbk", "big5", "shift_jis",
                 "euc-jp", "euc-kr"):
            cjk_r = _cjk_ratio(text)
            score += cjk_r * 0.5
        candidates.append((e, score))
    if candidates:
        candidates.sort(key=lambda x: -x[1])
        best_enc, best_score = candidates[0]
        return {
            "encoding": best_enc,
            "confidence": min(0.85, best_score),
            "method": "heuristic", "bom": False,
            "bom_offset": 0, "candidates": candidates[:5],
        }
    return {
        "encoding": "iso-8859-1", "confidence": 0.3,
        "method": "fallback", "bom": False,
        "bom_offset": 0, "candidates": [("iso-8859-1", 0.3)],
    }


def read_text_auto(path: Path, prefer: str = "") -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"ok": False, "text": "", "encoding": "",
                "confidence": 0, "method": "", "size": 0,
                "error": str(exc)}
    info = detect_encoding(raw, prefer=prefer)
    enc = info["encoding"]
    offset = info.get("bom_offset", 0)
    try:
        text = raw[offset:].decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError) as exc:
        return {"ok": False, "text": "", "encoding": enc,
                "confidence": info["confidence"],
                "method": info["method"], "size": len(raw),
                "error": str(exc)}
    return {
        "ok": True, "text": text, "encoding": enc,
        "confidence": info["confidence"],
        "method": info["method"], "size": len(raw),
        "error": "",
    }