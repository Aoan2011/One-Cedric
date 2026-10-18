"""Shell C：会话状态（唯一真相源）。

TUI 里的 widget 只负责画，数据一律从 ``SessionState`` 读 —— 会话、消息、
待答审批、上下文用量、忙碌标记都挂在这里，widget 订阅它的变更信号。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ToolRun:
    """一次工具调用（用于渲染成一张卡片）。"""
    name: str
    args: str = ""
    status: str = "running"          # running | ok | error
    output: str = ""
    detail: str = ""
    started: float = field(default_factory=time.time)
    ended: float | None = None

    @property
    def elapsed(self) -> float:
        return (self.ended or time.time()) - self.started

    @property
    def glyph(self) -> str:
        return {"running": "◐", "ok": "✔", "error": "✘"}.get(self.status, "•")


@dataclass
class ChatMessage:
    role: str                        # user | assistant | system
    text: str = ""
    reasoning: str = ""
    reasoning_ms: float = 0.0        # 推理耗时（毫秒），Thought 折叠行用
    tools: list[ToolRun] = field(default_factory=list)
    meta: str = ""                   # 「Build · deepseek-flash · 3.6s · 8.2 tok/s」
    done: bool = True
    error: str = ""


class SessionState:
    """一个会话的全部可变状态。"""

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.busy = False
        self.streaming: ChatMessage | None = None
        self.tokens = 0
        self.usage: dict = {}
        self.cost = 0.0
        self.model = ""
        self.host = ""
        self.title = ""
        self.mode = "Build"
        #: 思考档位（composer 第二行与设置浮层展示；不改 reset 语义）。
        self.think = "max"
        self.started = time.time()
        self.error = ""

    # -- 查询 ---------------------------------------------------------- #
    @property
    def percent(self) -> float:
        """上下文占用百分比（按 128k 窗口估算，与 WebUI 的估算口径一致）。"""
        window = self.usage.get("window") or 128000
        return min(100.0, (self.tokens / window) * 100.0) if window else 0.0

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def last_assistant(self) -> ChatMessage | None:
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    # -- 变更 ---------------------------------------------------------- #
    def add_user(self, text: str) -> ChatMessage:
        msg = ChatMessage(role="user", text=text, done=True)
        self.messages.append(msg)
        return msg

    def begin_assistant(self) -> ChatMessage:
        self.streaming = ChatMessage(role="assistant", text="", done=False)
        self.messages.append(self.streaming)
        return self.streaming

    def finish_assistant(self, meta: str = "", error: str = "") -> None:
        if self.streaming is None:
            return
        self.streaming.done = True
        self.streaming.meta = meta
        self.streaming.error = error or self.streaming.error
        self.streaming = None

    def reset(self) -> None:
        self.messages.clear()
        self.streaming = None
        self.tokens = 0
        self.usage = {}
        self.cost = 0.0
        self.error = ""
        self.started = time.time()

    def load_from(self, data: dict) -> None:
        """从 /api/sessions/{id}/messages 的返回装载历史。"""
        self.reset()
        self.title = data.get("title") or self.title
        self.model = data.get("model") or self.model
        for raw in data.get("messages") or []:
            role = raw.get("role", "")
            if role == "system":
                continue
            msg = ChatMessage(
                role="assistant" if role == "assistant" else "user",
                text=raw.get("content") or "",
                done=True,
            )
            self.messages.append(msg)

    # -- 会话操作（compact / undo） ------------------------------------- #
    def compact(self, keep_turns: int = 4) -> int:
        """压缩会话：丢弃推理正文，只保留最近 ``keep_turns`` 轮对话。

        返回被丢弃的条数（0 表示没有变化）。token 的估算也随之缩水，
        由下一回合的 usage 回填纠正。
        """
        removed = 0
        for msg in self.messages:
            if msg.reasoning:
                msg.reasoning = ""
        keep = max(keep_turns, 1) * 2          # 每轮 ≈ user + assistant
        if len(self.messages) > keep:
            removed = len(self.messages) - keep
            self.messages = self.messages[-keep:]
        if removed:
            self.tokens = 0
            self.usage = {}
        return removed

    def undo_last_exchange(self) -> bool:
        """撤销最后一轮（连 user 带回复一起移除）。忙碌时禁止。"""
        if self.busy or not self.messages:
            return False
        if self.streaming is not None:         # 理论上 busy 已挡住；双保险
            return False
        while self.messages and self.messages[-1].role != "user":
            self.messages.pop()
        if self.messages:
            self.messages.pop()
            return True
        return True

    # -- 展示辅助 ------------------------------------------------------- #
    @property
    def tokens_short(self) -> str:
        """6369 → '6.4K'；156 → '156'。状态栏用。"""
        if self.tokens >= 1000:
            return f"{self.tokens / 1000:.1f}K"
        return str(self.tokens)
