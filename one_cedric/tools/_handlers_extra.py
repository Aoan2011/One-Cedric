"""通知 / 应用 / 天气 / 定位 / 高德 / 邮件 / 微信 / Compose / K8s 只读 handlers。"""
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
# 通知
# ═══════════════════════════════════════════════════════════════════════ #

def _notify_check(root: Path, args: dict) -> str:
    return _imp("notify_tool").check_support()


# ═══════════════════════════════════════════════════════════════════════ #
# 应用管理
# ═══════════════════════════════════════════════════════════════════════ #

def _open_app(root: Path, args: dict) -> str:
    err = _require(args, "target")
    if err:
        return err
    return _imp("apps").open_app(
        args["target"], args.get("args"))


def _list_apps(root: Path, args: dict) -> str:
    return _imp("apps").list_apps(
        args.get("filter", ""), args.get("limit", 100))


def _find_app(root: Path, args: dict) -> str:
    err = _require(args, "name")
    if err:
        return err
    return _imp("apps").find_app(
        args["name"], args.get("max_results", 20))


def _pkg_manager_info(root: Path, args: dict) -> str:
    return _imp("apps").list_pkg_manager()


def _pkg_search(root: Path, args: dict) -> str:
    err = _require(args, "query")
    if err:
        return err
    return _imp("apps").search_pkg(
        args["query"], args.get("source", ""),
        args.get("limit", 20))


def _pkg_list_installed(root: Path, args: dict) -> str:
    return _imp("apps").list_installed(args.get("source", ""))


# ═══════════════════════════════════════════════════════════════════════ #
# 天气 / 定位
# ═══════════════════════════════════════════════════════════════════════ #

def _weather(root: Path, args: dict) -> str:
    err = _require(args, "location")
    if err:
        return err
    return _imp("weather").get_weather(
        location=args["location"],
        format=args.get("format", "full"),
        lang=args.get("lang", ""))


def _locate_rough(root: Path, args: dict) -> str:
    mod = _imp("geolocate")
    d = mod.rough_locate()
    return mod.format_rough(d)


def _locate_current(root: Path, args: dict) -> str:
    mod = _imp("geolocate")
    if mod.has_consent():
        d = mod.get_exact_location()
        return f"已保存的精确位置: {mod.format_exact(d)}"
    return "未保存精确位置。可用 locate_rough 粗查。"


def _locate_set_exact(root: Path, args: dict) -> str:
    err = _require(args, "location")
    if err:
        return err
    mod = _imp("geolocate")
    if not args.get("consent"):
        return "ERROR: 保存精确位置需要用户明确同意（consent=true）。"
    data = mod.parse_location_input(args["location"])
    if not data:
        return "ERROR: 无法解析的位置输入。请用「国-省-市-区」或经纬度。"
    mod.set_consent(True, data)
    return f"已保存精确位置（本会话有效）: {mod.format_exact(data)}"


# ═══════════════════════════════════════════════════════════════════════ #
# 高德地图
# ═══════════════════════════════════════════════════════════════════════ #

def _amap_geocode(root: Path, args: dict) -> str:
    err = _require(args, "address")
    if err:
        return err
    return _imp("amap").amap_geocode(
        args["address"], args.get("city", ""))


def _amap_regeocode(root: Path, args: dict) -> str:
    err = _require(args, "location")
    if err:
        return err
    return _imp("amap").amap_regeocode(
        args["location"],
        radius=args.get("radius", 1000),
        extensions=args.get("extensions", "base"))


def _amap_search_poi(root: Path, args: dict) -> str:
    return _imp("amap").amap_search_poi(
        keywords=args.get("keywords", ""),
        city=args.get("city", ""),
        types=args.get("types", ""),
        location=args.get("location", ""),
        radius=args.get("radius", 3000),
        page=args.get("page", 1),
        offset=args.get("offset", 20),
        extensions=args.get("extensions", "all"))


def _amap_poi_detail(root: Path, args: dict) -> str:
    err = _require(args, "poi_id")
    if err:
        return err
    return _imp("amap").amap_poi_detail(
        args["poi_id"], args.get("extensions", "all"))


def _amap_around(root: Path, args: dict) -> str:
    err = _require(args, "location")
    if err:
        return err
    return _imp("amap").amap_around(
        location=args["location"],
        keywords=args.get("keywords", ""),
        types=args.get("types", ""),
        radius=args.get("radius", 1000),
        offset=args.get("offset", 20))


def _amap_input_tips(root: Path, args: dict) -> str:
    err = _require(args, "keywords")
    if err:
        return err
    return _imp("amap").amap_input_tips(
        keywords=args["keywords"], city=args.get("city", ""))


def _amap_weather(root: Path, args: dict) -> str:
    err = _require(args, "city")
    if err:
        return err
    return _imp("amap").amap_weather(
        args["city"], args.get("extensions", "base"))


