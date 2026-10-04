"""梦境工具：让模型能主动做梦。"""
from __future__ import annotations

from .. import dream as _dream


def dream_run(days: int = 3, focus: str = "",
              save_memories: bool = False, parent=None) -> str:
    if parent is None:
        return "ERROR: 需要 parent 实例"
    r = _dream.run_dream(parent, days=days, focus=focus,
                         save_memories=save_memories)
    if not r.get("ok"):
        return f"ERROR: {r.get('error', '未知错误')}"
    lines = [
        f"🌙 梦境完成 · {r['duration']}s",
        f"分析: {r['stats']['sessions']} 个会话 · "
        f"{r['stats']['turns']} 轮 · {r['stats']['tools']} 次工具调用",
        "",
        r["answer"],
    ]
    if r.get("memory_candidates"):
        lines.append("")
        lines.append(f"💡 {len(r['memory_candidates'])} 条记忆候选"
                     + ("（已保存）" if r.get("saved_memories") else "（未保存）"))
    lines.append("")
    lines.append(f"已保存: {r['path']}")
    return "\n".join(lines)


def dream_list(limit: int = 10) -> str:
    dreams = _dream.list_dreams(limit=limit)
    if not dreams:
        return "还没有做过梦。"
    import time as _t
    lines = [f"最近 {len(dreams)} 个梦境：", ""]
    for d in dreams:
        ts = _t.strftime("%m-%d %H:%M", _t.localtime(d["mtime"]))
        lines.append(f"  {ts}  {d['id']}  ({d['size']} bytes)")
    lines.append("")
    lines.append("用 dream_read <id> 查看内容。")
    return "\n".join(lines)


def dream_read(dream_id: str) -> str:
    text = _dream.read_dream(dream_id)
    return text or f"未找到 {dream_id}"


def dream_stats() -> str:
    return _dream.dream_stats()