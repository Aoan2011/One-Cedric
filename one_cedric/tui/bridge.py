"""Shell C：内核桥。

TUI 需要「构造一个 OneCedric」「跑一个回合」「中断」「读写会话」四件事。
直接 import core 会把 CLI 的一堆组装逻辑（配置、项目、profile）搬进 TUI，
所以这里留一层薄适配：

* 有 ``bridge`` 注入（CLI/测试）就用注入的；
* 否则退回默认实现 —— 懒 import ``core``，用标准配置构造。
"""
from __future__ import annotations

import threading
from typing import Callable, Iterator


class Engine:
    """包装一个 OneCedric 实例，暴露 TUI 需要的四个动作。"""

    def __init__(self, copilot=None, factory: Callable[[], object] | None = None):
        self._copilot = copilot
        self._factory = factory
        self._lock = threading.Lock()

    # -- 会话 ---------------------------------------------------------- #
    @property
    def copilot(self):
        if self._copilot is None:
            self._copilot = self._make()
        return self._copilot

    def _make(self):
        if self._factory is not None:
            return self._factory()
        from ..core import OneCedric          # 懒 import：TUI 启动不拖 CLI
        return OneCedric()

    def new_session(self) -> None:
        """开新会话：有 fork 就用 fork（M0 的会话隔离），否则清空。"""
        with self._lock:
            cp = self.copilot
            if hasattr(cp, "fork"):
                self._copilot = cp.fork()
            elif hasattr(cp, "messages"):
                cp.messages = [m for m in cp.messages[:1]]

    def load_session(self, session_id: str) -> dict:
        """把历史会话装进内核，返回可渲染的数据。"""
        with self._lock:
            cp = self.copilot
            loader = getattr(cp, "_apply_session_data", None)
            data = {}
            if loader is not None:
                try:
                    from ..storage import load_session_file
                    data = load_session_file(session_id) or {}
                    loader(data)
                except Exception as exc:            # 会话文件损坏不该炸 UI
                    data = {"error": str(exc)}
            return data

    # -- 回合 ---------------------------------------------------------- #
    def ask(self, prompt: str, auto_approve: bool = False) -> Iterator[dict]:
        """流式跑一个回合（生成器，在 worker 线程里消费）。"""
        cp = self.copilot
        if hasattr(cp, "ask_no_ui_stream"):
            yield from cp.ask_no_ui_stream(prompt, auto_approve=auto_approve)
        else:                                        # 兜底：非流式
            r = cp.ask_no_ui(prompt, auto_approve=auto_approve)
            yield {"type": "done", "answer": r.get("answer", ""),
                   "duration": 0.0}

    def stop(self) -> None:
        try:
            self.copilot.abort()
        except Exception:
            pass

    # -- 只读信息 ------------------------------------------------------ #
    def info(self) -> dict:
        cp = self.copilot
        out = {}
        for attr in ("model", "host", "session_id", "session_title",
                     "think_level"):
            try:
                out[attr] = getattr(cp, attr)
            except Exception:
                out[attr] = ""
        return out


class FakeEngine(Engine):
    """测试/演示用的假引擎：不需要后端就能跑完整交互。"""

    SCRIPT = [
        ("reasoning", "User said hi; answer directly."),
        ("content", "\u6211\u662f One Cedric\u3002"),
        ("content", "\u8fd9\u662f **TUI** \u7684\u6f14\u793a\u56de\u590d\u3002"),
        ("tool_start", "read_file", "one_cedric/tui/app.py"),
        ("tool_progress", "read_file", "\u8bfb\u53d6\u4e2d\u2026 128 \u884c"),
        ("tool_call", "read_file", "def compose(): ..."),
        ("content", "\u4ee5\u4e0a\u6f14\u793a\u5b8c\u6bd5\u3002"),
    ]

    def __init__(self, delay: float = 0.02):
        super().__init__(copilot=self)
        self.delay = delay
        self.model = "demo-model"
        self.host = "https://demo.invalid"
        self.session_id = "demo"
        self.session_title = "\u6f14\u793a\u4f1a\u8bdd"

    def fork(self, session_id: str = ""):
        return self

    def abort(self) -> None:
        pass

    def _apply_session_data(self, data: dict) -> None:
        pass

    def ask_no_ui_stream(self, prompt: str, auto_approve: bool = False):
        import time
        for kind, *rest in self.SCRIPT:
            time.sleep(self.delay)
            if kind == "content":
                for piece in rest[0].split(" "):
                    yield {"type": "content", "text": piece + " "}
                    time.sleep(self.delay / 2)
            elif kind == "reasoning":
                yield {"type": "reasoning", "text": rest[0]}
            elif kind == "tool_start":
                yield {"type": "tool_start", "name": rest[0], "args": rest[1]}
            elif kind == "tool_progress":
                yield {"type": "tool_progress", "name": rest[0],
                       "output": rest[1]}
            elif kind == "tool_call":
                yield {"type": "tool_call", "name": rest[0], "output": rest[1]}
        yield {"type": "usage", "prompt_tokens": 6249,
               "completion_tokens": 120, "total_tokens": 6369}
        yield {"type": "done", "answer": "\u6f14\u793a\u56de\u590d",
               "duration": 0.8}
