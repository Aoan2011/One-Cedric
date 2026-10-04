"""网络工具：web_fetch / http_request / web_search / web_research。

- 多引擎聚合（Bing 国内 + Bing 国际 + 百度）
- BM25 语义重排 + 位置分融合
- trafilatura / readability 正文提取
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Set
from urllib.parse import urljoin, urlparse, urlunparse

import requests

try:
    from bs4 import BeautifulSoup
    from bs4.element import Tag
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from ..config import (
    MAX_WEB_BYTES, WEB_TIMEOUT,
    MAX_HTTP_RESP_BYTES, MAX_HTTP_BODY_BYTES, HTTP_DEFAULT_TIMEOUT,
    MAX_SEARCH_QUERY_LEN,
)
from .extract import extract_main_content
from .rerank import bm25_scores, fuse, url_dedup_keep_best
from .sandbox import _as_int


def _extract_text_from_html(html: str) -> str:
    from .extract import html_to_text
    return html_to_text(html)


def _url_safety_check(url: str) -> str:
    try:
        u = urlparse(url)
    except (ValueError, TypeError):
        return "URL 格式错误。"
    if u.scheme not in ("http", "https"):
        return f"不支持的协议: {u.scheme}"
    host = u.hostname
    if not host:
        return "URL 缺少主机名。"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return f"DNS 解析失败: {exc}"
    for _f, _s, _p, _c, sockaddr in infos:
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast):
            return f"拒绝访问私有/本地地址: {ip}"
    return ""


def web_fetch(url: str, max_bytes=None, raw=False) -> str:
    if not url or not isinstance(url, str):
        return "ERROR: URL 不能为空。"
    err = _url_safety_check(url)
    if err:
        return f"ERROR: {err}"
    limit = _as_int(max_bytes, MAX_WEB_BYTES)
    if limit <= 0 or limit > MAX_WEB_BYTES * 5:
        limit = MAX_WEB_BYTES
    try:
        resp = requests.get(url, timeout=WEB_TIMEOUT, allow_redirects=True,
                            headers={"User-Agent": "OneCedric/1.0"})
    except requests.exceptions.RequestException as exc:
        return f"ERROR: 请求失败: {exc}"
    if resp.status_code >= 400:
        return f"ERROR: HTTP {resp.status_code} {resp.reason}"
    body = resp.content[:limit]
    enc = resp.encoding or "utf-8"
    try:
        text = body.decode(enc, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    ct = (resp.headers.get("content-type") or "").lower()
    if "html" in ct and not raw:
        text, _ = extract_main_content(text, url=url, max_chars=limit)
    header = (f"URL: {url}\n状态: {resp.status_code}  "
              f"类型: {ct or '未知'}  大小: {len(resp.content)} bytes")
    if len(resp.content) > limit:
        header += f"（截断到前 {limit} bytes）"
    return header + "\n\n" + text


def http_request(url: str, method: str = "GET", headers: dict | None = None,
                 body: str | None = None, timeout=None) -> str:
    if not url or not isinstance(url, str):
        return "ERROR: URL 不能为空。"
    err = _url_safety_check(url)
    if err:
        return f"ERROR: {err}"
    method = (method or "GET").upper().strip()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH",
                       "HEAD", "OPTIONS"):
        return f"ERROR: 不支持的 HTTP 方法: {method}"
    try:
        to = int(timeout) if timeout else HTTP_DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        to = HTTP_DEFAULT_TIMEOUT
    to = max(1, min(to, 120))
    hdrs = {"User-Agent": "OneCedric/1.0"}
    if isinstance(headers, dict):
        for k, v in headers.items():
            hdrs[str(k)] = str(v)
    if body and len(body.encode("utf-8")) > MAX_HTTP_BODY_BYTES:
        return f"ERROR: 请求体超过 {MAX_HTTP_BODY_BYTES} 字节上限。"
    try:
        resp = requests.request(method, url, headers=hdrs,
                                data=(body.encode("utf-8") if body else None),
                                timeout=to, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        return f"ERROR: 请求失败: {exc}"
    raw = resp.content[:MAX_HTTP_RESP_BYTES]
    enc = resp.encoding or "utf-8"
    try:
        text = raw.decode(enc, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    ct = (resp.headers.get("content-type") or "").lower()
    if "json" in ct:
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False,
                              indent=2)
        except (json.JSONDecodeError, ValueError):
            pass
    elif "html" in ct:
        text, _ = extract_main_content(text, url=url,
                                       max_chars=MAX_HTTP_RESP_BYTES)
    resp_headers = "\n".join(f"  {k}: {v}"
                              for k, v in resp.headers.items())
    header = (f"URL: {url}\n方法: {method}  "
              f"状态: {resp.status_code} {resp.reason}\n"
              f"类型: {ct or '未知'}  大小: {len(resp.content)} bytes\n"
              f"响应头:\n{resp_headers}")
    if len(resp.content) > MAX_HTTP_RESP_BYTES:
        header += f"\n（响应体已截断到前 {MAX_HTTP_RESP_BYTES} bytes）"
    return header + "\n\n--- 响应体 ---\n" + text


# ═══════════════════════════════════════════════════════════════════════ #
# 搜索
# ═══════════════════════════════════════════════════════════════════════ #

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SEARCH_TIMEOUT = 15
SEARCH_DELAY = 0.6
BING_WEIGHT = 65.0
BAIDU_WEIGHT = 35.0

DEFAULT_ENGINES = ("bing_cn", "bing_intl", "baidu")
ENGINE_WEIGHTS = {
    "bing_cn": BING_WEIGHT / 2,
    "bing_intl": BING_WEIGHT / 2,
    "baidu": BAIDU_WEIGHT,
}

RESEARCH_MODES = {
    "fast":     {"top_n": 5, "max_chars": 1500, "fetch_timeout": 10},
    "balanced": {"top_n": 8, "max_chars": 2500, "fetch_timeout": 12},
    "deep":     {"top_n": 12, "max_chars": 5000, "fetch_timeout": 18},
}


@dataclass
class SearchResult:
    source: str
    rank: int
    title: str
    url: str
    snippet: str = ""
    score: float = 0.0
    sources: Set[str] = field(default_factory=set)
    bm25: float = 0.0
    final_score: float = 0.0


@dataclass
class AggregateInfo:
    source: str
    kind: str
    title: str = ""
    text: str = ""
    url: str = ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(fragment=""))


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_bing_internal(url: str) -> bool:
    h = _host(url)
    if not h:
        return True
    return h.endswith("bing.com") or h.endswith("bing.net")


def _is_baidu_internal(url: str) -> bool:
    if "link?url=" in url:
        return False
    h = _host(url)
    if not h:
        return True
    return h.endswith("baidu.com") or h.endswith("baiducontent.com")


def _soup(html: str):
    if not _HAS_BS4:
        return None
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _bing_aggregate_kind(node: Tag) -> str:
    classes = set(node.get("class") or [])
    for c in ("b_ans", "b_rich", "b_entityTP", "b_vidAns"):
        if c in classes:
            return c
    if node.select_one(".b_algoheader"):
        return "b_algoheader"
    if node.select_one(".b_ans, .b_rich, .b_entityTP, .b_vidAns"):
        return "b_nested_aggregate"
    return ""


def _baidu_aggregate_kind(node: Tag) -> str:
    classes = set(node.get("class") or [])
    if "result-op" in classes:
        return "result-op"
    if "c-group-wrapper" in classes:
        return "c-group-wrapper"
    for c in classes:
        if c.startswith("op-") and len(c) > 3:
            return c
    if node.get("mu") or node.get("data-tools"):
        return "data-tools"
    if node.select_one(".result-op, .op-weather, .op-stock, "
                       ".op-calendar, .c-group-wrapper"):
        return "nested_aggregate"
    return ""


def _make_bing_aggregate(node: Tag, source_name: str) -> AggregateInfo:
    kind = _bing_aggregate_kind(node)
    title_el = node.select_one(
        "h2, .b_algoheader, .b_ansTitle, .b_entityTitle")
    title = _clean_text(title_el.get_text()) if title_el else ""
    text = _clean_text(node.get_text())
    a = node.select_one("a[href]")
    url = urljoin("https://www.bing.com", a.get("href")) \
        if a and a.get("href") else ""
    return AggregateInfo(source=source_name,
                         kind=kind or "b_aggregate",
                         title=title, text=text, url=url)


def _make_baidu_aggregate(node: Tag) -> AggregateInfo:
    kind = _baidu_aggregate_kind(node)
    title_el = node.select_one(
        "h3, .op-weather-title, .c-group-title")
    title = _clean_text(title_el.get_text()) if title_el else ""
    text = _clean_text(node.get_text())
    a = node.select_one("a[href]")
    url = urljoin("https://www.baidu.com", a.get("href")) \
        if a and a.get("href") else ""
    return AggregateInfo(source="baidu",
                         kind=kind or "baidu_aggregate",
                         title=title, text=text, url=url)


def _fetch_bing(query: str, market: str, source_name: str,
                domain: str, timeout: int):
    url = f"https://{domain}/search"
    params = {
        "q": query, "count": 20, "first": 1, "mkt": market,
        "setlang": "zh-Hans" if market == "zh-CN" else "en",
    }
    resp = requests.get(url, params=params, headers=SEARCH_HEADERS,
                        timeout=timeout)
    resp.raise_for_status()
    soup = _soup(resp.text)
    if soup is None:
        return [], []

    results: list = []
    aggregates: list = []
    seen: set = set()

    for li in soup.select("li.b_algo, li.b_ans, li.b_rich, "
                          "li.b_entityTP, li.b_vidAns"):
        kind = _bing_aggregate_kind(li)
        if kind:
            aggregates.append(_make_bing_aggregate(li, source_name))
            continue
        if len(results) >= 20:
            continue
        a = li.select_one("h2 a")
        if not a:
            continue
        href = a.get("href")
        if not href:
            continue
        href = urljoin(url, href)
        if _is_bing_internal(href):
            continue
        key = _normalize_url(href)
        if not key or key in seen:
            continue
        seen.add(key)
        title = _clean_text(a.get_text())
        snippet_el = li.select_one(
            ".b_caption p, .b_snippet, .b_lineclamp2, p")
        snippet = _clean_text(snippet_el.get_text()) if snippet_el else ""
        results.append(SearchResult(source_name, len(results) + 1,
                                     title, href, snippet))

    return results, aggregates


def _fetch_baidu(query: str, timeout: int):
    results: list = []
    aggregates: list = []
    seen: set = set()

    for pn in (0, 10):
        url = "https://www.baidu.com/s"
        params = {"wd": query, "pn": pn, "rn": 10, "ie": "utf-8"}
        resp = requests.get(url, params=params, headers=SEARCH_HEADERS,
                            timeout=timeout)
        resp.raise_for_status()
        soup = _soup(resp.text)
        if soup is None:
            break

        for div in soup.select(
                "div#content_left > div.result, "
                "div#content_left > div.c-container"):
            kind = _baidu_aggregate_kind(div)
            if kind:
                aggregates.append(_make_baidu_aggregate(div))
                continue
            if len(results) >= 20:
                continue
            a = div.select_one("h3 a") or div.select_one("a[href]")
            if not a:
                continue
            href = a.get("href")
            if not href:
                continue
            href = urljoin(url, href)
            if _is_baidu_internal(href):
                continue
            key = _normalize_url(href)
            if not key or key in seen:
                continue
            seen.add(key)
            title = _clean_text(a.get_text())
            snippet_el = div.select_one(
                ".c-abstract, .content-right_8Zs40, .c-span-last, "
                ".c-color-text, .c-gap-top-small span")
            snippet = _clean_text(snippet_el.get_text()) \
                if snippet_el else ""
            results.append(SearchResult("baidu", len(results) + 1,
                                         title, href, snippet))

        if len(results) >= 20:
            break
        time.sleep(SEARCH_DELAY)

    return results, aggregates


def _merge_and_rerank(query: str,
                      sources: Dict[str, list],
                      weights: Dict[str, float]) -> list:
    merged: Dict[str, SearchResult] = {}
    for source, results in sources.items():
        weight = weights.get(source, 0.0)
        for r in results:
            key = _normalize_url(r.url)
            if not key:
                continue
            if key not in merged:
                merged[key] = SearchResult(
                    source=source, rank=r.rank, title=r.title,
                    url=r.url, snippet=r.snippet, sources=set(),
                )
            merged[key].sources.add(source)
            merged[key].score += weight / r.rank

    items = list(merged.values())
    if not items:
        return items

    docs = [f"{it.title} {it.snippet}" for it in items]
    bm = bm25_scores(query, docs)
    for it, s in zip(items, bm):
        it.bm25 = s

    pos_scores = [it.score for it in items]
    fused = fuse(pos_scores, bm, bm25_weight=0.35)
    for it, s in zip(items, fused):
        it.final_score = s

    items.sort(key=lambda x: x.final_score, reverse=True)
    return items


def _format_search_output(query: str, ranked: list,
                          sources: Dict[str, list],
                          aggregates: Dict[str, list],
                          weights: Dict[str, float],
                          max_results: int,
                          include_aggregates: bool,
                          errors: list) -> str:
    lines: list = []
    counts = " · ".join(f"{name}({len(items)})"
                        for name, items in sources.items())
    lines.append(f"搜索: {query}    {counts}")
    if errors:
        lines.append(f"[警告] {' | '.join(errors)}")
    lines.append("")

    if not ranked:
        lines.append("（未找到自然结果）")
        return "\n".join(lines)

    n = min(max_results, len(ranked))
    lines.append(f"Top {n}：")
    for i, r in enumerate(ranked[:n], 1):
        src = "/".join(sorted(r.sources))
        lines.append(f"{i}. [{src}] {r.title}")
        snippet = r.snippet[:120] + ("…" if len(r.snippet) > 120 else "")
        lines.append(f"   {r.url}")
        if snippet:
            lines.append(f"   {snippet}")
    lines.append("")

    if include_aggregates:
        flat: list = []
        for name in aggregates:
            flat.extend(aggregates[name])
        if flat:
            lines.append("── 知识卡片 ──")
            for a in flat[:3]:
                title = (a.title or "")[:80]
                text = (a.text or "")[:200]
                lines.append(f"[{a.source}/{a.kind}] {title}")
                if text:
                    lines.append(f"  {text}")
            lines.append("")

    return "\n".join(lines)


def web_search(query: str,
               max_results=None,
               engines: list | None = None,
               include_aggregates: bool = True,
               timeout=None) -> str:
    if not _HAS_BS4:
        return ("ERROR: web_search 需要 beautifulsoup4 和 lxml。\n"
                "请运行：pip install beautifulsoup4 lxml")
    if not query or not isinstance(query, str):
        return "ERROR: query 不能为空。"
    q = query.strip()
    if len(q) > MAX_SEARCH_QUERY_LEN:
        q = q[:MAX_SEARCH_QUERY_LEN]

    limit = _as_int(max_results, 13)
    if limit <= 0:
        limit = 13
    limit = min(limit, 30)

    try:
        to = int(timeout) if timeout else SEARCH_TIMEOUT
    except (TypeError, ValueError):
        to = SEARCH_TIMEOUT
    to = max(3, min(to, 60))

    if engines:
        wanted = [e for e in engines if e in DEFAULT_ENGINES]
        if not wanted:
            return f"ERROR: engines 无效。可选: {', '.join(DEFAULT_ENGINES)}"
    else:
        wanted = list(DEFAULT_ENGINES)

    sources: Dict[str, list] = {}
    aggregates: Dict[str, list] = {}
    errors: list = []

    for name in wanted:
        try:
            if name == "bing_cn":
                res, agg = _fetch_bing(q, "zh-CN", "bing_cn",
                                        "cn.bing.com", to)
            elif name == "bing_intl":
                res, agg = _fetch_bing(q, "en-US", "bing_intl",
                                        "www.bing.com", to)
            elif name == "baidu":
                res, agg = _fetch_baidu(q, to)
            else:
                continue
            sources[name] = res
            aggregates[name] = agg
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}")
            sources[name] = []
            aggregates[name] = []

    if not any(sources.values()):
        return (f"搜索 {q!r} 失败。\n"
                f"错误: {'; '.join(errors) if errors else '所有引擎都无结果'}\n"
                f"可能原因：网络不通 / 被反爬 / 引擎结构变化。")

    weights = {name: ENGINE_WEIGHTS.get(name, 0.0) for name in wanted}
    ranked = _merge_and_rerank(q, sources, weights)

    return _format_search_output(
        query=q, ranked=ranked, sources=sources,
        aggregates=aggregates, weights=weights,
        max_results=limit,
        include_aggregates=include_aggregates, errors=errors,
    )


def _fetch_page(url: str, max_chars: int, timeout: int) -> tuple:
    err = _url_safety_check(url)
    if err:
        return "", f"URL 拒绝: {err}"
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers=SEARCH_HEADERS)
    except requests.exceptions.RequestException as exc:
        return "", f"请求失败: {exc}"
    if resp.status_code >= 400:
        return "", f"HTTP {resp.status_code}"
    ct = (resp.headers.get("content-type") or "").lower()
    if not any(k in ct for k in ("html", "text", "xml", "json")):
        return "", f"不支持的内容类型: {ct or '未知'}"
    body = resp.content[:MAX_WEB_BYTES * 2]
    enc = resp.encoding or "utf-8"
    try:
        html = body.decode(enc, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")
    if "json" in ct:
        try:
            text = json.dumps(json.loads(html), ensure_ascii=False,
                              indent=2)
            if len(text) > max_chars:
                text = text[:max_chars] + "…"
            return text, "json"
        except (json.JSONDecodeError, ValueError):
            pass
    text, extractor = extract_main_content(html, url=url,
                                            max_chars=max_chars)
    if not text.strip():
        return "", "正文提取为空"
    return text, extractor


def web_research(query: str,
                 top_n=None,
                 max_chars_per_page=None,
                 engines: list | None = None,
                 fetch_timeout=None,
                 mode: str = "balanced") -> str:
    if not _HAS_BS4:
        return ("ERROR: web_research 需要 beautifulsoup4 和 lxml。\n"
                "请运行：pip install beautifulsoup4 lxml")
    if not query or not isinstance(query, str):
        return "ERROR: query 不能为空。"
    q = query.strip()
    if len(q) > MAX_SEARCH_QUERY_LEN:
        q = q[:MAX_SEARCH_QUERY_LEN]

    mode = (mode or "balanced").lower()
    if mode not in RESEARCH_MODES:
        mode = "balanced"
    preset = RESEARCH_MODES[mode]

    try:
        n = int(top_n) if top_n else preset["top_n"]
    except (TypeError, ValueError):
        n = preset["top_n"]
    n = max(1, min(n, 15))

    try:
        mc = int(max_chars_per_page) if max_chars_per_page \
            else preset["max_chars"]
    except (TypeError, ValueError):
        mc = preset["max_chars"]
    mc = max(500, min(mc, 12000))

    try:
        ft = int(fetch_timeout) if fetch_timeout \
            else preset["fetch_timeout"]
    except (TypeError, ValueError):
        ft = preset["fetch_timeout"]
    ft = max(3, min(ft, 60))

    if engines:
        wanted = [e for e in engines if e in DEFAULT_ENGINES]
        if not wanted:
            return f"ERROR: engines 无效。可选: {', '.join(DEFAULT_ENGINES)}"
    else:
        wanted = list(DEFAULT_ENGINES)

    sources: Dict[str, list] = {}
    aggregates: Dict[str, list] = {}
    errors: list = []

    for name in wanted:
        try:
            if name == "bing_cn":
                res, agg = _fetch_bing(q, "zh-CN", "bing_cn",
                                        "cn.bing.com", SEARCH_TIMEOUT)
            elif name == "bing_intl":
                res, agg = _fetch_bing(q, "en-US", "bing_intl",
                                        "www.bing.com", SEARCH_TIMEOUT)
            elif name == "baidu":
                res, agg = _fetch_baidu(q, SEARCH_TIMEOUT)
            else:
                continue
            sources[name] = res
            aggregates[name] = agg
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}")
            sources[name] = []
            aggregates[name] = []

    if not any(sources.values()):
        return (f"搜索 {q!r} 失败。\n"
                f"错误: {'; '.join(errors) if errors else '所有引擎都无结果'}")

    weights = {name: ENGINE_WEIGHTS.get(name, 0.0) for name in wanted}
    ranked = _merge_and_rerank(q, sources, weights)

    urls = [r.url for r in ranked]
    scores = [r.final_score for r in ranked]
    keep_idx = url_dedup_keep_best(urls, scores, keep=n)
    targets = [ranked[i] for i in keep_idx]

    if not targets:
        return (f"搜索 {q!r} 有结果，但无可抓取的 URL。\n"
                f"Top: {', '.join(urls[:3])}")

    fetched: dict = {}
    with ThreadPoolExecutor(max_workers=min(3, len(targets))) as pool:
        futures = {
            pool.submit(_fetch_page, t.url, mc, ft): t
            for t in targets
        }
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                text, tag = fut.result(timeout=ft + 5)
            except Exception as exc:
                text, tag = "", f"内部错误: {exc}"
            fetched[t.url] = (text, tag)

    lines: list = []
    lines.append(f"# 研究: {q}    [mode={mode}]")
    counts = " · ".join(f"{name}({len(sources[name])})"
                        for name in wanted)
    lines.append(f"引擎: {counts}")
    if errors:
        lines.append(f"[部分失败] {' | '.join(errors)}")
    lines.append("")

    flat_agg: list = []
    for name in aggregates:
        flat_agg.extend(aggregates[name])
    if flat_agg:
        lines.append("## 知识卡片")
        for a in flat_agg[:2]:
            lines.append(
                f"- [{a.source}/{a.kind}] {(a.title or '')[:100]}")
            if a.text:
                lines.append(f"  {a.text[:300]}")
        lines.append("")

    lines.append(f"## 网页正文（{len(fetched)} 页）")
    lines.append("")
    for i, t in enumerate(targets, 1):
        text, tag = fetched.get(t.url, ("", "未抓取"))
        src = "/".join(sorted(t.sources))
        lines.append(f"### [{i}] {t.title}")
        lines.append(f"{t.url}")
        lines.append(f"[{src} · {tag}]")
        lines.append("")
        if tag.startswith(("请求", "HTTP", "URL", "不支持",
                            "正文", "内部")):
            lines.append(f"[抓取失败] {tag}")
        else:
            lines.append(text)
        lines.append("")

    if not any(fetched.get(t.url, ("", ""))[0] for t in targets):
        lines.append("**所有页面都抓取失败。**"
                     "建议改用 `web_fetch` 直接访问 URL。")

    return "\n".join(lines)