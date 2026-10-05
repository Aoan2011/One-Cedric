# -*- coding: utf-8 -*-
"""服务端工具链路验证：真实 copilot + 模拟 LLM（先 tool_call 后 content）"""
import sys, json, tempfile, pathlib
sys.path.insert(0, r"F:\one-cedric5")

from one_cedric.core import OneCedric

calls = {"n": 0}

def fake_stream_chat(self, api_messages, **kw):
    """模拟 LLM：第一轮只调工具，收到 tool 结果后第二轮输出回答"""
    has_tool = any(m.get("role") == "tool" for m in api_messages)
    if not has_tool:
        calls["n"] += 1
        if self._stream_hook is not None:
            try: self._stream_hook({"type": "reasoning", "delta": "先看看目录"})
            except Exception: pass
        yield ("final", {
            "content": "", "reasoning": "先看看目录",
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "list_files", "arguments": "{}"},
            }],
        })
    else:
        for piece in ("项目里包含 ", "one_cedric 包、build 目录等。"):
            if self._stream_hook is not None:
                try: self._stream_hook({"type": "content", "delta": piece})
                except Exception: pass
            yield ("content", piece)
        yield ("final", {
            "content": "项目里包含 one_cedric 包、build 目录等。",
            "reasoning": "", "tool_calls": [],
        })

OneCedric._stream_chat = fake_stream_chat

copilot = OneCedric(model="mock-llm", host="http://localhost:11434",
                    root=r"F:\one-cedric5", api_key="",
                    config_path=pathlib.Path(tempfile.mkdtemp()) / "cfg.json",
                    project_config_path=lambda root: None)
copilot.show_reasoning = False

events = list(copilot.ask_no_ui_stream(
    "列出项目里的文件", auto_approve=True))

print("=== ask_no_ui_stream 事件序列 ===")
for evt in events:
    t = evt.get("type")
    if t == "reasoning":
        print(f"  reasoning: {evt.get('delta','')[:30]!r}")
    elif t == "content":
        print(f"  content: {evt.get('delta','')[:40]!r}")
    elif t == "tool_call":
        print(f"  tool_call: {evt.get('name')} -> {evt.get('target','')} [{evt.get('status')}]")
    elif t == "done":
        print(f"  done: answer={evt.get('answer','')[:40]!r} duration={evt.get('duration')}")
    elif t == "error":
        print(f"  ERROR: {evt.get('message')}")

types = [e["type"] for e in events]
print()
print("tool_call 事件数:", types.count("tool_call"), "(expect >=1)")
print("content 事件数:", types.count("content"), "(expect >=1)")
print("done 存在:", "done" in types)
done = [e for e in events if e["type"] == "done"][0]
print("done.answer 非空:", bool(done.get("answer")))
print("done.answer 全文:", done.get("answer", "")[:500])
print()
print("RESULT:", "PASS" if (types.count("tool_call") >= 1 and types.count("content") >= 1 and done.get("answer")) else "FAIL")
