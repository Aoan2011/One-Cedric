"""正文提取：优先 trafilatura，fallback readability-lxml，最后启发式。"""
from __future__ import annotations

import html as _html
import re


def extract_main_content(html: str, url: str = "",
                         max_chars: int = 3000) -> tuple:
    if not html:
        return "", "empty"

    try:
        import trafilatura
        text = trafilatura.extract(
            html, url=url or None,
            include_comments=False, include_tables=False,
            include_images=False, include_links=False,
            favor_precision=True,
            output_format="txt",
        )
        if text and len(text) >= 100:
            return _truncate(text, max_chars), "trafilatura"
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from readability import Document
        doc = Document(html)
        summary_html = doc.summary(html_partial=True)
        text = html_to_text(summary_html)
        if text and len(text) >= 100:
            return _truncate(text, max_chars), "readability"
    except ImportError:
        pass
    except Exception:
        pass

    return _truncate(_heuristic_extract(html), max_chars), "heuristic"


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        orig = len(text)
        text = text[:max_chars] + f"\n…（截断，原始 {orig} 字符）"
    return text


def html_to_text(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(?:p|div|h[1-6]|li|tr|section|article)>", "\n",
                  html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    html = _html.unescape(html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n +", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _heuristic_extract(html: str) -> str:
    blocks: list = []
    for m in re.finditer(
        r"<(p|article|section|div)[^>]*>(.*?)</\1>",
        html, flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = m.group(2)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = _html.unescape(raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if len(raw) >= 40:
            blocks.append(raw)

    if not blocks:
        return html_to_text(html)

    out: list = []
    seen: set = set()
    for b in blocks:
        key = b[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return "\n".join(out)