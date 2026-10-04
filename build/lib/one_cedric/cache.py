"""工具结果缓存：避免重复调用相同的只读工具。"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path


class ToolCache:
    """LRU + TTL 内存缓存。

    用法：
        cache = ToolCache(max_entries=200, ttl=300)
        cache.put(root, "read_file", {"path": "a.py"}, "...")
        result = cache.get(root, "read_file", {"path": "a.py"})
    """

    def __init__(self, max_entries: int = 200, ttl: int = 300):
        self.max_entries = max_entries
        self.ttl = ttl
        self._data: dict = {}
        self._order: list = []
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _key(self, root: Path, name: str, args: dict) -> str:
        payload = {
            "root": str(root),
            "name": name,
            "args": args,
        }
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()

    def get(self, root: Path, name: str, args: dict):
        key = self._key(root, name, args)
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, ts = entry
            if self.ttl > 0 and (time.time() - ts) > self.ttl:
                self._data.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
                self._misses += 1
                return None
            # LRU 更新
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            self._hits += 1
            return value

    def put(self, root: Path, name: str, args: dict, value) -> None:
        key = self._key(root, name, args)
        with self._lock:
            self._data[key] = (value, time.time())
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            # 淘汰
            while len(self._order) > self.max_entries:
                old = self._order.pop(0)
                self._data.pop(old, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._order.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "entries": len(self._data),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "rate": rate,
            }