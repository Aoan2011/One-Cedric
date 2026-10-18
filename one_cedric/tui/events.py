"""Shell C：后台 agent 工程。

Textual 的 UI 线程不能被网络/工具阻塞，所以：

* ``Engine`` 持有一个 ``OneCedric``（由 ``bridge`` 负责构造，避免 TUI 反向
  依赖 CLI 的组装逻辑），用 ``run_worker(thread=True)`` 跑；
* 事件从 ``core`` 的流式生成器冒出来，经 ``post_message`` 回 UI 线程；
* ``stop()`` 调 ``copilot.abort()``，内核在下一个检查点协作退出（M0 已铺好）。
"""
from __future__ import annotations

from textual.message import Message


class Chunk(Message):
    """助手正文增量。"""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class Reasoning(Message):
    """推理过程增量。"""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ToolStart(Message):
    def __init__(self, name: str, args: str = "") -> None:
        self.name = name
        self.args = args
        super().__init__()


class ToolEnd(Message):
    def __init__(self, name: str, status: str = "ok", output: str = "") -> None:
        self.name = name
        self.status = status
        self.output = output
        super().__init__()


class Usage(Message):
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        super().__init__()


class Finished(Message):
    """一个回合结束（成功、出错或被中断）。"""

    def __init__(self, kind: str, answer: str = "", duration: float = 0.0,
                 message: str = "") -> None:
        self.kind = kind
        self.answer = answer
        self.duration = duration
        self.message = message
        super().__init__()


class KernelOutput(Message):
    """一条内核 slash 命令在捕获 Console 里跑完，输出文本上屏。"""

    def __init__(self, label: str, text: str) -> None:
        self.label = label
        self.text = text
        super().__init__()


def map_event(evt: dict) -> Message | None:
    """把内核流式事件映射成 Textual 消息。"""
    kind = evt.get("type")
    if kind == "content":
        return Chunk(evt.get("text") or "")
    if kind == "reasoning":
        return Reasoning(evt.get("text") or "")
    if kind == "tool_start":
        return ToolStart(evt.get("name") or "?", evt.get("args") or "")
    if kind in ("tool_call", "tool_progress", "tool_result", "tool_end"):
        return ToolEnd(
            evt.get("name") or "?",
            evt.get("status") or ("ok" if kind != "tool_progress" else "running"),
            evt.get("output") or evt.get("summary") or "",
        )
    if kind == "usage":
        return Usage(evt)
    if kind in ("done", "aborted", "error"):
        return Finished(kind, evt.get("answer") or "",
                        float(evt.get("duration") or 0.0),
                        evt.get("message") or "")
    return None