def _amap_driving(root: Path, args: dict) -> str:
    err = _require(args, "origin", "destination")
    if err:
        return err
    return _imp("amap").amap_driving(
        args["origin"], args["destination"],
        strategy=args.get("strategy", 0))


def _amap_walking(root: Path, args: dict) -> str:
    err = _require(args, "origin", "destination")
    if err:
        return err
    return _imp("amap").amap_walking(
        args["origin"], args["destination"])


def _amap_bicycling(root: Path, args: dict) -> str:
    err = _require(args, "origin", "destination")
    if err:
        return err
    return _imp("amap").amap_bicycling(
        args["origin"], args["destination"])


def _amap_transit(root: Path, args: dict) -> str:
    err = _require(args, "origin", "destination", "city")
    if err:
        return err
    return _imp("amap").amap_transit(
        args["origin"], args["destination"], args["city"],
        cityd=args.get("cityd", ""),
        strategy=args.get("strategy", 0))


def _amap_distance(root: Path, args: dict) -> str:
    err = _require(args, "origins", "destination")
    if err:
        return err
    return _imp("amap").amap_distance(
        args["origins"], args["destination"],
        type_=args.get("type_", 1))


def _amap_ip_location(root: Path, args: dict) -> str:
    return _imp("amap").amap_ip_location(args.get("ip", ""))


def _amap_district(root: Path, args: dict) -> str:
    return _imp("amap").amap_district(
        keywords=args.get("keywords", ""),
        subdistrict=args.get("subdistrict", 1),
        extensions=args.get("extensions", "base"))


# ═══════════════════════════════════════════════════════════════════════ #
# 邮件（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _email_accounts(root: Path, args: dict) -> str:
    return _imp("email_tools").email_accounts()


def _email_list_folders(root: Path, args: dict) -> str:
    return _imp("email_tools").imap_list_folders(
        args.get("account", ""))


def _email_list_messages(root: Path, args: dict) -> str:
    return _imp("email_tools").imap_list_messages(
        account=args.get("account", ""),
        folder=args.get("folder", "INBOX"),
        count=args.get("count", 20),
        unread_only=bool(args.get("unread_only", False)),
        since=args.get("since", ""))


def _email_search(root: Path, args: dict) -> str:
    return _imp("email_tools").imap_search(
        account=args.get("account", ""),
        folder=args.get("folder", "INBOX"),
        from_=args.get("from_", ""),
        to=args.get("to", ""),
        subject=args.get("subject", ""),
        body=args.get("body", ""),
        since=args.get("since", ""),
        before=args.get("before", ""),
        unseen_only=bool(args.get("unseen_only", False)),
        count=args.get("count", 30))


def _email_read(root: Path, args: dict) -> str:
    err = _require(args, "uid")
    if err:
        return err
    return _imp("email_tools").imap_read(
        account=args.get("account", ""),
        folder=args.get("folder", "INBOX"),
        uid=str(args["uid"]),
        mark_seen=bool(args.get("mark_seen", False)),
        include_html=bool(args.get("include_html", False)))


def _email_list_attachments(root: Path, args: dict) -> str:
    err = _require(args, "uid")
    if err:
        return err
    return _imp("email_tools").imap_list_attachments(
        account=args.get("account", ""),
        folder=args.get("folder", "INBOX"),
        uid=str(args["uid"]))


def _email_pop_list(root: Path, args: dict) -> str:
    return _imp("email_tools").pop3_list(
        account=args.get("account", ""),
        count=args.get("count", 20))


def _email_pop_read(root: Path, args: dict) -> str:
    err = _require(args, "index")
    if err:
        return err
    return _imp("email_tools").pop3_read(
        account=args.get("account", ""),
        index=int(args["index"]),
        delete_after=bool(args.get("delete_after", False)))


# ═══════════════════════════════════════════════════════════════════════ #
# 微信（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _wechat_status(root: Path, args: dict) -> str:
    return _imp("wechat").wechat_status()


def _wechat_read_recent(root: Path, args: dict) -> str:
    return _imp("wechat").wechat_read_recent(
        args.get("contact", ""), args.get("count", 10))


def _wechat_moments_read(root: Path, args: dict) -> str:
    return _imp("wechat").wechat_moments_read()


# ═══════════════════════════════════════════════════════════════════════ #
# Docker Compose（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _compose_status(root: Path, args: dict) -> str:
    return _imp("orchestration").compose_status(
        args.get("file", "docker-compose.yml"), root)


def _compose_logs(root: Path, args: dict) -> str:
    return _imp("orchestration").compose_logs(
        args.get("file", "docker-compose.yml"),
        args.get("service", ""), args.get("tail", 100), root)


def _compose_config(root: Path, args: dict) -> str:
    return _imp("orchestration").compose_config(
        args.get("file", "docker-compose.yml"), root)


