"""轻量语义重排：BM25（中英文 2-gram）+ 位置分融合。"""
from __future__ import annotations

import math
import re
from collections import Counter


def _tokenize(text: str) -> list:
    if not text:
        return []
    text = text.lower()
    tokens: list = []
    for m in re.finditer(r"[a-z0-9]+", text):
        tokens.append(m.group(0))
    for m in re.finditer(r"[\u4e00-\u9fff]+", text):
        s = m.group(0)
        if len(s) == 1:
            tokens.append(s)
        else:
            for i in range(len(s) - 1):
                tokens.append(s[i:i + 2])
    return tokens


def bm25_scores(query: str, docs: list,
                k1: float = 1.5, b: float = 0.75) -> list:
    if not docs:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return [0.0] * len(docs)

    tokenized = [_tokenize(d) for d in docs]
    N = len(tokenized)
    avgdl = sum(len(d) for d in tokenized) / max(N, 1) or 1.0

    df: Counter = Counter()
    for d in tokenized:
        for t in set(d):
            df[t] += 1

    scores: list = []
    for d in tokenized:
        dl = len(d) or 1
        tf = Counter(d)
        s = 0.0
        for qt in q_tokens:
            if qt not in tf:
                continue
            idf = math.log((N - df[qt] + 0.5) / (df[qt] + 0.5) + 1.0)
            num = tf[qt] * (k1 + 1)
            den = tf[qt] + k1 * (1 - b + b * dl / avgdl)
            s += idf * num / den
        scores.append(s)
    return scores


def fuse(position_scores: list,
         bm25_list: list,
         bm25_weight: float = 0.35) -> list:
    n = len(position_scores)
    if n == 0:
        return []
    max_pos = max(position_scores) or 1.0
    max_bm = max(bm25_list) or 1.0
    out: list = []
    for i in range(n):
        pos_n = position_scores[i] / max_pos
        bm_n = bm25_list[i] / max_bm
        out.append((1 - bm25_weight) * pos_n + bm25_weight * bm_n)
    return out


def url_dedup_keep_best(urls: list, scores: list,
                        keep: int) -> list:
    if not urls:
        return []
    order = sorted(range(len(urls)), key=lambda i: -scores[i])
    seen_paths: list = []
    picked: list = []

    for i in order:
        if len(picked) >= keep:
            break
        u = urls[i]
        m = re.match(r"https?://([^/]+)(/[^/]+/[^/]+)?", u)
        key = (m.group(1) + (m.group(2) or "")).lower() if m else u.lower()
        dup = False
        for k in seen_paths:
            if key == k or key.startswith(k + "/") or k.startswith(key + "/"):
                dup = True
                break
        if dup:
            continue
        seen_paths.append(key)
        picked.append(i)
    return picked