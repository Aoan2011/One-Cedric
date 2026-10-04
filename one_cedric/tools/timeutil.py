"""时间/日期相关工具。"""
from __future__ import annotations

import calendar
import datetime as _dt
import re
import time as _time


def now_info() -> str:
    now = _dt.datetime.now()
    utc = _dt.datetime.utcnow()
    ts = _time.time()
    weekday = ["周一", "周二", "周三", "周四", "周五",
               "周六", "周日"][now.weekday()]
    return (f"本地时间: {now.strftime('%Y-%m-%d %H:%M:%S')}（{weekday}）\n"
            f"UTC 时间: {utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Unix 时间戳: {int(ts)}\n"
            f"时区: {now.astimezone().tzinfo}\n"
            f"ISO 8601: {now.isoformat()}")


def _re_offset(s):
    m = re.match(r"^\s*([+\-])\s*(\d+)\s*([smhdwMy])\s*$", s or "")
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3)


def _days_in_month(y, m):
    return calendar.monthrange(y, m)[1]


def _add_months(dt: _dt.datetime, months: int) -> _dt.datetime:
    y = dt.year
    m = dt.month - 1 + months
    y += m // 12
    m = m % 12 + 1
    day = min(dt.day, _days_in_month(y, m))
    return dt.replace(year=y, month=m, day=day)


def date_calc(base: str = "", offset: str = "+1d",
              format: str = "%Y-%m-%d") -> str:
    if base:
        try:
            base_dt = _dt.datetime.fromisoformat(base)
        except ValueError:
            return f"ERROR: base 不是 ISO 格式: {base}"
    else:
        base_dt = _dt.datetime.now()
    m = _re_offset(offset)
    if not m:
        return (f"ERROR: offset 格式错误: {offset}"
                f"（示例 +1d, -3w, +2h, +30M）")
    sign, n, unit = m
    delta = n * (1 if sign == "+" else -1)
    try:
        if unit == "s":
            result = base_dt + _dt.timedelta(seconds=delta)
        elif unit == "M":
            result = base_dt + _dt.timedelta(minutes=delta)
        elif unit == "h":
            result = base_dt + _dt.timedelta(hours=delta)
        elif unit == "d":
            result = base_dt + _dt.timedelta(days=delta)
        elif unit == "w":
            result = base_dt + _dt.timedelta(weeks=delta)
        elif unit == "m":
            result = _add_months(base_dt, delta)
        elif unit == "y":
            result = _add_months(base_dt, delta * 12)
        else:
            return f"ERROR: 未知单位: {unit}"
    except Exception as exc:
        return f"ERROR: 计算失败: {exc}"
    return (f"基准: {base_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"偏移: {offset}\n"
            f"结果: {result.strftime(format)}\n"
            f"ISO: {result.isoformat()}")


def timezone_convert(time_str: str, from_tz: str, to_tz: str,
                     format: str = "%Y-%m-%d %H:%M:%S") -> str:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        return "ERROR: 需要 Python 3.9+ 的 zoneinfo"
    try:
        src = ZoneInfo(from_tz)
        dst = ZoneInfo(to_tz)
    except Exception as exc:
        return f"ERROR: 时区无效: {exc}"
    try:
        dt = _dt.datetime.fromisoformat(time_str)
    except ValueError:
        return "ERROR: 时间格式错误（用 ISO 格式如 2024-01-01T12:00:00）"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=src)
    converted = dt.astimezone(dst)
    return (f"原时间: {dt.strftime(format)} ({from_tz})\n"
            f"转换后: {converted.strftime(format)} ({to_tz})\n"
            f"UTC: "
            f"{converted.astimezone(_dt.timezone.utc).strftime(format)}")


def cron_next(expression: str, count: int = 5) -> str:
    parts = (expression or "").split()
    if len(parts) != 5:
        return "ERROR: cron 表达式需要 5 段（分 时 日 月 周）"
    try:
        n = max(1, min(int(count), 20))
    except (TypeError, ValueError):
        n = 5

    def _match(field, value):
        if field == "*":
            return True
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0
        for token in field.split(","):
            if "-" in token:
                a, b = token.split("-", 1)
                if int(a) <= value <= int(b):
                    return True
            else:
                if int(token) == value:
                    return True
        return False

    results = []
    now = _dt.datetime.now().replace(second=0, microsecond=0)
    candidate = now + _dt.timedelta(minutes=1)
    for _ in range(200000):
        if (candidate - now).days > 400:
            break
        m, h, d, mo, wd = (candidate.minute, candidate.hour,
                            candidate.day, candidate.month,
                            candidate.weekday())
        cron_wd = (wd + 1) % 7
        if (_match(parts[0], m) and _match(parts[1], h)
                and _match(parts[2], d) and _match(parts[3], mo)
                and _match(parts[4], cron_wd)):
            results.append(candidate.strftime("%Y-%m-%d %H:%M  %a"))
            if len(results) >= n:
                break
        candidate += _dt.timedelta(minutes=1)
    if not results:
        return f"未找到下次执行时间（表达式: {expression}）"
    return (f"cron: {expression}\n"
            f"下次 {len(results)} 次执行：\n"
            + "\n".join(f"  {r}" for r in results))