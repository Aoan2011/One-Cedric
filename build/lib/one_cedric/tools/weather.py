"""wttr.in 天气查询。

wttr.in 是一个纯文本天气服务，支持：
- 一行简版：?format=3
- 完整 ASCII 图：无 format 参数
- JSON：?format=j1
- 自定义格式串：?format=%l:+%c+%t+%w
- 多语言：?lang=zh
"""
from __future__ import annotations

from urllib.parse import quote

import requests

USER_AGENT = "curl/8.0.0"        # wttr.in 对 curl UA 返回纯文本
BASE = "https://wttr.in"
DEFAULT_TIMEOUT = 15


def get_weather(location: str, format: str = "3", lang: str = "",
                timeout: int = DEFAULT_TIMEOUT) -> str:
    if not location or not str(location).strip():
        return "ERROR: location 不能为空。"

    loc = str(location).strip()
    loc_enc = quote(loc, safe="")

    params: list[str] = []
    if format is not None and str(format) != "":
        params.append(f"format={quote(str(format), safe='')}")
    if lang:
        params.append(f"lang={quote(str(lang), safe='')}")

    qs = "&".join(params)
    url = f"{BASE}/{loc_enc}" + (f"?{qs}" if qs else "")

    try:
        t = max(3, min(int(timeout), 60))
    except (TypeError, ValueError):
        t = DEFAULT_TIMEOUT

    try:
        r = requests.get(
            url,
            timeout=t,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
    except requests.exceptions.Timeout:
        return f"ERROR: 请求超时\nURL: {url}"
    except requests.exceptions.RequestException as exc:
        return f"ERROR: 请求失败: {exc}\nURL: {url}"

    if r.status_code >= 400:
        return f"ERROR: HTTP {r.status_code} {r.reason}\nURL: {url}"

    text = r.text.strip()
    if not text:
        return f"ERROR: wttr.in 返回为空\nURL: {url}"

    low = text[:200].lower()
    if low.startswith("<!doctype") or low.startswith("<html"):
        return (
            f"ERROR: wttr.in 返回了 HTML（可能限流，稍后再试）\n"
            f"URL: {url}\n---\n{text[:500]}"
        )

    return f"URL: {url}\n---\n{text}"