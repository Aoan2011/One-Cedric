"""文本 / 编码 / 时间 / 转换 handlers。"""
from __future__ import annotations

import importlib
from pathlib import Path


def _imp(name: str):
    return importlib.import_module(f".{name}", package=__package__)


def _require(args: dict, *keys: str) -> str:
    for k in keys:
        if k not in args or args[k] in ("", None):
            return f"ERROR: 缺少必需参数 {k}。"
    return ""


# ═══════════════════════════════════════════════════════════════════════ #
# 文本处理
# ═══════════════════════════════════════════════════════════════════════ #

def _regex_extract(root: Path, args: dict) -> str:
    err = _require(args, "pattern", "path")
    if err:
        return err
    mod = _imp("text")
    return mod.regex_extract(
        root, args["pattern"], args["path"],
        file_pattern=args.get("file_pattern", "*"),
        unique=bool(args.get("unique", True)),
        max_results=args.get("max_results"),
    )


def _code_stats(root: Path, args: dict) -> str:
    mod = _imp("text")
    return mod.code_stats(
        root, path=args.get("path", "."),
        exclude=args.get(
            "exclude",
            "node_modules,__pycache__,.git,venv,.venv,dist,build"),
    )


def _markdown_toc(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("text")
    return mod.markdown_toc(root, args["path"],
                             max_level=args.get("max_level"))


def _template_render(root: Path, args: dict) -> str:
    err = _require(args, "template", "variables")
    if err:
        return err
    mod = _imp("text")
    return mod.template_render(args["template"], args["variables"])


def _word_frequency(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.word_frequency(
        text=args.get("text", ""), file=args.get("file", ""),
        top=args.get("top", 30), min_len=args.get("min_len", 2),
        stopwords=args.get("stopwords", ""), root=root)


def _tokenize(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.tokenize(
        text=args.get("text", ""), file=args.get("file", ""),
        mode=args.get("mode", "mix"), root=root)


def _simplify_chinese(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.simplify_chinese(
        text=args.get("text", ""), file=args.get("file", ""),
        direction=args.get("direction", "t2s"), root=root)


def _dedupe_lines(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.dedupe_lines(
        text=args.get("text", ""), file=args.get("file", ""),
        case_insensitive=bool(args.get("case_insensitive", False)),
        strip_whitespace=bool(args.get("strip_whitespace", True)),
        keep_order=bool(args.get("keep_order", True)),
        root=root)


def _text_similarity(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.text_similarity(
        text1=args.get("text1", ""), text2=args.get("text2", ""),
        file1=args.get("file1", ""), file2=args.get("file2", ""),
        algorithm=args.get("algorithm", "jaccard"), root=root)


def _strip_invisible(root: Path, args: dict) -> str:
    mod = _imp("text_advanced")
    return mod.strip_invisible(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root)


# ═══════════════════════════════════════════════════════════════════════ #
# 编码 / 哈希
# ═══════════════════════════════════════════════════════════════════════ #

def _base64_codec(root: Path, args: dict) -> str:
    err = _require(args, "action")
    if err:
        return err
    mod = _imp("encoding")
    return mod.base64_codec(
        args["action"],
        data=args.get("data", ""),
        file=args.get("file", ""),
        root=root)


def _hash_text(root: Path, args: dict) -> str:
    mod = _imp("encoding")
    return mod.hash_text(
        args.get("text", ""),
        args.get("algorithm", "sha256"))


def _url_codec(root: Path, args: dict) -> str:
    err = _require(args, "action", "text")
    if err:
        return err
    mod = _imp("encoding")
    return mod.url_codec(args["action"], args["text"])


def _password_gen(root: Path, args: dict) -> str:
    mod = _imp("encoding")
    return mod.password_gen(
        length=args.get("length", 20),
        count=args.get("count", 1),
        charset=args.get("charset", "mixed"),
        symbols=bool(args.get("symbols", True)))


def _jwt_decode(root: Path, args: dict) -> str:
    err = _require(args, "token")
    if err:
        return err
    mod = _imp("encoding")
    return mod.jwt_decode(args["token"])


def _random_bytes(root: Path, args: dict) -> str:
    mod = _imp("crypto")
    return mod.random_bytes(
        args.get("length", 32),
        args.get("fmt", "hex"))


def _hash_data(root: Path, args: dict) -> str:
    mod = _imp("crypto")
    return mod.hash_data(
        data=args.get("data", ""), file=args.get("file", ""),
        algorithm=args.get("algorithm", "sha256"),
        hmac_key=args.get("hmac_key", ""), root=root)


# ═══════════════════════════════════════════════════════════════════════ #
# 时间
# ═══════════════════════════════════════════════════════════════════════ #

def _now_info(root: Path, args: dict) -> str:
    return _imp("timeutil").now_info()


def _date_calc(root: Path, args: dict) -> str:
    err = _require(args, "offset")
    if err:
        return err
    mod = _imp("timeutil")
    return mod.date_calc(
        base=args.get("base", ""), offset=args["offset"],
        format=args.get("format", "%Y-%m-%d"))


def _timezone_convert(root: Path, args: dict) -> str:
    err = _require(args, "time_str", "from_tz", "to_tz")
    if err:
        return err
    mod = _imp("timeutil")
    return mod.timezone_convert(
        args["time_str"], args["from_tz"], args["to_tz"])


def _cron_next(root: Path, args: dict) -> str:
    err = _require(args, "expression")
    if err:
        return err
    mod = _imp("timeutil")
    return mod.cron_next(args["expression"], args.get("count", 5))


# ═══════════════════════════════════════════════════════════════════════ #
# 格式转换
# ═══════════════════════════════════════════════════════════════════════ #

def _json_format(root: Path, args: dict) -> str:
    mod = _imp("convert")
    return mod.json_format(
        data=args.get("data", ""), file=args.get("file", ""),
        indent=args.get("indent", 2),
        compact=bool(args.get("compact", False)), root=root)


def _json_diff(root: Path, args: dict) -> str:
    mod = _imp("convert")
    return mod.json_diff(
        a=args.get("a", ""), b=args.get("b", ""),
        file_a=args.get("file_a", ""),
        file_b=args.get("file_b", ""), root=root)


def _csv_to_json(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("convert")
    return mod.csv_to_json(
        args["path"], root,
        delimiter=args.get("delimiter", ","))


def _json_to_csv(root: Path, args: dict) -> str:
    mod = _imp("convert")
    return mod.json_to_csv(
        data=args.get("data", ""), file=args.get("file", ""),
        root=root, delimiter=args.get("delimiter", ","))


def _md_to_html(root: Path, args: dict) -> str:
    mod = _imp("convert")
    return mod.md_to_html(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root, full=bool(args.get("full", False)))


def _text_stats(root: Path, args: dict) -> str:
    mod = _imp("convert")
    return mod.text_stats(
        text=args.get("text", ""), file=args.get("file", ""),
        root=root)


# ═══════════════════════════════════════════════════════════════════════ #
# 注册表
# ═══════════════════════════════════════════════════════════════════════ #

HANDLERS = {
    # 文本
    "regex_extract":      _regex_extract,
    "code_stats":         _code_stats,
    "markdown_toc":       _markdown_toc,
    "template_render":    _template_render,
    "word_frequency":     _word_frequency,
    "tokenize":           _tokenize,
    "simplify_chinese":   _simplify_chinese,
    "dedupe_lines":       _dedupe_lines,
    "text_similarity":    _text_similarity,
    "strip_invisible":    _strip_invisible,
    # 编码 / 哈希
    "base64_codec":       _base64_codec,
    "hash_text":          _hash_text,
    "url_codec":          _url_codec,
    "password_gen":       _password_gen,
    "jwt_decode":         _jwt_decode,
    "random_bytes":       _random_bytes,
    "hash_data":          _hash_data,
    # 时间
    "now_info":           _now_info,
    "date_calc":          _date_calc,
    "timezone_convert":   _timezone_convert,
    "cron_next":          _cron_next,
    # 转换
    "json_format":        _json_format,
    "json_diff":          _json_diff,
    "csv_to_json":        _csv_to_json,
    "json_to_csv":        _json_to_csv,
    "md_to_html":         _md_to_html,
    "text_stats":         _text_stats,
}