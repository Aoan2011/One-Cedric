"""文本高级处理：分词、词频、繁简转换、去重、相似度、清不可见字符。

依赖：jieba（中文分词）、opencc（繁简转换）—— 均按需
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def _read(text: str, file: str, root: Path | None):
    if file:
        if root is None:
            return None, "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return None, err
        if not p.exists():
            return None, f"ERROR: 文件不存在: {file}"
        try:
            return p.read_text(encoding="utf-8", errors="replace"), ""
        except OSError as exc:
            return None, f"ERROR: {exc}"
    if text:
        return text, ""
    return None, "ERROR: 需要 text 或 file"


def word_frequency(text: str = "", file: str = "",
                   top: int = 30, min_len: int = 2,
                   stopwords: str = "",
                   root: Path | None = None) -> str:
    raw, err = _read(text, file, root)
    if err:
        return err

    try:
        n = max(1, min(_as_int(top, 30), 500))
    except Exception:
        n = 30

    stop = set()
    if stopwords:
        stop = {w.strip() for w in stopwords.split(",") if w.strip()}

    eng = re.findall(r"[A-Za-z]{2,}", raw.lower())
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", raw)

    cjk_tokens = []
    for run in cjk_runs:
        L = max(2, min(_as_int(min_len, 2), 4))
        for i in range(len(run) - L + 1):
            cjk_tokens.append(run[i:i + L])

    counter = Counter(eng + cjk_tokens)
    for w in list(counter):
        if w in stop:
            del counter[w]

    lines = [f"总 token: {sum(counter.values())}",
             f"唯一 token: {len(counter)}",
             f"Top {n}:", ""]
    if counter:
        top_count = counter.most_common(1)[0][1]
        for w, c in counter.most_common(n):
            bar = "█" * max(1, int(c / max(1, top_count) * 20))
            lines.append(f"  {w:<20} {c:>5}  {bar}")
    return "\n".join(lines)


def tokenize(text: str = "", file: str = "",
             mode: str = "mix", root: Path | None = None) -> str:
    raw, err = _read(text, file, root)
    if err:
        return err

    mode = (mode or "mix").lower()
    tokens = []
    if mode in ("cn", "mix", "all"):
        try:
            import jieba
            tokens.extend(jieba.lcut(raw))
        except ImportError:
            if mode in ("cn", "all"):
                return ("ERROR: 中文分词需要 jieba"
                        "（pip install jieba）\n或改用 mode=en")
    if mode in ("en", "mix", "all"):
        tokens.extend(re.findall(r"[A-Za-z]+", raw))

    if mode == "en":
        tokens = re.findall(r"[A-Za-z]+", raw)

    tokens = [t.strip() for t in tokens if t.strip()]
    lines = [f"模式: {mode}", f"token 数: {len(tokens)}", ""]
    lines.append(" ".join(tokens[:200]))
    if len(tokens) > 200:
        lines.append(f"\n... 还有 {len(tokens) - 200} 个")
    return "\n".join(lines)


def simplify_chinese(text: str = "", file: str = "",
                     direction: str = "t2s",
                     root: Path | None = None) -> str:
    raw, err = _read(text, file, root)
    if err:
        return err

    try:
        import opencc
    except ImportError:
        return ("ERROR: 需要 opencc"
                "（pip install opencc-python-reimplemented）")

    d = (direction or "t2s").lower()
    config_map = {
        "t2s": "t2s",
        "s2t": "s2t",
        "t2s_p": "tw2sp",
        "s2tw": "s2tw",
        "s2hk": "s2hk",
    }
    cfg = config_map.get(d)
    if not cfg:
        return f"ERROR: direction 必须是 {', '.join(config_map.keys())}"

    try:
        converter = opencc.OpenCC(cfg)
        result = converter.convert(raw)
    except Exception as exc:
        return f"ERROR: 转换失败: {exc}"

    return f"方向: {d}\n长度: {len(raw)} → {len(result)}\n---\n{result}"


def dedupe_lines(text: str = "", file: str = "",
                 case_insensitive: bool = False,
                 strip_whitespace: bool = True,
                 keep_order: bool = True,
                 root: Path | None = None) -> str:
    raw, err = _read(text, file, root)
    if err:
        return err

    lines = raw.splitlines()
    seen: set = set()
    out: list = []
    removed = 0

    for line in lines:
        key = line
        if strip_whitespace:
            key = key.strip()
        if case_insensitive:
            key = key.lower()
        if not key:
            out.append(line)
            continue
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(line)

    if not keep_order:
        out = sorted(out)

    return (f"原始 {len(lines)} 行 → 去重 {len(out)} 行"
            f"（移除 {removed}）\n"
            f"---\n" + "\n".join(out))


def text_similarity(text1: str = "", text2: str = "",
                    file1: str = "", file2: str = "",
                    algorithm: str = "jaccard",
                    root: Path | None = None) -> str:
    def _load(t, f):
        if f:
            if root is None:
                return None, "ERROR: file 需要 root"
            p, err = _resolve_path(root, f)
            if err:
                return None, err
            if not p.exists():
                return None, f"ERROR: 文件不存在: {f}"
            try:
                return p.read_text(encoding="utf-8",
                                    errors="replace"), ""
            except OSError as exc:
                return None, f"ERROR: {exc}"
        return (t or ""), ""

    a, err = _load(text1, file1)
    if err:
        return err
    b, err = _load(text2, file2)
    if err:
        return err
    if not a or not b:
        return "ERROR: 需要两段文本"

    algo = (algorithm or "jaccard").lower()

    def _tokens(s):
        s = s.lower()
        eng = set(re.findall(r"[a-z0-9]+", s))
        cjk = set(re.findall(r"[\u4e00-\u9fff]", s))
        return eng | cjk

    ta, tb = _tokens(a), _tokens(b)

    if algo == "jaccard":
        inter = len(ta & tb)
        union = len(ta | tb)
        score = inter / union if union else 0
    elif algo == "dice":
        inter = len(ta & tb)
        denom = len(ta) + len(tb)
        score = 2 * inter / denom if denom else 0
    elif algo == "cosine":
        from collections import Counter as _Counter
        import math

        def _count(s):
            eng = re.findall(r"[a-z0-9]+", s.lower())
            cjk = re.findall(r"[\u4e00-\u9fff]", s)
            return _Counter(eng + cjk)

        ca, cb = _count(a), _count(b)
        keys = set(ca) | set(cb)
        dot = sum(ca[k] * cb[k] for k in keys)
        na = math.sqrt(sum(v * v for v in ca.values()))
        nb = math.sqrt(sum(v * v for v in cb.values()))
        score = dot / (na * nb) if na and nb else 0
    elif algo == "levenshtein":
        sa, sb = a[:2000], b[:2000]
        d = _levenshtein(sa, sb)
        score = 1 - d / max(len(sa), len(sb)) if max(len(sa), len(sb)) else 0
    else:
        return f"ERROR: 不支持的算法: {algo}"

    return (f"算法: {algo}\n"
            f"A: {len(a)} 字符  B: {len(b)} 字符\n"
            f"相似度: {score:.4f}（{score * 100:.1f}%）")


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                cur[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + (ca != cb),
            ))
        prev = cur
    return prev[-1]


def strip_invisible(text: str = "", file: str = "",
                    root: Path | None = None) -> str:
    raw, err = _read(text, file, root)
    if err:
        return err

    out: list = []
    removed = 0
    for ch in raw:
        cat = unicodedata.category(ch)
        code = ord(ch)
        if ch in "\n\t\r":
            out.append(ch)
            continue
        if cat in ("Cc", "Cf", "Co", "Cs"):
            removed += 1
            continue
        if code in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF):
            removed += 1
            continue
        out.append(ch)

    result = "".join(out)
    return (f"清除 {removed} 个不可见字符\n"
            f"长度: {len(raw)} → {len(result)}\n---\n{result}")