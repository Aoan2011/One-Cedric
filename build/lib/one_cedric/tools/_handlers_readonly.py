"""只读 handlers：文件 / 网络 / 数据 / 系统。"""
from __future__ import annotations

from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════ #
# 惰性导入工具
# ═══════════════════════════════════════════════════════════════════════ #

def _imp(module_name: str):
    """导入同级模块。失败抛 ImportError。"""
    import importlib
    return importlib.import_module(
        f".{module_name}", package=__package__)


def _require(args: dict, *keys: str) -> str:
    for k in keys:
        if k not in args or args[k] in ("", None):
            return f"ERROR: 缺少必需参数 {k}。"
    return ""


def _err_wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ═══════════════════════════════════════════════════════════════════════ #
# 文件读
# ═══════════════════════════════════════════════════════════════════════ #

def _read_file(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("readonly")
    return mod.read_file(
        root, args["path"],
        start_line=args.get("start_line", 1),
        end_line=args.get("end_line"),
        encoding=args.get("encoding", ""),
    )


def _list_files(root: Path, args: dict) -> str:
    mod = _imp("readonly")
    return mod.list_files(root, args.get("path", "."),
                          bool(args.get("recursive", False)))


def _search_in_files(root: Path, args: dict) -> str:
    err = _require(args, "pattern")
    if err:
        return err
    mod = _imp("readonly")
    return mod.search_in_files(
        root, args["pattern"],
        path=args.get("path", "."),
        file_pattern=args.get("file_pattern", "*"),
    )


def _file_info(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("readonly")
    return mod.file_info(root, args["path"])


def _glob(root: Path, args: dict) -> str:
    err = _require(args, "pattern")
    if err:
        return err
    mod = _imp("readonly")
    return mod.glob_files(
        root, args["pattern"],
        path=args.get("path", "."),
        max_results=args.get("max_results"),
    )


def _grep_regex(root: Path, args: dict) -> str:
    err = _require(args, "pattern")
    if err:
        return err
    mod = _imp("readonly")
    return mod.grep_regex(
        root, args["pattern"],
        path=args.get("path", "."),
        file_pattern=args.get("file_pattern", "*"),
        case_insensitive=bool(args.get("case_insensitive", False)),
        max_results=args.get("max_results"),
    )


def _hash_file(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("files")
    return mod.hash_file(root, args["path"],
                          algorithm=args.get("algorithm", "sha256"))


def _find_duplicates(root: Path, args: dict) -> str:
    mod = _imp("files")
    return mod.find_duplicates(
        root, args.get("path", "."),
        min_size=args.get("min_size"),
        max_groups=args.get("max_groups"),
    )


def _pdf_extract(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("pdf")
    return mod.pdf_extract(
        root, args["path"],
        start_page=args.get("start_page"),
        end_page=args.get("end_page"),
        max_chars=args.get("max_chars"),
    )


# ═══════════════════════════════════════════════════════════════════════ #
# 网络
# ═══════════════════════════════════════════════════════════════════════ #

def _web_fetch(root: Path, args: dict) -> str:
    err = _require(args, "url")
    if err:
        return err
    mod = _imp("net")
    return mod.web_fetch(
        args["url"],
        max_bytes=args.get("max_bytes"),
        raw=bool(args.get("raw", False)),
    )


def _http_request(root: Path, args: dict) -> str:
    err = _require(args, "url")
    if err:
        return err
    mod = _imp("net")
    return mod.http_request(
        args["url"],
        method=args.get("method", "GET"),
        headers=args.get("headers"),
        body=args.get("body"),
        timeout=args.get("timeout"),
    )


def _web_search(root: Path, args: dict) -> str:
    err = _require(args, "query")
    if err:
        return err
    mod = _imp("net")
    return mod.web_search(
        query=args["query"],
        max_results=args.get("max_results"),
        engines=args.get("engines"),
        include_aggregates=bool(args.get("include_aggregates", True)),
        timeout=args.get("timeout"),
    )


def _web_research(root: Path, args: dict) -> str:
    err = _require(args, "query")
    if err:
        return err
    mod = _imp("net")
    return mod.web_research(
        query=args["query"],
        top_n=args.get("top_n"),
        max_chars_per_page=args.get("max_chars_per_page"),
        engines=args.get("engines"),
        fetch_timeout=args.get("fetch_timeout"),
        mode=args.get("mode", "balanced"),
    )


def _download_info(root: Path, args: dict) -> str:
    err = _require(args, "url")
    if err:
        return err
    mod = _imp("downloader")
    res = mod.download_preview(
        args["url"], args.get("out", ""),
        args.get("threads", 0), root=root)
    # 返回 (preview, is_write, err, meta)
    if isinstance(res, tuple) and len(res) >= 3:
        preview, _is_write, err = res[0], res[1], res[2]
        if err:
            return err
        return preview
    return str(res)


def _ping_host(root: Path, args: dict) -> str:
    err = _require(args, "host")
    if err:
        return err
    mod = _imp("netprobe")
    return mod.ping_host(args["host"], args.get("count", 4))


def _port_scan(root: Path, args: dict) -> str:
    err = _require(args, "host")
    if err:
        return err
    mod = _imp("netprobe")
    return mod.port_scan(
        args["host"],
        ports=args.get("ports", "common"),
        timeout=args.get("timeout", 1.0),
        workers=args.get("workers", 100),
    )


def _traceroute(root: Path, args: dict) -> str:
    err = _require(args, "host")
    if err:
        return err
    mod = _imp("netprobe")
    return mod.traceroute(args["host"], args.get("max_hops", 20))


def _get_public_ip(root: Path, args: dict) -> str:
    mod = _imp("netprobe")
    return mod.get_public_ip()


def _dns_lookup(root: Path, args: dict) -> str:
    err = _require(args, "host")
    if err:
        return err
    mod = _imp("network_diag")
    return mod.dns_lookup(args["host"],
                          args.get("record_type", "A"))


def _ssl_check(root: Path, args: dict) -> str:
    err = _require(args, "url")
    if err:
        return err
    mod = _imp("network_diag")
    return mod.ssl_check(args["url"], args.get("port", 0))


def _http_head(root: Path, args: dict) -> str:
    err = _require(args, "url")
    if err:
        return err
    mod = _imp("network_diag")
    return mod.http_head(args["url"], args.get("timeout", 10))


# ═══════════════════════════════════════════════════════════════════════ #
# 数据
# ═══════════════════════════════════════════════════════════════════════ #

def _json_query(root: Path, args: dict) -> str:
    err = _require(args, "file")
    if err:
        return err
    mod = _imp("data")
    return mod.json_query(root, args["file"],
                          args.get("path", ""))


def _csv_query(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("data")
    return mod.csv_query(
        root, args["path"],
        columns=args.get("columns"),
        limit=args.get("limit"),
        delimiter=args.get("delimiter", ","),
    )


def _sqlite(root: Path, args: dict) -> str:
    err = _require(args, "path", "query")
    if err:
        return err
    mod = _imp("data")
    res, is_write, err2 = mod.sqlite_query(
        root, args["path"], args["query"],
        params=args.get("params"),
        allow_write=bool(args.get("allow_write", False)),
        max_rows=args.get("max_rows"),
    )
    if err2:
        return err2
    return res


def _sqlite_tables(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("database")
    return mod.sqlite_tables(args["path"], root)


def _sqlite_schema(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    mod = _imp("database")
    return mod.sqlite_schema(args["path"],
                              args.get("table", ""), root)


def _json_schema_validate(root: Path, args: dict) -> str:
    err = _require(args, "data_file", "schema_file")
    if err:
        return err
    mod = _imp("data")
    return mod.json_schema_validate(
        root, args["data_file"], args["schema_file"])


def _postgres_query(root: Path, args: dict) -> str:
    err = _require(args, "query")
    if err:
        return err
    mod = _imp("database")
    return mod.postgres_query(
        args.get("conn", ""), args["query"],
        args.get("database", ""), args.get("params"),
        args.get("limit", 100))


def _postgres_list_tables(root: Path, args: dict) -> str:
    mod = _imp("database")
    return mod.postgres_list_tables(args.get("conn", ""),
                                     args.get("database", ""))


def _postgres_describe(root: Path, args: dict) -> str:
    err = _require(args, "table")
    if err:
        return err
    mod = _imp("database")
    return mod.postgres_describe(
        args.get("conn", ""), args["table"],
        args.get("database", ""))


def _mysql_query(root: Path, args: dict) -> str:
    err = _require(args, "query")
    if err:
        return err
    mod = _imp("database")
    return mod.mysql_query(
        args.get("conn", ""), args["query"],
        args.get("database", ""), args.get("params"),
        args.get("limit", 100))


def _mysql_list_tables(root: Path, args: dict) -> str:
    mod = _imp("database")
    return mod.mysql_list_tables(args.get("conn", ""),
                                  args.get("database", ""))


def _mysql_describe(root: Path, args: dict) -> str:
    err = _require(args, "table")
    if err:
        return err
    mod = _imp("database")
    return mod.mysql_describe(
        args.get("conn", ""), args["table"],
        args.get("database", ""))


def _mongo_list_databases(root: Path, args: dict) -> str:
    mod = _imp("database")
    return mod.mongo_list_databases(args.get("uri", ""))


def _mongo_list_collections(root: Path, args: dict) -> str:
    err = _require(args, "database")
    if err:
        return err
    mod = _imp("database")
    return mod.mongo_list_collections(
        args.get("uri", ""), args["database"])


def _mongo_find(root: Path, args: dict) -> str:
    err = _require(args, "database", "collection")
    if err:
        return err
    mod = _imp("database")
    return mod.mongo_find(
        args.get("uri", ""), args["database"], args["collection"],
        args.get("filter_json", ""), args.get("limit", 20),
        args.get("projection_json", ""))


def _mongo_aggregate(root: Path, args: dict) -> str:
    err = _require(args, "database", "collection", "pipeline_json")
    if err:
        return err
    mod = _imp("database")
    return mod.mongo_aggregate(
        args.get("uri", ""), args["database"], args["collection"],
        args["pipeline_json"], args.get("limit", 50))


def _mongo_stats(root: Path, args: dict) -> str:
    err = _require(args, "database")
    if err:
        return err
    mod = _imp("database")
    return mod.mongo_stats(args.get("uri", ""), args["database"])


# ═══════════════════════════════════════════════════════════════════════ #
# 系统
# ═══════════════════════════════════════════════════════════════════════ #

def _env_info(root: Path, args: dict) -> str:
    mod = _imp("system")
    return mod.env_info(root, args.get("include", "all"))


def _process_info(root: Path, args: dict) -> str:
    mod = _imp("system")
    return mod.process_info(
        args.get("scope", "processes"),
        args.get("filter", ""),
        args.get("limit"))


def _calculate(root: Path, args: dict) -> str:
    err = _require(args, "expression")
    if err:
        return err
    mod = _imp("system")
    return mod.calculate(args["expression"])


def _system_metrics(root: Path, args: dict) -> str:
    mod = _imp("system")
    return mod.system_metrics(args.get("include", "all"))


def _diff_files(root: Path, args: dict) -> str:
    err = _require(args, "a", "b")
    if err:
        return err
    mod = _imp("dev")
    return mod.diff_files(root, args["a"], args["b"],
                           args.get("context"))


def _pip_list(root: Path, args: dict) -> str:
    mod = _imp("sysinfo")
    return mod.pip_list(
        filter=args.get("filter", ""),
        outdated=bool(args.get("outdated", False)))


def _pip_show(root: Path, args: dict) -> str:
    err = _require(args, "package")
    if err:
        return err
    mod = _imp("sysinfo")
    return mod.pip_show(args["package"])


def _disk_tree(root: Path, args: dict) -> str:
    mod = _imp("sysinfo")
    return mod.disk_tree(
        args.get("path", "."), root=root,
        max_depth=args.get("max_depth", 3),
        min_size=args.get("min_size", 0),
        top=args.get("top", 30))


# ═══════════════════════════════════════════════════════════════════════ #
# 注册表
# ═══════════════════════════════════════════════════════════════════════ #

HANDLERS = {
    # 文件读
    "read_file":          _read_file,
    "list_files":         _list_files,
    "search_in_files":    _search_in_files,
    "file_info":          _file_info,
    "glob":               _glob,
    "grep_regex":         _grep_regex,
    "hash_file":          _hash_file,
    "find_duplicates":    _find_duplicates,
    "pdf_extract":        _pdf_extract,
    # 网络
    "web_fetch":          _web_fetch,
    "http_request":       _http_request,
    "web_search":         _web_search,
    "web_research":       _web_research,
    "download_info":      _download_info,
    "ping_host":          _ping_host,
    "port_scan":          _port_scan,
    "traceroute":         _traceroute,
    "get_public_ip":      _get_public_ip,
    "dns_lookup":         _dns_lookup,
    "ssl_check":          _ssl_check,
    "http_head":          _http_head,
    # 数据
    "json_query":         _json_query,
    "csv_query":          _csv_query,
    "sqlite":             _sqlite,
    "sqlite_tables":      _sqlite_tables,
    "sqlite_schema":      _sqlite_schema,
    "json_schema_validate": _json_schema_validate,
    "postgres_query":     _postgres_query,
    "postgres_list_tables": _postgres_list_tables,
    "postgres_describe":  _postgres_describe,
    "mysql_query":        _mysql_query,
    "mysql_list_tables":  _mysql_list_tables,
    "mysql_describe":     _mysql_describe,
    "mongo_list_databases": _mongo_list_databases,
    "mongo_list_collections": _mongo_list_collections,
    "mongo_find":         _mongo_find,
    "mongo_aggregate":    _mongo_aggregate,
    "mongo_stats":        _mongo_stats,
    # 系统
    "env_info":           _env_info,
    "process_info":       _process_info,
    "calculate":          _calculate,
    "system_metrics":     _system_metrics,
    "diff_files":         _diff_files,
    "pip_list":           _pip_list,
    "pip_show":           _pip_show,
    "disk_tree":          _disk_tree,
}