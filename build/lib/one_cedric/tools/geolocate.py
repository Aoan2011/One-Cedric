"""网络定位：先粗查（IP），再询问用户是否提供精确位置。
风险告知：
  - IP 定位只能到城市级，且不精确
  - 精确到区县需要用户主动提供
  - 所有数据不离开本机（除非用户主动调用高德等 API）
"""
from __future__ import annotations
import json
import time
from pathlib import Path
# 全局：本次会话用户是否同意提供精确位置
_EXACT_LOCATION: dict = {}
_USER_CONSENT: bool = False
def reset_consent() -> None:
    global _USER_CONSENT, _EXACT_LOCATION
    _USER_CONSENT = False
    _EXACT_LOCATION = {}
def has_consent() -> bool:
    return _USER_CONSENT
def set_consent(consented: bool, data: dict | None = None) -> None:
    global _USER_CONSENT, _EXACT_LOCATION
    _USER_CONSENT = bool(consented)
    if data:
        _EXACT_LOCATION = dict(data)
def get_exact_location() -> dict:
    return dict(_EXACT_LOCATION)
# ═══════════════════════════════════════════════════════════════════════ #
# 粗查（IP 定位）
# ═══════════════════════════════════════════════════════════════════════ #
def _try_ipapi_co() -> dict:
    """ipapi.co — 免费，无需 key。"""
    try:
        import requests
        r = requests.get("https://ipapi.co/json/", timeout=8,
                         headers={"User-Agent": "OneCedric/1.0"})
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "ip": d.get("ip", ""),
            "country": d.get("country_name", ""),
            "country_code": d.get("country_code", ""),
            "region": d.get("region", ""),
            "city": d.get("city", ""),
            "postal": d.get("postal", ""),
            "latitude": d.get("latitude"),
            "longitude": d.get("longitude"),
            "timezone": d.get("timezone", ""),
            "isp": d.get("org", ""),
            "source": "ipapi.co",
        }
    except Exception:
        return {}
def _try_ipinfo_io() -> dict:
    try:
        import requests
        r = requests.get("https://ipinfo.io/json", timeout=8,
                         headers={"User-Agent": "OneCedric/1.0"})
        if r.status_code != 200:
            return {}
        d = r.json()
        loc = d.get("loc", ",").split(",")
        return {
            "ip": d.get("ip", ""),
            "country": d.get("country", ""),
            "region": d.get("region", ""),
            "city": d.get("city", ""),
            "postal": d.get("postal", ""),
            "latitude": float(loc[0]) if loc and loc[0] else None,
            "longitude": float(loc[1]) if len(loc) > 1 and loc[1] else None,
            "timezone": d.get("timezone", ""),
            "isp": d.get("org", ""),
            "source": "ipinfo.io",
        }
    except Exception:
        return {}
def _try_ip_api_com() -> dict:
    try:
        import requests
        r = requests.get("http://ip-api.com/json/?lang=zh-CN", timeout=8)
        if r.status_code != 200:
            return {}
        d = r.json()
        if d.get("status") != "success":
            return {}
        return {
            "ip": d.get("query", ""),
            "country": d.get("country", ""),
            "country_code": d.get("countryCode", ""),
            "region": d.get("regionName", ""),
            "city": d.get("city", ""),
            "postal": d.get("zip", ""),
            "latitude": d.get("lat"),
            "longitude": d.get("lon"),
            "timezone": d.get("timezone", ""),
            "isp": d.get("isp", ""),
            "source": "ip-api.com",
        }
    except Exception:
        return {}
def rough_locate() -> dict:
    """粗查：尝试多个 IP 服务，返回最完整的一份。"""
    results = []
    for fn in (_try_ipapi_co, _try_ipinfo_io, _try_ip_api_com):
        d = fn()
        if d.get("ip"):
            results.append(d)
    if not results:
        return {"ok": False, "error": "所有 IP 定位服务都失败"}
    # 合并：取字段最多的
    best = max(results, key=lambda x: sum(1 for v in x.values() if v))
    # 交叉验证：多源城市一致则置信度更高
    cities = {r.get("city", "") for r in results if r.get("city")}
    best["confidence"] = "高" if len(cities) == 1 else \
                          "中" if len(cities) <= 2 else "低"
    best["sources"] = [r.get("source") for r in results]
    best["ok"] = True
    return best