# ═══════════════════════════════════════════════════════════════════════ #
# Kubernetes（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _k8s_get(root: Path, args: dict) -> str:
    return _imp("orchestration").k8s_get(
        args.get("resource", "pods"),
        args.get("namespace", ""),
        bool(args.get("all_namespaces", False)),
        args.get("output", ""))


def _k8s_describe(root: Path, args: dict) -> str:
    err = _require(args, "resource")
    if err:
        return err
    return _imp("orchestration").k8s_describe(
        args["resource"], args.get("name", ""),
        args.get("namespace", ""))


def _k8s_logs(root: Path, args: dict) -> str:
    err = _require(args, "pod")
    if err:
        return err
    return _imp("orchestration").k8s_logs(
        args["pod"], args.get("namespace", ""),
        args.get("container", ""), args.get("tail", 100),
        bool(args.get("previous", False)))


def _k8s_contexts(root: Path, args: dict) -> str:
    return _imp("orchestration").k8s_contexts()


def _k8s_top(root: Path, args: dict) -> str:
    return _imp("orchestration").k8s_top(
        args.get("kind", "pods"),
        args.get("namespace", ""),
        bool(args.get("all_namespaces", False)))


# ═══════════════════════════════════════════════════════════════════════ #
# 注册表
# ═══════════════════════════════════════════════════════════════════════ #

def _github_latest_version(root: Path, args: dict) -> str:
    repo = str(args.get("repo") or "Aoan2011/One-Cedric").strip()
    try:
        import requests as _r
    except Exception as exc:
        return f"ERROR: 需要 requests: {exc}"
    try:
        resp = _r.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "One-Cedric"},
            timeout=15)
        if resp.status_code == 404:
            return f"ERROR: 仓库 {repo} 没有发布过 release"
        if resp.status_code != 200:
            return f"ERROR: GitHub API 返回 {resp.status_code}"
        data = resp.json()
    except Exception as exc:
        return f"ERROR: 请求失败: {exc}"
    body = str(data.get("body") or "")[:400] or "（无说明）"
    return (f"仓库: {repo}\n"
            f"最新版本: {data.get('tag_name', '?')}\n"
            f"发布时间: {data.get('published_at', '?')}\n"
            f"版本说明: {body}\n"
            f"链接: {data.get('html_url', '')}")


try:
    from ..browser_tools import BROWSER_HANDLERS as _BROWSER_HANDLERS
except Exception as _exc:  # playwright 未安装时仅少浏览器工具
    print(f"[tools] 跳过 browser_tools（{_exc}）")
    _BROWSER_HANDLERS = {}

HANDLERS = {
    **_BROWSER_HANDLERS,
    # 版本信息
    "github_latest_version": _github_latest_version,
    # 通知
    "notify_check":         _notify_check,
    # 应用
    "open_app":             _open_app,
    "list_apps":            _list_apps,
    "find_app":             _find_app,
    "pkg_manager_info":     _pkg_manager_info,
    "pkg_search":           _pkg_search,
    "pkg_list_installed":   _pkg_list_installed,
    # 天气 / 定位
    "weather":              _weather,
    "locate_rough":         _locate_rough,
    "locate_current":       _locate_current,
    "locate_set_exact":     _locate_set_exact,
    # 高德
    "amap_geocode":         _amap_geocode,
    "amap_regeocode":       _amap_regeocode,
    "amap_search_poi":      _amap_search_poi,
    "amap_poi_detail":      _amap_poi_detail,
    "amap_around":          _amap_around,
    "amap_input_tips":      _amap_input_tips,
    "amap_weather":         _amap_weather,
    "amap_driving":         _amap_driving,
    "amap_walking":         _amap_walking,
    "amap_bicycling":       _amap_bicycling,
    "amap_transit":         _amap_transit,
    "amap_distance":        _amap_distance,
    "amap_ip_location":     _amap_ip_location,
    "amap_district":        _amap_district,
    # 邮件
    "email_accounts":       _email_accounts,
    "email_list_folders":   _email_list_folders,
    "email_list_messages":  _email_list_messages,
    "email_search":         _email_search,
    "email_read":           _email_read,
    "email_list_attachments": _email_list_attachments,
    "email_pop_list":       _email_pop_list,
    "email_pop_read":       _email_pop_read,
    # 微信
    "wechat_status":        _wechat_status,
    "wechat_read_recent":   _wechat_read_recent,
    "wechat_moments_read":  _wechat_moments_read,
    # Compose
    "compose_status":       _compose_status,
    "compose_logs":         _compose_logs,
    "compose_config":       _compose_config,
    # K8s
    "k8s_get":              _k8s_get,
    "k8s_describe":         _k8s_describe,
    "k8s_logs":             _k8s_logs,
    "k8s_contexts":         _k8s_contexts,
    "k8s_top":              _k8s_top,
}