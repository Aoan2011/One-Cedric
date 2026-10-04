"""cron 工具：让模型能创建/管理定时任务。"""
from __future__ import annotations

import datetime as _dt

from .. import cron as _cron


def cron_add(name: str, schedule: str, prompt: str) -> str:
    jid, err = _cron.add_job(name, schedule, prompt)
    if err:
        return f"ERROR: {err}"
    nxt = _cron.next_run_time(schedule)
    nxt_str = (_dt.datetime.fromtimestamp(nxt).strftime("%Y-%m-%d %H:%M")
               if nxt else "?")
    return (f"✓ 已创建任务 '{name}'\n"
            f"  id: {jid}\n"
            f"  表达式: {schedule}\n"
            f"  下次运行: {nxt_str}")


def cron_list() -> str:
    jobs = _cron.list_jobs()
    if not jobs:
        return "无定时任务。用 cron_add 创建。"
    lines = [f"共 {len(jobs)} 个定时任务：", ""]
    for j in jobs:
        lines.append(_cron.format_job(j))
        lines.append("")
    return "\n".join(lines)


def cron_remove(token: str) -> str:
    if not token:
        return "ERROR: 需要 token"
    return f"✓ 已删除 '{token}'" if _cron.remove_job(token) \
        else f"未找到 '{token}'"


def cron_enable(token: str, enabled: bool = True) -> str:
    ok = _cron.enable_job(token, enabled)
    verb = "启用" if enabled else "禁用"
    return f"✓ 已{verb} '{token}'" if ok else f"未找到 '{token}'"


def cron_logs(token: str, limit: int = 5) -> str:
    j = _cron.get_job(token)
    if not j:
        return f"未找到 '{token}'"
    files = _cron.list_logs(j["id"], limit=limit)
    if not files:
        return f"'{j.get('name')}' 无日志"
    lines = [f"任务 '{j.get('name')}' 最近 {len(files)} 次：", ""]
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        head = content.split("\n")[:8]
        lines.append(f"── {f.name} ──")
        lines.extend(head)
        lines.append("")
    return "\n".join(lines)