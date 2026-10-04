"""长期记忆：跨会话记住用户偏好、项目背景。

存储: ~/.one-cedric/memory.toml
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None


MEMORY_PATH = Path.home() / ".one-cedric" / "memory.toml"
CATEGORIES = ("preference", "context", "profile", "project", "other")


def _path() -> Path:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return MEMORY_PATH


def _load() -> dict:
    p = _path()
    if not p.exists() or tomllib is None:
        return {"items": []}
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}
    items = raw.get("items")
    if not isinstance(items, list):
        return {"items": []}
    return {"items": items}


def _esc(s: str) -> str:
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n"))


def _save(data: dict) -> bool:
    p = _path()
    items = data.get("items") or []
    lines = ["# One Cedric 长期记忆", ""]
    for it in items:
        lines.append("[[items]]")
        lines.append(f'id = "{_esc(it.get("id", ""))}"')
        lines.append(f'key = "{_esc(it.get("key", ""))}"')
        lines.append(f'value = "{_esc(it.get("value", ""))}"')
        lines.append(f'category = "{_esc(it.get("category", "other"))}"')
        lines.append(f"created_at = {float(it.get('created_at', 0))}")
        lines.append(f"updated_at = {float(it.get('updated_at', 0))}")
        lines.append(f'source = "{_esc(it.get("source", "user"))}"')
        tags = it.get("tags") or []
        tag_str = ", ".join(f'"{_esc(str(t))}"' for t in tags)
        lines.append(f"tags = [{tag_str}]")
        lines.append("")
    try:
        p.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def _new_id() -> str:
    return "mem_" + secrets.token_hex(4)


def _find_index(items: list, token: str):
    t = (token or "").strip().lower()
    if not t:
        return None
    for i, it in enumerate(items):
        if t == it.get("id", "").lower():
            return i
    for i, it in enumerate(items):
        if t == it.get("key", "").lower():
            return i
    for i, it in enumerate(items):
        if t in it.get("key", "").lower() or t in it.get("value", "").lower():
            return i
    return None


def add(key: str, value: str, category: str = "other",
        tags: list | None = None, source: str = "user") -> str:
    key = (key or "").strip()
    value = (value or "").strip()
    if not key:
        return ""
    if category not in CATEGORIES:
        category = "other"
    data = _load()
    items = data["items"]
    now = time.time()
    for it in items:
        if it.get("key", "").lower() == key.lower():
            it["value"] = value
            it["category"] = category
            if tags:
                it["tags"] = [str(t) for t in tags if str(t).strip()]
            it["updated_at"] = now
            _save(data)
            return it.get("id", "")
    mid = _new_id()
    items.append({
        "id": mid, "key": key, "value": value, "category": category,
        "created_at": now, "updated_at": now, "source": source,
        "tags": [str(t) for t in (tags or []) if str(t).strip()],
    })
    _save(data)
    return mid


def remove(token: str) -> bool:
    data = _load()
    items = data["items"]
    i = _find_index(items, token)
    if i is None:
        return False
    items.pop(i)
    return _save(data)


def get(token: str) -> dict | None:
    data = _load()
    i = _find_index(data["items"], token)
    return data["items"][i] if i is not None else None


def list_all(category: str = "") -> list[dict]:
    items = _load()["items"]
    if category:
        items = [x for x in items if x.get("category") == category]
    return sorted(items, key=lambda x: x.get("updated_at", 0), reverse=True)


def search(query: str) -> list[dict]:
    if not query:
        return list_all()
    q = query.lower()
    out = []
    for x in list_all():
        if (q in x.get("key", "").lower()
                or q in x.get("value", "").lower()
                or q in x.get("id", "").lower()):
            out.append(x)
    return out


def clear() -> int:
    data = _load()
    n = len(data["items"])
    data["items"] = []
    _save(data)
    return n


def to_prompt_block(max_items: int = 50, max_chars: int = 4000) -> str:
    items = list_all()
    if not items:
        return ""
    lines = ["## 长期记忆", "",
             "以下是你记住的关于用户和项目的持久信息，"
             "对话中优先遵守（除非用户明确改变）：", ""]
    total = 0
    shown = 0
    for it in items[:max_items]:
        line = (f"- [{it.get('category', 'other')}] "
                f"**{it.get('key', '')}**: {it.get('value', '')}")
        if total + len(line) > max_chars:
            lines.append(f"- ...（还有 {len(items) - shown} 条未展示）")
            break
        lines.append(line)
        total += len(line)
        shown += 1
    return "\n".join(lines)


def stats() -> str:
    items = list_all()
    if not items:
        return "长期记忆为空。"
    by_cat: dict = {}
    for it in items:
        c = it.get("category", "other")
        by_cat[c] = by_cat.get(c, 0) + 1
    lines = [f"共 {len(items)} 条：", ""]
    for c in CATEGORIES:
        if c in by_cat:
            lines.append(f"  {c}: {by_cat[c]}")
    lines.append("")
    lines.append(f"文件: {MEMORY_PATH}")
    return "\n".join(lines)