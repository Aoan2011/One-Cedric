"""梦境：后台回顾最近会话，生成洞察和记忆候选。

存储: ~/.one-cedric/dreams/dream_<timestamp>.md
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path


DREAM_DIR = Path.home() / ".one-cedric" / "dreams"


def _ensure_dir() -> Path:
    DREAM_DIR.mkdir(parents=True, exist_ok=True)
    return DREAM_DIR


DREAM_PROMPT = """你正在做「梦境回顾」。分析下面最近的会话摘要，输出结构化洞察。

要求：
1. 用简体中文
2. 严格按以下格式，不要额外解释：

## 回想
（1-2 句总结最近在做什么，最高频的主题）

## 洞察
- 观察 1
- 观察 2
（3-6 条，关于用户的工作模式、习惯、未完成事项）

## 建议记忆
- [preference] key: value
- [project] key: value
（0-5 条，只有确实值得长期记住的才写）

## 明日建议
- 建议 1
- 建议 2
（2-4 条可执行的小建议）

只输出上述四部分。"""


def collect_recent_context(copilot, days: int = 3,
                            max_sessions: int = 20,
                            max_chars: int = 30000) -> tuple:
    from .storage import list_session_files
    cutoff = time.time() - days * 86400
    try:
        all_sessions = list_session_files()
    except Exception:
        all_sessions = []

    filtered = [s for s in all_sessions if s.get("updated_at", 0) >= cutoff]
    filtered.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    filtered = filtered[:max_sessions]

    if not filtered:
        return "", {"sessions": 0, "turns": 0, "tools": 0}

    lines = []
    total_turns = 0
    total_tools = 0

    for s in filtered:
        title = s.get("title") or "（未命名）"
        ts = time.strftime("%Y-%m-%d %H:%M",
                           time.localtime(s.get("updated_at", 0)))
        lines.append(f"### 会话 {title}  ·  {ts}")
        for m in s.get("messages", []):
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role == "user":
                total_turns += 1
                lines.append(f"用户：{content[:300]}")
            elif role == "assistant" and content:
                lines.append(f"助手：{content[:400]}")
            elif role == "tool":
                total_tools += 1
        lines.append("")
        if sum(len(x) for x in lines) > max_chars:
            lines.append("...（已截断）")
            break

    return "\n".join(lines), {
        "sessions": len(filtered),
        "turns": total_turns,
        "tools": total_tools,
    }


def _extract_memories(text: str) -> list:
    out = []
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## 建议记忆"):
            in_section = True
            continue
        if in_section and s.startswith("## "):
            break
        if not in_section or not s.startswith("-"):
            continue
        body = s.lstrip("- ").strip()
        if not body.startswith("["):
            continue
        try:
            rest = body[1:]
            end = rest.index("]")
            cat = rest[:end].strip()
            rest = rest[end + 1:].strip()
            if ":" not in rest:
                continue
            key, _, value = rest.partition(":")
            out.append({
                "category": cat or "other",
                "key": key.strip(),
                "value": value.strip(),
            })
        except (ValueError, IndexError):
            continue
    return out


def run_dream(copilot, days: int = 3, focus: str = "",
              save_memories: bool = False) -> dict:
    t0 = time.time()
    context, stats = collect_recent_context(copilot, days=days)

    if not context:
        return {
            "ok": False,
            "error": f"最近 {days} 天没有会话记录",
            "duration": round(time.time() - t0, 2),
        }

    if focus:
        context = f"**重点关注**：{focus}\n\n" + context

    msgs = [
        {"role": "system", "content": DREAM_PROMPT},
        {"role": "user", "content": "最近的会话摘要：\n\n" + context},
    ]

    try:
        raw = copilot._once_chat(msgs, temperature=0.4)
    except SystemExit as exc:
        return {"ok": False, "error": str(exc),
                "duration": round(time.time() - t0, 2)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "duration": round(time.time() - t0, 2)}

    answer = (raw or "").strip()
    if not answer:
        return {"ok": False, "error": "模型返回空内容",
                "duration": round(time.time() - t0, 2)}

    memory_candidates = _extract_memories(answer)

    ts = time.strftime("%Y%m%d-%H%M%S")
    dream_id = f"dream_{ts}_{secrets.token_hex(2)}"
    path = _ensure_dir() / f"{dream_id}.md"

    lines = [
        f"# 🌙 梦境 · {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 会话数: {stats['sessions']}",
        f"- 轮数: {stats['turns']}",
        f"- 工具调用: {stats['tools']}",
        f"- 时长: {round(time.time() - t0, 2)}s",
        f"- focus: {focus or '（无）'}",
        "",
        "---",
        "",
        answer,
    ]
    if memory_candidates:
        lines += ["", "---", "", "## 记忆候选（未自动保存）"]
        for c in memory_candidates:
            lines.append(f"- [{c['category']}] {c['key']}: {c['value']}")

    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"保存失败: {exc}",
                "duration": round(time.time() - t0, 2)}

    saved = []
    if save_memories and memory_candidates:
        try:
            from . import memory as _mem
            for c in memory_candidates:
                mid = _mem.add(c["key"], c["value"],
                               category=c["category"], source="dream")
                if mid:
                    saved.append(c)
        except Exception:
            pass

    return {
        "ok": True,
        "answer": answer,
        "memory_candidates": memory_candidates,
        "saved_memories": saved,
        "path": str(path),
        "dream_id": dream_id,
        "stats": stats,
        "duration": round(time.time() - t0, 2),
    }


def list_dreams(limit: int = 20) -> list:
    d = _ensure_dir()
    files = sorted(d.glob("dream_*.md"), reverse=True)[:limit]
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        out.append({
            "id": f.stem,
            "path": str(f),
            "title": title,
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        })
    return out


def read_dream(dream_id: str) -> str:
    p = _ensure_dir() / f"{dream_id}.md"
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def dream_stats() -> str:
    dreams = list_dreams(limit=1000)
    if not dreams:
        return "还没有做过梦。"
    total = sum(d["size"] for d in dreams)
    last = dreams[0] if dreams else None
    lines = [
        f"共 {len(dreams)} 个梦境记录",
        f"总大小: {total // 1024} KB",
    ]
    if last:
        ts = time.strftime("%Y-%m-%d %H:%M:%S",
                           time.localtime(last["mtime"]))
        lines.append(f"最近: {ts}")
    lines.append(f"位置: {DREAM_DIR}")
    return "\n".join(lines)