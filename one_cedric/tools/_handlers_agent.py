"""Agent / 记忆 / 定时 / 梦境 / 成本 / LSP / Computer 只读 handlers。"""
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


def _core_stub(name: str) -> str:
    return (f"ERROR: 工具 '{name}' 需要 core 层实例（session/copilot）。"
            f"不应直接走 dispatch_tool。")


# ═══════════════════════════════════════════════════════════════════════ #
# Agent（core 层处理，这里给明确错误）
# ═══════════════════════════════════════════════════════════════════════ #

def _spawn_agent(root: Path, args: dict) -> str:
    return _core_stub("spawn_agent")


def _multi_review(root: Path, args: dict) -> str:
    return _core_stub("multi_review")


def _ask_user(root: Path, args: dict) -> str:
    return _core_stub("ask_user")


# ═══════════════════════════════════════════════════════════════════════ #
# 记忆
# ═══════════════════════════════════════════════════════════════════════ #

def _memory_recall(root: Path, args: dict) -> str:
    return _imp("memory_tool").memory_recall(
        args.get("query", ""), args.get("category", ""))


def _memory_list(root: Path, args: dict) -> str:
    return _imp("memory_tool").memory_list()


# ═══════════════════════════════════════════════════════════════════════ #
# 定时任务
# ═══════════════════════════════════════════════════════════════════════ #

def _cron_list(root: Path, args: dict) -> str:
    return _imp("cron_tool").cron_list()


def _cron_logs(root: Path, args: dict) -> str:
    err = _require(args, "token")
    if err:
        return err
    return _imp("cron_tool").cron_logs(
        args["token"], args.get("limit", 5))


# ═══════════════════════════════════════════════════════════════════════ #
# 梦境
# ═══════════════════════════════════════════════════════════════════════ #

def _dream_list(root: Path, args: dict) -> str:
    return _imp("dream_tool").dream_list(args.get("limit", 10))


def _dream_read(root: Path, args: dict) -> str:
    err = _require(args, "dream_id")
    if err:
        return err
    return _imp("dream_tool").dream_read(args["dream_id"])


def _dream_stats(root: Path, args: dict) -> str:
    return _imp("dream_tool").dream_stats()


# ═══════════════════════════════════════════════════════════════════════ #
# 成本
# ═══════════════════════════════════════════════════════════════════════ #

def _cost_report(root: Path, args: dict) -> str:
    mod = _imp("cost_tracker")
    period = args.get("period", "today")
    info_map = {
        "today": mod.today_total,
        "week": mod.week_total,
        "month": mod.month_total,
        "all": mod.all_total,
    }
    info = info_map.get(period, mod.today_total)()["total"]
    lines = [
        f"{period} 成本: ${info['cost']:.4f}",
        f"{info['turns']} 轮 · {info['in']}↑ {info['out']}↓ tok · "
        f"缓存 {info['cached']}",
    ]
    if args.get("chart"):
        if period == "today":
            lines.append("")
            lines.append(mod.render_hourly_chart(24))
        else:
            days = {"week": 7, "month": 30, "all": 90}.get(period, 30)
            lines.append("")
            lines.append(mod.render_daily_chart(days))
    if args.get("by_model"):
        lines.append("")
        lines.append(mod.render_by_model(period))
    return "\n".join(lines)


def _budget_status(root: Path, args: dict) -> str:
    return _imp("cost_tracker").format_budget_status()


def _cost_anomaly(root: Path, args: dict) -> str:
    days = args.get("days", 30)
    try:
        days = max(7, min(int(days), 180))
    except (TypeError, ValueError):
        days = 30
    sens = args.get("sensitivity", "medium")
    if sens not in ("low", "medium", "high"):
        sens = "medium"
    return _imp("cost_tracker").format_anomaly_report(
        days=days, sensitivity=sens)


def _cost_forecast(root: Path, args: dict) -> str:
    days = args.get("days_ahead", 30)
    try:
        days = max(7, min(int(days), 365))
    except (TypeError, ValueError):
        days = 30
    return _imp("cost_tracker").format_forecast(days_ahead=days)


def _cost_export(root: Path, args: dict) -> str:
    # 实际写操作在 core 层，这里给出提示
    return _core_stub("cost_export")


# ═══════════════════════════════════════════════════════════════════════ #
# LSP
# ═══════════════════════════════════════════════════════════════════════ #

def _lsp_hover(root: Path, args: dict) -> str:
    err = _require(args, "path", "line", "column")
    if err:
        return err
    return _imp("lsp.tools").lsp_hover(
        root, args["path"], args["line"], args["column"])


def _lsp_definition(root: Path, args: dict) -> str:
    err = _require(args, "path", "line", "column")
    if err:
        return err
    return _imp("lsp.tools").lsp_definition(
        root, args["path"], args["line"], args["column"])


def _lsp_references(root: Path, args: dict) -> str:
    err = _require(args, "path", "line", "column")
    if err:
        return err
    return _imp("lsp.tools").lsp_references(
        root, args["path"], args["line"], args["column"],
        include_declaration=bool(
            args.get("include_declaration", True)))


def _lsp_diagnostics(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    return _imp("lsp.tools").lsp_diagnostics(root, args["path"])


def _lsp_symbols(root: Path, args: dict) -> str:
    err = _require(args, "path")
    if err:
        return err
    return _imp("lsp.tools").lsp_symbols(root, args["path"])


def _lsp_status(root: Path, args: dict) -> str:
    return _imp("lsp.tools").lsp_status(root)


# ═══════════════════════════════════════════════════════════════════════ #
# Computer（只读）
# ═══════════════════════════════════════════════════════════════════════ #

def _screen_info(root: Path, args: dict) -> str:
    return _imp("computer.tools").screen_info(root)


# ═══════════════════════════════════════════════════════════════════════ #
# 注册表
# ═══════════════════════════════════════════════════════════════════════ #

HANDLERS = {
    # Agent（stub）
    "spawn_agent":        _spawn_agent,
    "multi_review":       _multi_review,
    "ask_user":           _ask_user,
    # 记忆
    "memory_recall":      _memory_recall,
    "memory_list":        _memory_list,
    # 定时
    "cron_list":          _cron_list,
    "cron_logs":          _cron_logs,
    # 梦境
    "dream_list":         _dream_list,
    "dream_read":         _dream_read,
    "dream_stats":        _dream_stats,
    # 成本
    "cost_report":        _cost_report,
    "budget_status":      _budget_status,
    "cost_anomaly":       _cost_anomaly,
    "cost_forecast":      _cost_forecast,
    "cost_export":        _cost_export,
    # LSP
    "lsp_hover":          _lsp_hover,
    "lsp_definition":     _lsp_definition,
    "lsp_references":     _lsp_references,
    "lsp_diagnostics":    _lsp_diagnostics,
    "lsp_symbols":        _lsp_symbols,
    "lsp_status":         _lsp_status,
    # Computer
    "screen_info":        _screen_info,
}