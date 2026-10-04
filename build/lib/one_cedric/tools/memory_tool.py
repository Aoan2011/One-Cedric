"""记忆工具：让模型能主动读写长期记忆。"""
from __future__ import annotations

from .. import memory as _mem


def memory_remember(key: str, value: str, category: str = "preference",
                    tags: list | None = None) -> str:
    if not key or not value:
        return "ERROR: key 和 value 都不能为空"
    mid = _mem.add(key, value, category=category, tags=tags)
    if not mid:
        return "ERROR: 保存失败"
    return f"✓ 已记住 [{category}] {key} = {value}\n(id: {mid})"


def memory_recall(query: str = "", category: str = "") -> str:
    items = _mem.search(query) if query else _mem.list_all(category)
    if not items:
        return f"未找到匹配的记忆（query={query!r}）"
    lines = [f"找到 {len(items)} 条：", ""]
    for it in items[:30]:
        lines.append(
            f"  [{it.get('category','other')}] {it.get('key','')}"
            f" = {it.get('value','')}  (id={it.get('id','')})"
        )
    if len(items) > 30:
        lines.append(f"  ... 还有 {len(items) - 30} 条")
    return "\n".join(lines)


def memory_forget(token: str) -> str:
    if not token:
        return "ERROR: 需要 token"
    return f"✓ 已删除 '{token}'" if _mem.remove(token) else f"未找到 '{token}'"


def memory_list() -> str:
    return _mem.stats()