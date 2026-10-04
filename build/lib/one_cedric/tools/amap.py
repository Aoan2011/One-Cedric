"""高德地图 Web 服务 API 工具集。

API Key 配置（三选一，优先级从高到低）：
  1. 环境变量 AMAP_API_KEY
  2. 全局配置 ~/.one-cedric/config.toml 的 [amap] api_key
  3. 项目配置中的 [amap] api_key

申请地址：https://lbs.amap.com/dev/key/app
需选择「Web服务」平台类型。
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

BASE = "https://restapi.amap.com/v3"
TIMEOUT = 12
USER_AGENT = "OneCedric/1.0"


# --------------------------------------------------------------------------- #
# Key 管理
# --------------------------------------------------------------------------- #

_AMAP_KEY_CACHE: str | None = None


def _load_amap_key() -> str:
    """按优先级查找 API Key。"""
    global _AMAP_KEY_CACHE
    if _AMAP_KEY_CACHE is not None:
        return _AMAP_KEY_CACHE

    import os
    key = os.environ.get("AMAP_API_KEY", "").strip()
    if key:
        _AMAP_KEY_CACHE = key
        return key

    try:
        from ..storage import default_config_path, project_config_path
        from ..config import AMAP_CONFIG_FILENAME  # noqa: F401
        import tomllib
    except ImportError:
        _AMAP_KEY_CACHE = ""
        return ""

    for cfg_path in (
        Path.home() / ".one-cedric" / "amap.toml",
        default_config_path(),
    ):
        if not cfg_path.exists():
            continue
        try:
            raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        k = (raw.get("amap") or {}).get("api_key", "").strip()
        if k:
            _AMAP_KEY_CACHE = k
            return k

    _AMAP_KEY_CACHE = ""
    return ""


def set_amap_key(key: str) -> None:
    """运行时设置 Key（/amap-key 命令用）。"""
    global _AMAP_KEY_CACHE
    _AMAP_KEY_CACHE = (key or "").strip()


def amap_key_status() -> str:
    k = _load_amap_key()
    if not k:
        return ("未配置 AMAP API Key。\n"
                "配置方式（三选一）：\n"
                "  1. 设置环境变量：$env:AMAP_API_KEY='你的key'\n"
                "  2. 在 ~/.one-cedric/amap.toml 写：\n"
                "     [amap]\n     api_key = \"你的key\"\n"
                "  3. 在 ~/.one-cedric/config.toml 的 [amap] 段写 api_key\n"
                "申请：https://lbs.amap.com/dev/key/app（选「Web服务」）")
    masked = k[:6] + "..." + k[-4:] if len(k) > 12 else "***"
    return f"AMAP API Key: {masked}（已配置）"


# --------------------------------------------------------------------------- #
# 请求基座
# --------------------------------------------------------------------------- #

def _amap_get(endpoint: str, params: dict) -> tuple[dict | None, str]:
    key = _load_amap_key()
    if not key:
        return None, ("ERROR: 未配置 AMAP API Key。"
                      "运行 /amap-key <你的key> 或设置环境变量 AMAP_API_KEY。")

    p = {k: v for k, v in params.items() if v is not None and v != ""}
    p["key"] = key

    url = f"{BASE}{endpoint}"
    try:
        r = requests.get(url, params=p, timeout=TIMEOUT,
                         headers={"User-Agent": USER_AGENT})
    except requests.exceptions.Timeout:
        return None, f"ERROR: 请求超时（{TIMEOUT}s）"
    except requests.exceptions.RequestException as exc:
        return None, f"ERROR: 请求失败: {exc}"

    if r.status_code >= 400:
        return None, f"ERROR: HTTP {r.status_code} {r.reason}"

    try:
        data = r.json()
    except ValueError:
        return None, f"ERROR: 响应不是 JSON: {r.text[:200]}"

    status = str(data.get("status", ""))
    if status != "1":
        info = data.get("info", "未知错误")
        infocode = data.get("infocode", "")
        hint = _amap_error_hint(info, infocode)
        return None, f"ERROR: 高德 API 返回 {info} ({infocode}){hint}"

    return data, ""


def _amap_error_hint(info: str, infocode: str) -> str:
    hints = {
        "INVALID_USER_KEY": "（Key 无效，检查是否申请的是 Web服务 类型）",
        "SERVICE_NOT_AVAILABLE": "（该服务未开通，去控制台勾选对应 API）",
        "DAILY_QUERY_OVER_LIMIT": "（当日配额已用完）",
        "INVALID_USER_DOMAIN": "（域名白名单不匹配，Web服务无需配置域名）",
        "INSUFFICIENT_PRIVILEGES": "（Key 未开通此服务）",
        "USERKEY_PLAT_NOMATCH": "（Key 绑定的平台不对，需 Web服务 类型）",
        "INVALID_PARAMS": "（参数错误）",
        "ENGINE_RESPONSE_DATA_ERROR": "（服务端数据错误，稍后重试）",
    }
    return hints.get(info, "")


def _fmt_json(data: dict, drop_keys: tuple = ("key",)) -> str:
    clean = {k: v for k, v in data.items() if k not in drop_keys}
    return json.dumps(clean, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 1. 地理编码 / 逆地理编码
# --------------------------------------------------------------------------- #

def amap_geocode(address: str, city: str = "") -> str:
    if not address:
        return "ERROR: address 不能为空"
    data, err = _amap_get("/geocode/geo", {"address": address, "city": city})
    if err:
        return err

    geocodes = data.get("geocodes") or []
    if not geocodes:
        return f"未找到地址: {address}"

    lines = [f"地址: {address}", f"匹配 {len(geocodes)} 条：", ""]
    for i, g in enumerate(geocodes, 1):
        lines.append(f"{i}. {g.get('formatted_address', '')}")
        lines.append(f"   省: {g.get('province', '')}  市: {g.get('city', '')}")
        lines.append(f"   区: {g.get('district', '')}")
        lines.append(f"   坐标: {g.get('location', '')}")
        lines.append(f"   行政区码: {g.get('adcode', '')}")
        lines.append(f"   级别: {g.get('level', '')}")
        lines.append("")
    return "\n".join(lines)


def amap_regeocode(location: str, radius: int = 1000,
                   extensions: str = "base") -> str:
    if not location:
        return "ERROR: location 不能为空（格式：经度,纬度）"
    data, err = _amap_get("/geocode/regeo", {
        "location": location, "radius": radius, "extensions": extensions,
    })
    if err:
        return err

    regeo = data.get("regeocode") or {}
    addr = regeo.get("formatted_address", "")
    comp = regeo.get("addressComponent") or {}

    lines = [
        f"坐标: {location}",
        f"格式化地址: {addr}",
        "",
        f"省: {comp.get('province', '')}",
        f"市: {comp.get('city', '') or '（直辖市）'}",
        f"区: {comp.get('district', '')}",
        f"乡镇: {comp.get('township', '')}",
        f"行政区码: {comp.get('adcode', '')}",
        f"城市编码: {comp.get('citycode', '')}",
        f"经纬度: {comp.get('location', '') or location}",
    ]

    streets = comp.get("streetNumber") or {}
    if streets:
        lines.append("")
        lines.append(f"街道: {streets.get('street', '')} {streets.get('number', '')}")
        lines.append(f"最近道路: {streets.get('street', '')}")

    if extensions == "all":
        pois = regeo.get("pois") or []
        roads = regeo.get("roads") or []
        if pois:
            lines.append("")
            lines.append(f"周边 POI（{len(pois)}）：")
            for p in pois[:10]:
                lines.append(f"  · {p.get('name', '')}  [{p.get('type', '')}]")
                lines.append(f"    {p.get('address', '')}  距离 {p.get('distance', '')}m")
        if roads:
            lines.append("")
            lines.append(f"附近道路（{len(roads)}）：")
            for rd in roads[:5]:
                lines.append(f"  · {rd.get('name', '')}  距离 {rd.get('distance', '')}m")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 2. POI 搜索
# --------------------------------------------------------------------------- #

def amap_search_poi(keywords: str = "", city: str = "", types: str = "",
                    location: str = "", radius: int = 3000,
                    page: int = 1, offset: int = 20,
                    extensions: str = "all") -> str:
    if not keywords and not types:
        return "ERROR: 至少需要 keywords 或 types 之一"

    params = {
        "keywords": keywords, "city": city, "types": types,
        "location": location, "radius": radius,
        "page_num": page, "page_size": max(1, min(int(offset), 25)),
        "extensions": extensions, "citylimit": "false" if not city else "true",
    }
    data, err = _amap_get("/place/text", params)
    if err:
        return err

    pois = data.get("pois") or []
    count = data.get("count", "0")

    if not pois:
        return f"未找到 POI（关键词={keywords!r} 城市={city!r} 类型={types!r}）"

    lines = [f"找到 {count} 条，显示第 {page} 页（{len(pois)} 条）：", ""]
    for i, p in enumerate(pois, 1):
        name = p.get("name", "")
        addr = p.get("address", "")
        ptype = p.get("type", "")
        tel = p.get("tel", "")
        loc = p.get("location", "")
        dist = p.get("distance", "")

        lines.append(f"{i}. {name}")
        lines.append(f"   类型: {ptype}")
        lines.append(f"   地址: {addr}")
        if tel:
            lines.append(f"   电话: {tel}")
        if loc:
            lines.append(f"   坐标: {loc}" + (f"  距离 {dist}m" if dist else ""))
        lines.append(f"   ID: {p.get('id', '')}")

        biz = p.get("biz_ext") or {}
        if isinstance(biz, dict):
            rating = biz.get("rating") or biz.get("score")
            cost = biz.get("cost")
            if rating or cost:
                extras = []
                if rating:
                    extras.append(f"评分 {rating}")
                if cost:
                    extras.append(f"人均 ¥{cost}")
                lines.append(f"   {' · '.join(extras)}")

        photos = p.get("photos") or []
        if photos:
            lines.append(f"   图片: {len(photos)} 张")

        lines.append("")
    return "\n".join(lines)


def amap_poi_detail(poi_id: str, extensions: str = "all") -> str:
    if not poi_id:
        return "ERROR: poi_id 不能为空"
    data, err = _amap_get("/place/detail", {
        "id": poi_id, "extensions": extensions,
    })
    if err:
        return err

    pois = data.get("pois") or []
    if not pois:
        return f"未找到 POI: {poi_id}"

    p = pois[0]
    lines = [
        f"名称: {p.get('name', '')}",
        f"类型: {p.get('type', '')}",
        f"地址: {p.get('address', '')}",
        f"电话: {p.get('tel', '') or '（未提供）'}",
        f"坐标: {p.get('location', '')}",
        f"省市区: {p.get('pname', '')} {p.get('cityname', '')} {p.get('adname', '')}",
        f"ID: {p.get('id', '')}",
    ]

    rating = p.get("rating")
    cost = p.get("cost")
    if rating:
        lines.append(f"综合评分: {rating}")
    if cost and cost != "[]":
        lines.append(f"人均消费: ¥{cost}")

    biz = p.get("biz_ext") or {}
    if isinstance(biz, dict) and biz:
        lines.append("")
        lines.append("扩展信息:")
        for k, v in biz.items():
            if v and v != "[]":
                lines.append(f"  {k}: {v}")

    hours = p.get("biz_ext", {}).get("opentime") if isinstance(biz, dict) else ""
    if hours:
        lines.append(f"  营业时间: {hours}")

    photos = p.get("photos") or []
    if photos:
        lines.append("")
        lines.append(f"图片 ({len(photos)} 张):")
        for ph in photos[:5]:
            lines.append(f"  {ph.get('title', '')}: {ph.get('url', '')}")

    return "\n".join(lines)


def amap_around(location: str, keywords: str = "", types: str = "",
                radius: int = 1000, offset: int = 20) -> str:
    if not location:
        return "ERROR: location 不能为空（格式：经度,纬度）"
    params = {
        "location": location, "keywords": keywords, "types": types,
        "radius": radius, "offset": max(1, min(int(offset), 25)),
        "page": 1, "extensions": "all",
    }
    data, err = _amap_get("/place/around", params)
    if err:
        return err

    pois = data.get("pois") or []
    if not pois:
        return f"附近未找到 POI（半径 {radius}m）"

    lines = [f"附近 {len(pois)} 个 POI（半径 {radius}m）：", ""]
    for i, p in enumerate(pois, 1):
        dist = p.get("distance", "")
        lines.append(f"{i}. {p.get('name', '')}  [{p.get('type', '')}]")
        lines.append(f"   地址: {p.get('address', '')}")
        if dist:
            lines.append(f"   距离: {dist}m")
        tel = p.get("tel", "")
        if tel:
            lines.append(f"   电话: {tel}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 3. 输入提示
# --------------------------------------------------------------------------- #

def amap_input_tips(keywords: str, city: str = "",
                    types: str = "", datatype: str = "all") -> str:
    if not keywords:
        return "ERROR: keywords 不能为空"
    data, err = _amap_get("/assistant/inputtips", {
        "keywords": keywords, "city": city,
        "type": types, "datatype": datatype,
    })
    if err:
        return err

    tips = data.get("tips") or []
    if not tips:
        return f"无输入提示: {keywords}"

    lines = [f"输入提示（{len(tips)} 条）：", ""]
    for i, t in enumerate(tips, 1):
        name = t.get("name", "")
        district = t.get("district", "")
        addr = t.get("address", "")
        loc = t.get("location", "")
        lines.append(f"{i}. {name}")
        if district:
            lines.append(f"   区域: {district}")
        if addr:
            lines.append(f"   地址: {addr}")
        if loc:
            lines.append(f"   坐标: {loc}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 4. 天气
# --------------------------------------------------------------------------- #

def amap_weather(city: str, extensions: str = "base") -> str:
    if not city:
        return "ERROR: city 不能为空（adcode 或城市名）"

    ext = "all" if extensions in ("all", "forecast", "3d") else "base"
    data, err = _amap_get("/weather/weatherInfo", {
        "city": city, "extensions": ext,
    })
    if err:
        return err

    if ext == "base":
        lives = data.get("lives") or []
        if not lives:
            return f"未找到天气: {city}"
        lines = []
        for lv in lives:
            lines.append(f"{lv.get('province', '')} {lv.get('city', '')}")
            lines.append(f"  天气: {lv.get('weather', '')}")
            lines.append(f"  温度: {lv.get('temperature', '')}°C")
            lines.append(f"  风向: {lv.get('winddirection', '')}")
            lines.append(f"  风力: {lv.get('windpower', '')} 级")
            lines.append(f"  湿度: {lv.get('humidity', '')}%")
            lines.append(f"  发布时间: {lv.get('reporttime', '')}")
            lines.append("")
        return "\n".join(lines)

    forecasts = data.get("forecasts") or []
    if not forecasts:
        return f"未找到天气预报: {city}"

    lines = []
    for fc in forecasts:
        lines.append(f"{fc.get('province', '')} {fc.get('city', '')}  {fc.get('reporttime', '')}")
        casts = fc.get("casts") or []
        for c in casts:
            lines.append(f"  {c.get('date', '')}  {c.get('week', '')}")
            lines.append(f"    白天: {c.get('dayweather', '')}  {c.get('daytemp', '')}°C  "
                         f"风 {c.get('daywind', '')} {c.get('daypower', '')}级")
            lines.append(f"    夜间: {c.get('nightweather', '')}  {c.get('nighttemp', '')}°C  "
                         f"风 {c.get('nightwind', '')} {c.get('nightpower', '')}级")
            lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 5. 路径规划
# --------------------------------------------------------------------------- #

def _fmt_route_general(route: dict, label: str) -> list[str]:
    lines = []
    paths = route.get("paths") or []
    if not paths:
        return [f"（{label} 无路径）"]

    for i, path in enumerate(paths[:3], 1):
        dist = path.get("distance", "0")
        dur = path.get("duration", "0")
        try:
            dist_km = f"{int(dist) / 1000:.2f} km"
        except ValueError:
            dist_km = f"{dist} m"
        try:
            dur_min = f"{int(dur) / 60:.1f} 分钟"
        except ValueError:
            dur_min = f"{dur} s"

        lines.append(f"方案 {i}: {dist_km} · {dur_min}")
        if i == 1:
            steps = path.get("steps") or []
            lines.append(f"  步骤（{len(steps)} 步，前 15 步）：")
            for s in steps[:15]:
                instr = s.get("instruction", "")
                road = s.get("road", "")
                sd = s.get("distance", "")
                lines.append(f"    · {instr}  [{road}]  {sd}m")
            if len(steps) > 15:
                lines.append(f"    ... 还有 {len(steps) - 15} 步")
        lines.append("")
    return lines


def amap_driving(origin: str, destination: str, strategy: int = 0,
                 extensions: str = "base") -> str:
    if not origin or not destination:
        return "ERROR: origin 和 destination 都不能为空（格式：经度,纬度）"
    data, err = _amap_get("/direction/driving", {
        "origin": origin, "destination": destination,
        "strategy": strategy, "extensions": extensions,
    })
    if err:
        return err

    route = data.get("route") or {}
    lines = [f"驾车路线: {origin} → {destination}", ""]
    lines.extend(_fmt_route_general(route, "驾车"))

    taxi = route.get("taxi_cost")
    if taxi and taxi != "0":
        lines.append(f"预估打车费用: ¥{taxi}")
    return "\n".join(lines)


def amap_walking(origin: str, destination: str) -> str:
    if not origin or not destination:
        return "ERROR: origin 和 destination 都不能为空（格式：经度,纬度）"
    data, err = _amap_get("/direction/walking", {
        "origin": origin, "destination": destination,
    })
    if err:
        return err

    route = data.get("route") or {}
    lines = [f"步行路线: {origin} → {destination}", ""]
    lines.extend(_fmt_route_general(route, "步行"))
    return "\n".join(lines)


def amap_bicycling(origin: str, destination: str) -> str:
    if not origin or not destination:
        return "ERROR: origin 和 destination 都不能为空"
    data, err = _amap_get("/direction/bicycling", {
        "origin": origin, "destination": destination,
    })
    if err:
        return err

    route = data.get("route") or {}
    lines = [f"骑行路线: {origin} → {destination}", ""]
    lines.extend(_fmt_route_general(route, "骑行"))
    return "\n".join(lines)


def amap_transit(origin: str, destination: str, city: str,
                 cityd: str = "", strategy: int = 0) -> str:
    if not origin or not destination or not city:
        return "ERROR: origin / destination / city 都不能为空"
    data, err = _amap_get("/direction/transit/integrated", {
        "origin": origin, "destination": destination,
        "city": city, "cityd": cityd or city, "strategy": strategy,
    })
    if err:
        return err

    route = data.get("route") or {}
    transits = route.get("transits") or []
    if not transits:
        return f"未找到公交方案: {origin} → {destination}"

    lines = [f"公交路线: {origin} → {destination}（{city}）", ""]
    for i, t in enumerate(transits[:3], 1):
        dist = t.get("distance", "0")
        dur = t.get("duration", "0")
        cost = t.get("cost", "")
        try:
            dist_km = f"{int(dist) / 1000:.2f} km"
        except ValueError:
            dist_km = dist
        try:
            dur_min = f"{int(dur) / 60:.0f} 分钟"
        except ValueError:
            dur_min = dur

        lines.append(f"方案 {i}: {dist_km} · {dur_min}" + (f" · ¥{cost}" if cost else ""))
        segments = t.get("segments") or []
        walking_total = sum(
            int(s.get("walking", {}).get("distance", 0) or 0)
            for s in segments
        )
        lines.append(f"  步行总长: {walking_total}m")
        lines.append("")
    return "\n".join(lines)


def amap_distance(origins: str, destination: str, type_: int = 1) -> str:
    """type_: 0 直线距离, 1 驾车, 3 步行。"""
    if not origins or not destination:
        return "ERROR: origins 和 destination 不能为空"
    data, err = _amap_get("/distance", {
        "origins": origins, "destination": destination, "type": type_,
    })
    if err:
        return err

    results = data.get("results") or []
    lines = [f"距离测量（type={type_}）:", ""]
    for r in results:
        d = r.get("distance", "")
        dur = r.get("duration", "")
        try:
            d_km = f"{int(d) / 1000:.2f} km"
        except (ValueError, TypeError):
            d_km = str(d)
        try:
            dur_min = f"{int(dur) / 60:.1f} 分钟"
        except (ValueError, TypeError):
            dur_min = ""
        lines.append(f"  {r.get('origin_id', '?')}: {d_km}" + (f" · {dur_min}" if dur_min else ""))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 6. IP 定位
# --------------------------------------------------------------------------- #

def amap_ip_location(ip: str = "") -> str:
    data, err = _amap_get("/ip", {"ip": ip})
    if err:
        return err

    lines = [
        f"IP: {data.get('ip', '') or '（本机）'}",
        f"省: {data.get('province', '')}",
        f"市: {data.get('city', '')}",
        f"城市编码: {data.get('adcode', '')}",
        f"坐标: {data.get('rectangle', '')}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 7. 行政区划
# --------------------------------------------------------------------------- #

def amap_district(keywords: str = "", subdistrict: int = 1,
                  extensions: str = "base") -> str:
    data, err = _amap_get("/config/district", {
        "keywords": keywords, "subdistrict": subdistrict,
        "extensions": extensions,
    })
    if err:
        return err

    districts = data.get("districts") or []
    if not districts:
        return f"未找到行政区: {keywords}"

    lines = []
    for d in districts:
        lines.append(f"{d.get('name', '')}  [{d.get('level', '')}]")
        lines.append(f"  adcode: {d.get('adcode', '')}")
        lines.append(f"  城市编码: {d.get('citycode', '')}")
        lines.append(f"  中心点: {d.get('center', '')}")

        sub = d.get("districts") or []
        if sub:
            lines.append(f"  下级行政区（{len(sub)}）：")
            for s in sub[:30]:
                lines.append(f"    · {s.get('name', '')}  [{s.get('level', '')}]  "
                             f"adcode={s.get('adcode', '')}")
            if len(sub) > 30:
                lines.append(f"    ... 还有 {len(sub) - 30} 个")
        lines.append("")
    return "\n".join(lines)