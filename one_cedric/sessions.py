"""M0：多会话注册表（session_id -> copilot + 会话级锁）。

在此之前网关只有单个 ``gw.copilot`` 和一把全局 ``_chat_lock``：
"同时只有一条流、只有一个对话"。四个界面（现有 WebUI / Codex WebUI /
TUI / 桌面）要并存，就必须让"会话"成为一等对象：

    session_id -> SessionEntry(copilot, lock)

约定：

* **同一会话仍然串行**——messages / undo_stack 必须顺序，抢不到锁就拒答；
* **不同会话各跑各的**——A 会话在流式输出时，B 会话照样能发消息；
* 事件通道本来就是实例属性（``OneCedric._stream_hook``），所以"一会话一
  实例"自动解决了两端同开互相截流的问题，不需要额外的事件总线。

默认会话（``registry.default``）仍然是进程启动时那个实例，保证 CLI 与
旧客户端（不带 session_id）的行为一字不变。
"""
from __future__ import annotations

import threading
import time

from .storage import (
    delete_session_file, list_session_files, load_session_file,
)


class SessionEntry:
    """一个会话 = 一个 OneCedric 实例 + 一把非阻塞锁。"""

    __slots__ = ("session_id", "copilot", "lock", "created_at")

    def __init__(self, session_id: str, copilot):
        self.session_id = session_id
        self.copilot = copilot
        self.lock = threading.Lock()
        self.created_at = time.time()

    @property
    def busy(self) -> bool:
        return self.lock.locked()

    def try_acquire(self) -> bool:
        return self.lock.acquire(blocking=False)

    def release(self) -> None:
        try:
            self.lock.release()
        except RuntimeError:
            pass

    def snapshot(self) -> dict:
        c = self.copilot
        return {
            "id": self.session_id or getattr(c, "session_id", ""),
            "title": getattr(c, "session_title", "") or "",
            "model": getattr(c, "model", ""),
            "messages": max(len(getattr(c, "messages", [])) - 1, 0),
            "updated_at": getattr(c, "session_updated_at", 0.0),
            "busy": self.busy,
            "root": str(getattr(c, "root", "")),
        }


class SessionRegistry:
    """网关进程内的会话表。``template`` 是用来 fork 配置的样板实例。"""

    def __init__(self, template):
        self._template = template
        self._entries: dict[str, SessionEntry] = {}
        self._guard = threading.Lock()
        self.default = SessionEntry(
            getattr(template, "session_id", "") or "", template)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get(self, session_id: str) -> SessionEntry | None:
        sid = (session_id or "").strip()
        if not sid:
            return self.default
        if sid == self.default.session_id:
            return self.default
        with self._guard:
            return self._entries.get(sid)

    def entry(self, session_id: str) -> SessionEntry:
        """取会话，没有就从磁盘装载（或按给定 id 新建），绝不返回 None。"""
        sid = (session_id or "").strip()
        if not sid:
            return self.default
        found = self.get(sid)
        if found is not None:
            return found

        data = None
        try:
            data = load_session_file(sid)
        except Exception:
            data = None

        with self._guard:
            # 双检：另一个协程/线程可能刚好装载完
            again = self._entries.get(sid)
            if again is not None:
                return again
            if data is None:
                # 客户端自带 id 的全新会话（还没落盘，首次落盘在回合结束时）
                copilot = self._template.fork(session_id=sid)
            else:
                copilot = self._template.fork()
                copilot._apply_session_data(data)
            entry = SessionEntry(copilot.session_id or sid, copilot)
            self._entries[entry.session_id] = entry
            return entry

    def ids(self) -> list[str]:
        with self._guard:
            return list(self._entries)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def new(self, title: str = "") -> SessionEntry:
        """新开一个空会话（fork 配置，全新状态）。"""
        copilot = self._template.fork()
        if title:
            copilot.session_title = title
            copilot.title_source = "user"
        entry = SessionEntry(copilot.session_id, copilot)
        with self._guard:
            self._entries[entry.session_id] = entry
        return entry

    def drop(self, session_id: str) -> bool:
        """删除会话：忙（正在流式）时拒绝，默认会话不可删。"""
        sid = (session_id or "").strip()
        if not sid or sid == self.default.session_id:
            return False
        with self._guard:
            entry = self._entries.get(sid)
            if entry is not None and entry.busy:
                return False
            self._entries.pop(sid, None)
        try:
            delete_session_file(sid)
        except Exception:
            return False
        return True

    def stop(self, session_id: str) -> bool:
        """请求中断某会话当前回合（协作式，见 OneCedric.abort）。"""
        entry = self.get(session_id)
        if entry is None:
            return False
        entry.copilot.abort()
        return True

    def list(self) -> list[dict]:
        """会话列表：磁盘上的历史 + 进程内还没落盘的新会话。"""
        out: dict[str, dict] = {}
        try:
            for row in list_session_files(
                    root=getattr(self._template, "root", None)):
                sid = row.get("id") or ""
                if sid:
                    out[sid] = {
                        "id": sid,
                        "title": row.get("title") or "",
                        "model": row.get("model", "?"),
                        "messages": len(row.get("messages", [])),
                        "updated_at": row.get("updated_at", 0.0),
                        "busy": False,
                        "root": row.get("root", ""),
                    }
        except Exception:
            pass
        for sid, entry in list(self._entries.items()):
            live = entry.snapshot()
            row = out.get(sid, {})
            row.update({k: v for k, v in live.items() if v not in ("", 0, 0.0)})
            row["busy"] = entry.busy
            out[sid] = row
        default_id = self.default.session_id
        if default_id:
            cur = out.get(default_id, {})
            cur.update(self.default.snapshot())
            out[default_id] = cur
        return sorted(out.values(),
                      key=lambda r: r.get("updated_at") or 0.0,
                      reverse=True)
