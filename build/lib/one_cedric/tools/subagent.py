"""Sub agent：在主 agent 派生的独立上下文里跑只读探索任务。

设计要点：
- 子 agent 只持有只读工具（不写文件、不发邮件、不改属性）
- 独立 messages，不污染主上下文
- 独立 console，输出捕获后只返回摘要
- 不能再 spawn 子 agent（_depth 防护在 core 层）
- 支持 3 种模式：explore / code / plan
"""
from __future__ import annotations

import io
import json
import time


SUBAGENT_MODES = ("explore", "code", "plan")
DEFAULT_MODE = "explore"
DEFAULT_MAX_STEPS = 6
DEFAULT_TIMEOUT = 300
MAX_MAX_STEPS = 20
MAX_TIMEOUT = 1800


SUBAGENT_SYSTEM = {
    "explore": r"""你是 One Cedric 的探索子 agent。

任务：在独立上下文里快速探索代码库或资料，返回精炼发现。

规则：
1. 优先使用 read_file / glob / grep_regex / list_files 等只读工具。
2. 不要一次读整个文件——先用 grep/glob 定位，再读相关行。
3. 尽量在 5 步内完成探索，超过就返回已有发现。
4. 输出格式：
   ## 发现
   - 关键点 1（文件:行号）
   - 关键点 2
   ## 未确认
   - 需要主 agent 进一步看的
5. 不要复述大段代码，只给关键片段和精确位置。
""",
    "code": r"""你是 One Cedric 的代码分析子 agent。

任务：分析一段代码，找出问题、给出改法建议。

规则：
1. 用 py_outline / py_imports / py_unused_imports / lsp_* 等工具快速理解结构。
2. 用 read_file 读关键部分。
3. 输出格式：
   ## 摘要
   一句话说明这段代码做什么
   ## 问题
   - 问题 1（行号，严重程度）
   ## 建议改法
   给出 diff 或代码片段
4. 不要真的改文件——只给建议。
""",
    "plan": r"""你是 One Cedric 的计划子 agent。

任务：为一个任务制定详细可执行的计划。

规则：
1. 先用只读工具确认现状（文件是否存在、代码结构）。
2. 输出格式必须是 Markdown 有序列表：
   ## 计划
   1. 动作 1（涉及文件）
   2. 动作 2
   ...
3. 每步是原子的、可独立验证的。
4. 不要执行计划，只输出。
""",
}


def _clamp(value, default, lo, hi):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(v, hi))


def _build_tools_for_subagent():
    """构造子 agent 可用的工具列表（全部只读工具，排除 spawn_agent）。"""
    from .schema import TOOLS, READONLY_TOOL_NAMES
    out = []
    for t in TOOLS:
        name = t["function"]["name"]
        if name == "spawn_agent":
            continue
        if name in READONLY_TOOL_NAMES:
            out.append(t)
    return out