def format_rough(d: dict) -> str:
    """格式化粗查结果。"""
    if not d.get("ok"):
        return f"粗查失败: {d.get('error', '未知')}"
    lines = [
        "网络定位（粗查）",
        "",
        f"  IP:        {d.get('ip', '?')}",
        f"  国家:      {d.get('country', '?')}"
        + (f" ({d.get('country_code', '')})" if d.get("country_code") else ""),
        f"  省/州:     {d.get('region', '?')}",
        f"  城市:      {d.get('city', '?')}",
    ]
    if d.get("postal"):
        lines.append(f"  邮编:      {d['postal']}")
    if d.get("latitude") and d.get("longitude"):
        lines.append(f"  坐标:      {d['latitude']:.2f}, "
                     f"{d['longitude']:.2f}（约 10km 精度）")
    if d.get("timezone"):
        lines.append(f"  时区:      {d['timezone']}")
    if d.get("isp"):
        lines.append(f"  ISP:       {d['isp']}")
    lines.append("")
    lines.append(f"  数据源:    {', '.join(d.get('sources', []))}")
    lines.append(f"  置信度:    {d.get('confidence', '?')}")
    lines.append("")
    lines.append("⚠ 风险告知：")
    lines.append("  · IP 定位只能到城市级，且不精确（10km 以上）")
    lines.append("  · 定位通过第三方 API 完成，本机会请求外网")
    lines.append("  · 若需精确到区县，需要用户主动提供")
    return "\n".join(lines)
# ═══════════════════════════════════════════════════════════════════════ #
# 生成"询问用户是否提供精确位置"的提示
# ═══════════════════════════════════════════════════════════════════════ #
def build_consent_prompt() -> str:
    """生成询问用户的话术。"""
    return (
        "是否需要提供更精确的位置？\n\n"
        "可以按以下格式提供：\n"
        "  · 国-省-市-区（如：中国-广东省-深圳市-南山区）\n"
        "  · 或具体地址（如：深圳市南山区科技园）\n"
        "  · 或经纬度（如：22.5431, 114.0579）\n\n"
        "提供后，涉及地理位置的任务（天气、地图、路线）会使用精确位置。\n"
        "所有数据仅保存在本机会话内，不会上传。\n\n"
        "风险提示：\n"
        "  · 提供精确位置会让 AI 知道你所在的具体区域\n"
        "  · 若担心隐私，可以不提供，继续用粗查结果"
    )
def parse_location_input(text: str) -> dict:
    """解析用户输入的精确位置。
    支持：
      · "中国-广东省-深圳市-南山区"（横线分隔）
      · "深圳市南山区"（简写）
      · "22.5431, 114.0579"（坐标）
    """
    text = (text or "").strip()
    if not text:
        return {}
    # 坐标格式
    import re
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", text)
    if m:
        try:
            return {
                "type": "coords",
                "latitude": float(m.group(1)),
                "longitude": float(m.group(2)),
                "raw": text,
            }
        except ValueError:
            pass
    # 横线分隔
    if "-" in text or "－" in text:
        parts = re.split(r"[-－]", text)
        parts = [p.strip() for p in parts if p.strip()]
        result = {"type": "structured", "raw": text}
        keys = ["country", "province", "city", "district"]
        for i, p in enumerate(parts[:4]):
            result[keys[i]] = p
        return result
    # 纯文本
    return {"type": "text", "raw": text}
def format_exact(d: dict) -> str:
    if not d:
        return "（未提供）"
    t = d.get("type", "")
    if t == "coords":
        return f"坐标: {d['latitude']}, {d['longitude']}"
    if t == "structured":
        parts = [d.get(k, "") for k in
                 ("country", "province", "city", "district")]
        parts = [p for p in parts if p]
        return " / ".join(parts)
    return d.get("raw", "")
