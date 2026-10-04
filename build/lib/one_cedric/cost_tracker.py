"""成本追踪：记录每轮成本、日累计、预算告警、异常检测、CSV 导出。

存储: ~/.one-cedric/costs.jsonl
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path


COST_LOG = Path.home() / ".one-cedric" / "costs.jsonl"
BUDGET_PATH = Path.home() / ".one-cedric" / "budget.toml"


def _ensure_dir() -> Path:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    return COST_LOG


def record(model: str, in_tok: int, out_tok: int,
           cached_tok: int, cost: float,
           session_id: str = "", note: str = "") -> None:
    if cost <= 0 and in_tok == 0 and out_tok == 0:
        return
    entry = {
        "ts": time.time(),
        "model": model,
        "in": int(in_tok or 0),
        "out": int(out_tok or 0),
        "cached": int(cached_tok or 0),
        "cost": float(cost or 0),
        "session": session_id,
        "note": note,
    }
    try:
        with open(_ensure_dir(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_all(max_lines: int = 100000) -> list:
    p = _ensure_dir()
    if not p.exists():
        return []
    entries = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries


def today_total() -> dict:
    now = time.time()
    today_start = now - (now % 86400) - time.timezone
    entries = [e for e in _read_all() if e.get("ts", 0) >= today_start]
    return _aggregate(entries)


def week_total() -> dict:
    now = time.time()
    week_start = now - 7 * 86400
    entries = [e for e in _read_all() if e.get("ts", 0) >= week_start]
    return _aggregate(entries)


def month_total() -> dict:
    now = time.time()
    month_start = now - 30 * 86400
    entries = [e for e in _read_all() if e.get("ts", 0) >= month_start]
    return _aggregate(entries)


def all_total() -> dict:
    return _aggregate(_read_all())


def _aggregate(entries: list) -> dict:
    total = {"cost": 0.0, "in": 0, "out": 0, "cached": 0, "turns": 0}
    by_model: dict = defaultdict(lambda: {
        "cost": 0.0, "in": 0, "out": 0, "cached": 0, "turns": 0,
    })
    for e in entries:
        c = float(e.get("cost", 0))
        i = int(e.get("in", 0))
        o = int(e.get("out", 0))
        ch = int(e.get("cached", 0))
        total["cost"] += c
        total["in"] += i
        total["out"] += o
        total["cached"] += ch
        total["turns"] += 1
        m = e.get("model", "?")
        by_model[m]["cost"] += c
        by_model[m]["in"] += i
        by_model[m]["out"] += o
        by_model[m]["cached"] += ch
        by_model[m]["turns"] += 1
    return {"total": total, "by_model": dict(by_model)}


def daily_buckets(days: int = 30) -> list:
    import datetime as _dt
    now = time.time()
    cutoff = now - days * 86400
    buckets: dict = defaultdict(lambda: {
        "cost": 0.0, "in": 0, "out": 0, "turns": 0,
    })
    for e in _read_all():
        ts = e.get("ts", 0)
        if ts < cutoff:
            continue
        d = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        b = buckets[d]
        b["cost"] += float(e.get("cost", 0))
        b["in"] += int(e.get("in", 0))
        b["out"] += int(e.get("out", 0))
        b["turns"] += 1
    result = []
    for i in range(days - 1, -1, -1):
        ts = now - i * 86400
        d = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        b = buckets.get(d, {"cost": 0, "in": 0, "out": 0, "turns": 0})
        result.append((d, b["cost"], b["in"], b["out"], b["turns"]))
    return result


def hourly_buckets(hours: int = 24) -> list:
    import datetime as _dt
    now = time.time()
    cutoff = now - hours * 3600
    buckets: dict = defaultdict(float)
    for e in _read_all():
        ts = e.get("ts", 0)
        if ts < cutoff:
            continue
        h = _dt.datetime.fromtimestamp(ts).strftime("%H:00")
        buckets[h] += float(e.get("cost", 0))
    result = []
    for i in range(hours - 1, -1, -1):
        ts = now - i * 3600
        h = _dt.datetime.fromtimestamp(ts).strftime("%H:00")
        result.append((h, buckets.get(h, 0.0)))
    return result


def by_model(period: str = "today") -> list:
    if period == "today":
        agg = today_total()
    elif period == "week":
        agg = week_total()
    elif period == "month":
        agg = month_total()
    else:
        agg = all_total()
    out = []
    for m, v in agg.get("by_model", {}).items():
        out.append((m, v["cost"], v["turns"]))
    out.sort(key=lambda x: -x[1])
    return out


# ═══════════════════════════════════════════════════════════════════════ #
# 预算
# ═══════════════════════════════════════════════════════════════════════ #

def load_budget() -> dict:
    p = BUDGET_PATH
    if not p.exists():
        return {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    try:
        import tomllib
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    out = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    for k in out:
        v = raw.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def save_budget(data: dict) -> bool:
    lines = ["# One Cedric 预算限制（美元）", "# 0 表示不限制", ""]
    for k in ("daily", "weekly", "monthly"):
        v = float(data.get(k, 0))
        lines.append(f"{k} = {v}")
    try:
        p = BUDGET_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def check_budget() -> dict:
    budget = load_budget()
    today = today_total()["total"]
    week = week_total()["total"]
    month = month_total()["total"]

    current = {
        "daily": {"budget": budget["daily"], "spent": today["cost"]},
        "weekly": {"budget": budget["weekly"], "spent": week["cost"]},
        "monthly": {"budget": budget["monthly"], "spent": month["cost"]},
    }
    for k in current:
        b = current[k]["budget"]
        s = current[k]["spent"]
        current[k]["pct"] = (s / b * 100) if b > 0 else 0
        current[k]["enabled"] = b > 0

    exceeded = []
    warnings = []
    for period in ("daily", "weekly", "monthly"):
        c = current[period]
        if not c["enabled"]:
            continue
        if c["spent"] >= c["budget"]:
            exceeded.append({
                "period": period,
                "budget": c["budget"],
                "spent": c["spent"],
                "pct": c["pct"],
            })
        elif c["pct"] >= 80:
            warnings.append({
                "period": period,
                "budget": c["budget"],
                "spent": c["spent"],
                "pct": c["pct"],
            })

    return {
        "ok": not exceeded,
        "exceeded": exceeded,
        "warnings": warnings,
        "current": current,
    }


def sparkline(values: list, width: int = 40) -> str:
    if not values:
        return "（无数据）"
    chars = " ▁▂▃▄▅▆▇█"
    mx = max(values) if values else 0
    if mx <= 0:
        return " " * min(len(values), width)
    if len(values) > width:
        step = len(values) / width
        reduced = [max(values[int(i * step):int((i + 1) * step)])
                   for i in range(width)]
        values = reduced
    out = []
    for v in values:
        idx = int(v / mx * (len(chars) - 1))
        out.append(chars[max(0, min(idx, len(chars) - 1))])
    return "".join(out)


def render_daily_chart(days: int = 30) -> str:
    buckets = daily_buckets(days=days)
    costs = [b[1] for b in buckets]
    total = sum(costs)
    mx = max(costs) if costs else 0

    lines = [f"过去 {days} 天成本", ""]
    lines.append(f"  max: {mx:.4f} USD")
    lines.append(f"  合计: {total:.4f} USD")
    lines.append("")
    lines.append("  " + sparkline(costs, width=min(60, days)))
    lines.append("")

    if buckets:
        first = buckets[0][0]
        last = buckets[-1][0]
        mid = buckets[len(buckets) // 2][0]
        line = "  " + first
        line += " " * max(1, 30 - len(first)) + mid
        line += " " * max(1, 30 - len(mid)) + last
        lines.append(line)

    top = sorted(buckets, key=lambda x: -x[1])[:5]
    top = [t for t in top if t[1] > 0]
    if top:
        lines.append("")
        lines.append("花费最高的 5 天：")
        for d, c, i, o, t in top:
            lines.append(f"  {d}  ${c:.4f}  ({t} 轮)")

    return "\n".join(lines)


def render_hourly_chart(hours: int = 24) -> str:
    buckets = hourly_buckets(hours=hours)
    costs = [b[1] for b in buckets]
    total = sum(costs)
    mx = max(costs) if costs else 0

    lines = [f"过去 {hours} 小时成本", ""]
    lines.append(f"  max: {mx:.4f} USD")
    lines.append(f"  合计: {total:.4f} USD")
    lines.append("")
    lines.append("  " + sparkline(costs, width=min(48, hours)))
    return "\n".join(lines)


def render_by_model(period: str = "today", top: int = 10) -> str:
    rows = by_model(period)
    if not rows:
        return "（无数据）"

    total = sum(r[1] for r in rows)
    lines = [f"按模型（{period}）· 总计 ${total:.4f}", ""]
    for m, c, turns in rows[:top]:
        pct = (c / total * 100) if total > 0 else 0
        bar_len = max(1, int(pct / 3))
        bar = "█" * bar_len
        lines.append(
            f"  {m:<28} ${c:>9.4f}  {pct:>5.1f}%  {bar}  ({turns} 轮)"
        )
    if len(rows) > top:
        lines.append(f"  ... 还有 {len(rows) - top} 个模型")
    return "\n".join(lines)


def format_budget_status() -> str:
    info = check_budget()
    lines = ["预算状态", ""]

    any_enabled = False
    labels = {"daily": "日", "weekly": "周", "monthly": "月"}
    for period in ("daily", "weekly", "monthly"):
        c = info["current"][period]
        if not c["enabled"]:
            continue
        any_enabled = True
        pct = c["pct"]
        if pct >= 100:
            mark = "❌"
        elif pct >= 80:
            mark = "⚠"
        else:
            mark = "✓"
        bar_len = min(30, int(pct / 3.3))
        bar = "█" * bar_len + "░" * (30 - bar_len)
        lines.append(
            f"  {mark} {labels[period]}  "
            f"${c['spent']:.4f} / ${c['budget']:.4f}  "
            f"[{bar}] {pct:.0f}%"
        )

    if not any_enabled:
        lines.append("  （未设置预算，用 /budget set daily <金额> 添加）")

    return "\n".join(lines)


def clear_log() -> int:
    p = _ensure_dir()
    if not p.exists():
        return 0
    try:
        n = sum(1 for _ in open(p, "r", encoding="utf-8"))
        p.unlink()
        return n
    except OSError:
        return 0


# ═══════════════════════════════════════════════════════════════════════ #
# 异常检测
# ═══════════════════════════════════════════════════════════════════════ #

def _today_entries() -> list:
    now = time.time()
    today_start = now - (now % 86400) - time.timezone
    return [e for e in _read_all() if e.get("ts", 0) >= today_start]


def detect_anomalies(days: int = 30, sensitivity: str = "medium") -> dict:
    k_map = {"low": 3.0, "medium": 2.0, "high": 1.5}
    k = k_map.get(sensitivity, 2.0)

    buckets = daily_buckets(days=days)
    if len(buckets) < 3:
        return {
            "daily_anomaly": None, "turn_anomalies": [],
            "baseline": {"mean": 0, "std": 0, "samples": 0},
            "today_cost": buckets[-1][1] if buckets else 0,
        }

    past = buckets[:-1]
    past_costs = [b[1] for b in past]
    today_cost = buckets[-1][1]

    n = len(past_costs)
    mean = sum(past_costs) / n if n else 0
    if n > 1:
        var = sum((c - mean) ** 2 for c in past_costs) / (n - 1)
        std = var ** 0.5
    else:
        std = 0

    daily_anomaly = None
    if std > 0 and today_cost > mean + k * std:
        daily_anomaly = {
            "today": today_cost, "mean": mean, "std": std,
            "threshold": mean + k * std,
            "multiple": today_cost / mean if mean > 0 else 0,
            "z_score": (today_cost - mean) / std if std > 0 else 0,
            "sensitivity": sensitivity,
        }
    elif std == 0 and today_cost > mean * 3 and mean > 0:
        daily_anomaly = {
            "today": today_cost, "mean": mean, "std": std,
            "threshold": mean * 3,
            "multiple": today_cost / mean, "z_score": 0,
            "sensitivity": sensitivity,
            "note": "历史波动为 0，用 3× 均值判定",
        }

    today_entries = _today_entries()
    turn_anomalies = []
    if len(today_entries) >= 5:
        costs = [e.get("cost", 0) for e in today_entries]
        sorted_costs = sorted(costs)
        baseline_pool = sorted_costs[:max(1, int(len(costs) * 0.8))]
        b_mean = sum(baseline_pool) / len(baseline_pool)
        if len(baseline_pool) > 1:
            b_var = sum((c - b_mean) ** 2 for c in baseline_pool) / \
                    (len(baseline_pool) - 1)
            b_std = b_var ** 0.5
        else:
            b_std = 0

        for e in today_entries:
            c = e.get("cost", 0)
            if b_std > 0 and c > b_mean + k * b_std:
                turn_anomalies.append({
                    "ts": e.get("ts", 0), "model": e.get("model", "?"),
                    "cost": c, "in": e.get("in", 0),
                    "out": e.get("out", 0), "cached": e.get("cached", 0),
                    "z_score": (c - b_mean) / b_std if b_std > 0 else 0,
                    "multiple": c / b_mean if b_mean > 0 else 0,
                })
            elif b_std == 0 and b_mean > 0 and c > b_mean * 3:
                turn_anomalies.append({
                    "ts": e.get("ts", 0), "model": e.get("model", "?"),
                    "cost": c, "in": e.get("in", 0),
                    "out": e.get("out", 0), "cached": e.get("cached", 0),
                    "z_score": 0, "multiple": c / b_mean,
                    "note": "历史波动为 0",
                })

    turn_anomalies.sort(key=lambda x: -x["cost"])

    return {
        "daily_anomaly": daily_anomaly,
        "turn_anomalies": turn_anomalies[:5],
        "baseline": {"mean": mean, "std": std, "samples": n},
        "today_cost": today_cost,
    }


def format_anomaly_report(days: int = 30,
                          sensitivity: str = "medium") -> str:
    r = detect_anomalies(days=days, sensitivity=sensitivity)
    lines = [
        f"成本异常检测（{days} 天基线 · 灵敏度 {sensitivity}）", ""]

    b = r["baseline"]
    lines.append(
        f"历史基线：均值 ${b['mean']:.4f} / 天，"
        f"标准差 ${b['std']:.4f}，样本 {b['samples']} 天"
    )
    lines.append(f"今日花费：${r['today_cost']:.4f}")
    lines.append("")

    da = r.get("daily_anomaly")
    if da:
        lines.append("🔴 每日异常")
        lines.append(
            f"  今日 ${da['today']:.4f} 超过阈值 ${da['threshold']:.4f}")
        lines.append(
            f"  是均值的 {da['multiple']:.1f} 倍，"
            f"z-score = {da['z_score']:.2f}")
        if da.get("note"):
            lines.append(f"  （{da['note']}）")
        lines.append("")
    else:
        lines.append("✓ 今日成本在正常范围内")
        lines.append("")

    ta = r.get("turn_anomalies") or []
    if ta:
        lines.append(f"🔴 单轮异常（{len(ta)} 条）")
        for a in ta:
            ts = time.strftime("%H:%M:%S", time.localtime(a["ts"]))
            lines.append(
                f"  {ts}  {a['model']}  ${a['cost']:.5f}  "
                f"({a['multiple']:.1f}×均值)")
            lines.append(
                f"          {a['in']}↑ {a['out']}↓ tok"
                + (f" · 缓存 {a['cached']}" if a.get("cached") else ""))
        lines.append("")
    else:
        lines.append("✓ 单轮成本无异常")

    return "\n".join(lines)


def check_turn_anomaly(turn_cost: float) -> dict | None:
    if turn_cost <= 0:
        return None

    today_entries = _today_entries()
    if len(today_entries) < 5:
        return None

    costs = [e.get("cost", 0) for e in today_entries]
    costs_sorted = sorted(costs)
    pool = costs_sorted[:max(1, int(len(costs_sorted) * 0.8))]
    b_mean = sum(pool) / len(pool)
    if len(pool) > 1:
        var = sum((c - b_mean) ** 2 for c in pool) / (len(pool) - 1)
        b_std = var ** 0.5
    else:
        b_std = 0

    if b_std > 0 and turn_cost > b_mean + 2.5 * b_std:
        return {
            "cost": turn_cost, "mean": b_mean, "std": b_std,
            "multiple": turn_cost / b_mean if b_mean > 0 else 0,
            "z_score": (turn_cost - b_mean) / b_std,
            "baseline_n": len(pool),
        }
    if b_std == 0 and b_mean > 0 and turn_cost > b_mean * 3:
        return {
            "cost": turn_cost, "mean": b_mean, "std": b_std,
            "multiple": turn_cost / b_mean, "z_score": 0,
            "baseline_n": len(pool), "note": "历史波动为 0",
        }
    return None


# ═══════════════════════════════════════════════════════════════════════ #
# 预测
# ═══════════════════════════════════════════════════════════════════════ #

def forecast(days_ahead: int = 30, lookback: int = 14) -> dict:
    buckets = daily_buckets(days=lookback)
    costs = [b[1] for b in buckets]

    nonzero = [c for c in costs if c > 0]
    n = len(nonzero)
    if n < 2:
        return {
            "daily_avg": sum(costs) / max(len(costs), 1),
            "daily_trend": 0.0, "month_forecast": 0.0,
            "month_end_total": 0.0, "confidence": 0.1,
            "samples": n, "note": "历史数据不足，预测不可靠",
        }

    xs = list(range(len(costs)))
    mean_x = sum(xs) / len(xs)
    mean_y = sum(costs) / len(costs)
    num = sum((xs[i] - mean_x) * (costs[i] - mean_y) for i in range(len(xs)))
    den = sum((xs[i] - mean_x) ** 2 for i in range(len(xs)))
    slope = num / den if den > 0 else 0.0
    intercept = mean_y - slope * mean_x

    future_total = 0.0
    for i in range(len(costs), len(costs) + days_ahead):
        future_total += max(0.0, intercept + slope * i)

    import datetime as _dt
    now = _dt.datetime.now()
    if now.month != 12:
        next_month = _dt.date(now.year, now.month + 1, 1)
    else:
        next_month = _dt.date(now.year + 1, 1, 1)
    cur_month = _dt.date(now.year, now.month, 1)
    days_in_month = (next_month - cur_month).days
    days_left = days_in_month - now.day + 1

    month_spent = month_total()["total"]["cost"]
    month_forecast = 0.0
    for i in range(len(costs), len(costs) + days_left):
        month_forecast += max(0.0, intercept + slope * i)

    variance = sum((c - mean_y) ** 2 for c in costs) / max(len(costs), 1)
    std = variance ** 0.5
    cv = std / mean_y if mean_y > 0 else 1.0
    confidence = max(0.1, min(0.95, n / 30 * (1 - min(cv, 1))))

    return {
        "daily_avg": round(mean_y, 4),
        "daily_trend": round(slope, 6),
        "trend_desc": ("上升" if slope > 0.01 else
                       "下降" if slope < -0.01 else "平稳"),
        "month_forecast": round(future_total, 4),
        "month_end_total": round(month_spent + month_forecast, 4),
        "month_spent_so_far": round(month_spent, 4),
        "days_left": days_left,
        "confidence": round(confidence, 2),
        "samples": n,
    }


def format_forecast(days_ahead: int = 30) -> str:
    f = forecast(days_ahead=days_ahead)
    lines = [
        f"成本预测（未来 {days_ahead} 天）", "",
        f"每日均值: ${f['daily_avg']:.4f}",
        f"每日趋势: {f['trend_desc']} (${f['daily_trend']:+.4f}/天)",
        f"未来 {days_ahead} 天预计: ${f['month_forecast']:.4f}",
        "",
        f"本月已花: ${f['month_spent_so_far']:.4f}",
        f"剩余天数: {f['days_left']}",
        f"本月月底预计: [bold]${f['month_end_total']:.4f}[/]",
        "",
        f"置信度: {f['confidence'] * 100:.0f}%  "
        f"（基于最近 {f['samples']} 天数据）",
    ]
    if f.get("note"):
        lines.append(f"⚠ {f['note']}")

    budget = load_budget()
    if budget["monthly"] > 0:
        pct = f["month_end_total"] / budget["monthly"] * 100
        warn = "❌ 将超支" if pct >= 100 else \
               "⚠ 接近上限" if pct >= 80 else "✓ 安全"
        lines.append("")
        lines.append(f"月预算 ${budget['monthly']:.2f}: "
                     f"预计占比 {pct:.0f}%  {warn}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════ #
# CSV 导出
# ═══════════════════════════════════════════════════════════════════════ #

def export_csv(path: str = "", period: str = "all",
               detail: str = "turn") -> tuple:
    import csv as _csv
    import io
    import datetime as _dt

    entries = _read_all()

    if period == "today":
        now = time.time()
        cutoff = now - (now % 86400) - time.timezone
        entries = [e for e in entries if e.get("ts", 0) >= cutoff]
    elif period == "week":
        cutoff = time.time() - 7 * 86400
        entries = [e for e in entries if e.get("ts", 0) >= cutoff]
    elif period == "month":
        cutoff = time.time() - 30 * 86400
        entries = [e for e in entries if e.get("ts", 0) >= cutoff]

    if not entries:
        return False, f"时间段 {period} 内无成本记录", 0

    buf = io.StringIO()
    w = _csv.writer(buf)

    if detail == "turn":
        w.writerow(["timestamp", "datetime", "model", "input_tokens",
                    "output_tokens", "cached_tokens", "cost_usd",
                    "session", "note"])
        for e in entries:
            ts = e.get("ts", 0)
            dt_str = _dt.datetime.fromtimestamp(ts).strftime(
                "%Y-%m-%d %H:%M:%S")
            w.writerow([
                f"{ts:.3f}", dt_str, e.get("model", ""),
                e.get("in", 0), e.get("out", 0), e.get("cached", 0),
                f"{e.get('cost', 0):.6f}", e.get("session", ""),
                e.get("note", ""),
            ])
        rows = len(entries)

    elif detail == "daily":
        buckets: dict = {}
        for e in entries:
            ts = e.get("ts", 0)
            d = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            b = buckets.setdefault(d, {
                "cost": 0.0, "in": 0, "out": 0, "cached": 0, "turns": 0})
            b["cost"] += float(e.get("cost", 0))
            b["in"] += int(e.get("in", 0))
            b["out"] += int(e.get("out", 0))
            b["cached"] += int(e.get("cached", 0))
            b["turns"] += 1
        w.writerow(["date", "turns", "input_tokens", "output_tokens",
                    "cached_tokens", "cost_usd"])
        for d in sorted(buckets.keys()):
            b = buckets[d]
            w.writerow([d, b["turns"], b["in"], b["out"], b["cached"],
                        f"{b['cost']:.6f}"])
        rows = len(buckets)

    elif detail == "model":
        buckets: dict = {}
        for e in entries:
            m = e.get("model", "?")
            b = buckets.setdefault(m, {
                "cost": 0.0, "in": 0, "out": 0, "cached": 0, "turns": 0})
            b["cost"] += float(e.get("cost", 0))
            b["in"] += int(e.get("in", 0))
            b["out"] += int(e.get("out", 0))
            b["cached"] += int(e.get("cached", 0))
            b["turns"] += 1
        w.writerow(["model", "provider", "turns", "input_tokens",
                    "output_tokens", "cached_tokens", "cost_usd",
                    "avg_cost_per_turn"])
        from .pricing import provider_of
        for m in sorted(buckets.keys()):
            b = buckets[m]
            avg = b["cost"] / b["turns"] if b["turns"] else 0
            w.writerow([m, provider_of(m), b["turns"], b["in"], b["out"],
                        b["cached"], f"{b['cost']:.6f}", f"{avg:.6f}"])
        rows = len(buckets)

    elif detail == "session":
        buckets: dict = {}
        for e in entries:
            sid = e.get("session", "") or "(无会话)"
            b = buckets.setdefault(sid, {
                "cost": 0.0, "in": 0, "out": 0, "cached": 0, "turns": 0,
                "models": set(),
                "first_ts": e.get("ts", 0), "last_ts": e.get("ts", 0)})
            b["cost"] += float(e.get("cost", 0))
            b["in"] += int(e.get("in", 0))
            b["out"] += int(e.get("out", 0))
            b["cached"] += int(e.get("cached", 0))
            b["turns"] += 1
            b["models"].add(e.get("model", "?"))
            b["first_ts"] = min(b["first_ts"], e.get("ts", 0))
            b["last_ts"] = max(b["last_ts"], e.get("ts", 0))
        w.writerow(["session_id", "start_time", "end_time",
                    "duration_min", "turns", "models",
                    "input_tokens", "output_tokens",
                    "cached_tokens", "cost_usd"])
        for sid in sorted(buckets.keys(),
                          key=lambda x: -buckets[x]["cost"]):
            b = buckets[sid]
            start = _dt.datetime.fromtimestamp(b["first_ts"]).strftime(
                "%Y-%m-%d %H:%M:%S")
            end = _dt.datetime.fromtimestamp(b["last_ts"]).strftime(
                "%Y-%m-%d %H:%M:%S")
            dur = (b["last_ts"] - b["first_ts"]) / 60
            w.writerow([sid, start, end, f"{dur:.1f}", b["turns"],
                        ",".join(sorted(b["models"])),
                        b["in"], b["out"], b["cached"],
                        f"{b['cost']:.6f}"])
        rows = len(buckets)

    else:
        return False, f"未知 detail: {detail}", 0

    content = buf.getvalue()

    if not path:
        suffix = f"-{period}" if period != "all" else ""
        path = str(Path.cwd() / f"cedric-costs{suffix}-{detail}.csv")

    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\ufeff" + content, encoding="utf-8")
    except OSError as exc:
        return False, str(exc), 0

    return True, str(out), rows


def list_export_formats() -> str:
    return (
        "detail 可选值：\n"
        "  turn     每轮一行（默认）\n"
        "  daily    按天汇总\n"
        "  model    按模型汇总\n"
        "  session  按会话汇总\n\n"
        "period 可选值：\n"
        "  today / week / month / all（默认）"
    )