def run_subagent(parent, task: str, mode: str = DEFAULT_MODE,
                 max_steps: int = DEFAULT_MAX_STEPS,
                 timeout: int = DEFAULT_TIMEOUT) -> dict:
    """在独立上下文里跑一次 sub agent。

    parent 需要提供：
      - model / host / api_key / root
      - _stream_chat(messages, tools_override=None)
      - tool_cache

    返回：
      {
        "ok": bool,
        "answer": str,
        "tool_calls": [{"name","target","status","summary"}, ...],
        "steps": int,
        "duration": float,
        "error": str,
        "log": str,
      }
    """
    from rich.console import Console as _Console
    from . import dispatch_tool
    from .schema import CACHEABLE_TOOLS

    mode = (mode or DEFAULT_MODE).lower()
    if mode not in SUBAGENT_MODES:
        mode = DEFAULT_MODE

    max_steps = _clamp(max_steps, DEFAULT_MAX_STEPS, 1, MAX_MAX_STEPS)
    timeout = _clamp(timeout, DEFAULT_TIMEOUT, 10, MAX_TIMEOUT)

    tools_list = _build_tools_for_subagent()
    if not tools_list:
        return {
            "ok": False, "answer": "", "tool_calls": [], "steps": 0,
            "duration": 0.0, "error": "没有可用的只读工具", "log": "",
        }

    sys_prompt = SUBAGENT_SYSTEM[mode]
    msgs: list[dict] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": task},
    ]

    buf = io.StringIO()
    sub_console = _Console(file=buf, width=110, no_color=True,
                           force_terminal=False, soft_wrap=True)

    # 临时屏蔽父的 stream hook
    old_hook = getattr(parent, "_stream_hook", None)
    try:
        parent._stream_hook = None
    except Exception:
        pass

    t0 = time.time()
    tool_log: list[dict] = []
    final_text = ""
    error = ""
    steps_used = 0

    try:
        for step in range(max_steps):
            steps_used = step + 1

            if time.time() - t0 > timeout:
                error = f"超时（>{timeout}s）"
                break

            final_content = ""
            tool_calls: list = []

            try:
                for kind, data in parent._stream_chat(msgs, tools_override=tools_list):
                    if kind == "final":
                        final_content = data.get("content", "")
                        tool_calls = data.get("tool_calls") or []
            except SystemExit as exc:
                error = str(exc)
                break
            except Exception as exc:
                error = f"API 错误: {type(exc).__name__}: {exc}"
                break

            asst: dict = {"role": "assistant", "content": final_content}
            if tool_calls:
                normalized = []
                for i, tc in enumerate(tool_calls):
                    normalized.append({
                        "id": tc.get("id") or f"call_{step}_{i}",
                        "type": "function",
                        "function": {
                            "name": (tc.get("function") or {}).get("name", ""),
                            "arguments": (tc.get("function") or {}).get("arguments") or "{}",
                        },
                    })
                asst["tool_calls"] = normalized
            msgs.append(asst)

            if not tool_calls:
                final_text = final_content or "(子 agent 无输出)"
                break

            for tc in asst["tool_calls"]:
                name = tc["function"]["name"]
                if not name:
                    msgs.append({
                        "role": "tool", "tool_call_id": tc["id"],
                        "content": "ERROR: 工具名为空",
                    })
                    continue

                raw_args = tc["function"]["arguments"]
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}

                target = ""
                for k in ("path", "file", "query", "url", "pattern",
                          "location", "address", "keywords", "name", "uid"):
                    if k in args and args[k] not in ("", None):
                        target = str(args[k])[:50]
                        break

                # 缓存
                cached = None
                if name in CACHEABLE_TOOLS:
                    try:
                        cached = parent.tool_cache.get(parent.root, name, args)
                    except Exception:
                        cached = None

                if cached is not None:
                    result = cached
                else:
                    try:
                        result = dispatch_tool(name, args, parent.root)
                    except Exception as exc:
                        result = f"ERROR: {type(exc).__name__}: {exc}"
                    if name in CACHEABLE_TOOLS and not result.startswith("ERROR"):
                        try:
                            parent.tool_cache.put(parent.root, name, args, result)
                        except Exception:
                            pass

                first_line = result.splitlines()[0] if result else ""
                tool_log.append({
                    "name": name,
                    "target": target,
                    "status": "error" if result.startswith("ERROR") else "ok",
                    "summary": first_line[:80],
                })

                # 工具结果截断，避免子 agent 上下文爆炸
                capped = result if len(result) <= 20_000 else (
                    result[:20_000] + f"\n... (截断，原始 {len(result)} 字符)"
                )
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": capped,
                })
        else:
            # for 循环跑完没 break
            final_text = final_content or f"(达到最大步数 {max_steps})"
            error = "达到最大步数"

    finally:
        try:
            parent._stream_hook = old_hook
        except Exception:
            pass

    duration = round(time.time() - t0, 2)
    ok = (not error) and bool(final_text) and not final_text.startswith("(")

    log_tail = buf.getvalue()
    if len(log_tail) > 4000:
        log_tail = "…(截断)\n" + log_tail[-4000:]

    return {
        "ok": ok,
        "answer": final_text,
        "tool_calls": tool_log,
        "steps": steps_used,
        "duration": duration,
        "error": error,
        "log": log_tail,
    }