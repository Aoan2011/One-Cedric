"""OneCedric 主体：Agent 循环 + 工具 handler + REPL。"""
from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cache import ToolCache
from .config import (
    BRAND, ACCENT, USER_C, TOOL_C, WARN_C, PLAN_C, OK_C, ERR_C, DIM_C, THEME,
    SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT, COMPACT_PROMPT, TITLE_PROMPT,
    MAX_WRITE_BYTES, SHELL_OUTPUT_LIMIT, DEFAULT_SHELL_TIMEOUT,
    REASONING_MODEL_KEYWORDS, DEEPSEEK_BUGGY_MODEL_KEYWORDS,
    THINK_LEVELS, THINK_LEVEL_DESC, THINK_TO_REASONING_EFFORT,
    THINK_TO_BUDGET, THINK_PROMPT_HINTS, DEFAULT_THINK_LEVEL,
    SHELL_WHITELIST,
    ACCESS_MODES, ACCESS_MODE_ALIASES, ACCESS_MODE_DESC,
    DEFAULT_ACCESS_MODE,
)
from .git_snap import _git_available, git_make_snapshot, git_rollback
from .storage import (
    save_session_file, load_session_file, list_session_files,
    delete_session_file, find_session_by_id_or_title,
    default_config_path, project_config_path, _fresh_config,
    _read_config_file, save_config_file,
    save_profile, load_profile, profile_path, list_profiles,
    delete_profile, PROFILE_NAME_RE, profile_preset_tag,
    _new_session_id,
    load_tools_config, save_tools_config, tools_config_path,
)
from .tools import (
    dispatch_tool, prepare_tool_call,
    TOOLS as _ALL_TOOLS, TOOLS_READONLY, WRITE_TOOLS, CACHEABLE_TOOLS,
    _resolve_path, _as_int,
)
from . import ui


# ═══════════════════════════════════════════════════════════════════════ #
# 外部编辑器
# ═══════════════════════════════════════════════════════════════════════ #

def _default_editor() -> str:
    for key in ("EDITOR", "VISUAL"):
        v = os.environ.get(key)
        if v and v.strip():
            return v.strip()
    return "notepad" if os.name == "nt" else "nano"


def _open_in_editor(initial_text: str, suffix: str) -> str | None:
    editor_cmd = _default_editor()
    try:
        editor_argv = shlex.split(editor_cmd)
    except ValueError:
        return None
    if not editor_argv:
        return None
    suffix = suffix if suffix.startswith(".") else (f".{suffix}" if suffix else ".txt")
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="one-cedric-edit-", suffix=suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(initial_text)
        try:
            ret = subprocess.run(editor_argv + [tmp_path]).returncode
        except FileNotFoundError:
            return None
        if ret != 0:
            return None
        with open(tmp_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════ #
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════ #

def _estimate_tokens(messages: list) -> int:
    total = 0
    for m in messages:
        total += len(m.get("content") or "")
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            total += len(fn.get("arguments") or "")
    return int(total / 2.5)


def _find_split_index(messages: list, keep_turns: int) -> int | None:
    user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idx) <= keep_turns:
        return None
    split = user_idx[-keep_turns]
    if split <= 1:
        return None
    return split


def parse_plan_items(text: str) -> list[str]:
    items: list[str] = []
    pat = re.compile(r"^\s*(?:\d+\.|[-*+])\s+(.+?)\s*$")
    for line in (text or "").splitlines():
        m = pat.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        if not item or len(item) > 200:
            continue
        items.append(item)
    seen = set()
    out = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _scan_text_tool_calls(text: str) -> list[dict]:
    results: list[dict] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            c = text[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        if depth != 0 or j >= n:
            i += 1
            continue
        snippet = text[i:j + 1]
        try:
            obj = json.loads(snippet)
        except json.JSONDecodeError:
            i += 1
            continue
        if not isinstance(obj, dict):
            i += 1
            continue
        name = obj.get("name")
        args = obj.get("arguments")
        if isinstance(name, str) and name and isinstance(args, dict):
            results.append({
                "id": f"recover_{len(results)}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })
        i = j + 1
    return results


def _strip_text_tool_calls(text: str) -> str:
    out_parts: list[str] = []
    i = 0
    n = len(text)
    last = 0
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            c = text[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        if depth != 0 or j >= n:
            i += 1
            continue
        snippet = text[i:j + 1]
        try:
            obj = json.loads(snippet)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
            out_parts.append(text[last:i])
            last = j + 1
        i = j + 1
    out_parts.append(text[last:])
    cleaned = "".join(out_parts)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _extract_cached_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    ptd = usage.get("prompt_tokens_details") or {}
    if isinstance(ptd, dict) and "cached_tokens" in ptd:
        try:
            return int(ptd["cached_tokens"])
        except (TypeError, ValueError):
            pass
    if "cache_read_input_tokens" in usage:
        try:
            return int(usage["cache_read_input_tokens"])
        except (TypeError, ValueError):
            pass
    if "prompt_cache_hit_tokens" in usage:
        try:
            return int(usage["prompt_cache_hit_tokens"])
        except (TypeError, ValueError):
            pass
    return 0


def _extract_input_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    for k in ("prompt_tokens", "input_tokens"):
        if k in usage:
            try:
                return int(usage[k])
            except (TypeError, ValueError):
                pass
    return 0


def _extract_output_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    for k in ("completion_tokens", "output_tokens"):
        if k in usage:
            try:
                return int(usage[k])
            except (TypeError, ValueError):
                pass
    return 0


def _human_size(n: int) -> str:
    if n <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_speed(bps: float) -> str:
    return _human_size(int(bps)) + "/s"


def _human_eta(sec: float) -> str:
    if sec <= 0:
        return "?"
    if sec < 60:
        return f"{sec:.0f}s"
    if sec < 3600:
        return f"{sec / 60:.1f}m"
    return f"{sec / 3600:.1f}h"


# ═══════════════════════════════════════════════════════════════════════ #
# OneCedric 类
# ═══════════════════════════════════════════════════════════════════════ #

class OneCedric:
    _OFFICE_MODULE = {
        "docx":  ("word",  "docx_apply"),
        "pdf":   ("pdf",   "pdf_apply"),
        "pptx":  ("pptx",  "pptx_apply"),
        "excel": ("excel", "excel_apply"),
    }

    def __init__(self, model: str, host: str, root: Path,
                 max_steps: int = 8, temperature: float = 0.2,
                 auto_yes: bool = False, session_data: dict | None = None,
                 config: dict | None = None,
                 config_path: Path | None = None,
                 project_config_path: Path | None = None,
                 profile_name: str = "",
                 api_key: str = "",
                 show_reasoning: bool = True,
                 enable_computer_use: bool = False,
                 enable_vision: bool = False,
                 think_level: str = DEFAULT_THINK_LEVEL,
                 access_mode: str = DEFAULT_ACCESS_MODE):
        self.console = Console(theme=THEME, highlight=False)
        self.model = model
        self.host = host
        self.root = root
        self.max_steps = max_steps
        self.temperature = temperature
        self.auto_yes = auto_yes
        self.api_key = api_key or ""
        self.show_reasoning = bool(show_reasoning)
        self.enable_vision = bool(enable_vision)
        self.system_msg = {"role": "system", "content": SYSTEM_PROMPT}

        lvl = (think_level or DEFAULT_THINK_LEVEL).lower()
        self.think_level = lvl if lvl in THINK_LEVELS else DEFAULT_THINK_LEVEL

        from .tools.sandbox import set_access_mode
        m = (access_mode or DEFAULT_ACCESS_MODE).lower()
        m = ACCESS_MODE_ALIASES.get(m, m)
        if m not in ACCESS_MODES:
            m = DEFAULT_ACCESS_MODE
        self.access_mode = m
        set_access_mode(m)

        self.git_enabled = _git_available(root)
        self.max_snapshots = 20
        self._snapshot_taken_this_turn = False
        self._save_warned = False

        self.config = config or _fresh_config()
        self.config_path = config_path or default_config_path()
        self.project_config_path = (project_config_path
                                     or project_config_path(root))
        self.tool_cache = ToolCache()

        d_cfg = self.config.get("default", {})
        self.compact_keep_turns = int(d_cfg.get("compact_keep_turns", 4))
        self.auto_compact_threshold = int(
            d_cfg.get("auto_compact_threshold", 0))
        self.compactions: list[dict] = []
        self.snapshot_granularity = str(
            d_cfg.get("snapshot_granularity", "turn"))
        if self.snapshot_granularity not in ("turn", "write"):
            self.snapshot_granularity = "turn"

        self.plan_mode = False
        self.plan_active = False
        self.plan_items: list[str] = []
        self.active_profile = profile_name
        self.preset_tag = ""
        self.session_title = ""
        self.title_source = ""

        try:
            from .computer import SafetyPolicy, set_policy as _set_cp
            self._computer_policy = SafetyPolicy(
                enabled=enable_computer_use)
            _set_cp(self._computer_policy)
        except Exception:
            class _FakePolicy:
                enabled = False
            self._computer_policy = _FakePolicy()

        self.allow_arbitrary_shell = bool(
            d_cfg.get("allow_arbitrary_shell", False)
        )
        self.session_allowed_cmds: set = set()
        self.disabled_tools: set = load_tools_config().get("disabled", set())
        self._current_tool_schemas = _ALL_TOOLS
        self._tool_started_at: dict[str, float] = {}
        self._last_tool_call_id = ""

        self._stream_hook = None
        self._pending_confirm = False
        self._last_usage: dict | None = None
        self._stream_waveform = None
        self._subagent_depth = 0
        self._cron_daemon = None
        self._ask_registry: dict = {}
        self._ask_lock = threading.Lock()
        self._gateway_ref = None

        if session_data:
            self.session_id = session_data["id"]
            self.session_created_at = session_data.get(
                "created_at", time.time())
            self.model = session_data.get("model", model)
            msgs = session_data.get("messages") or [self.system_msg]
            if not msgs or msgs[0].get("role") != "system":
                msgs = [self.system_msg] + msgs
            self.messages = msgs
            self.undo_stack = []
            for rec in session_data.get("undo_stack", []):
                self.undo_stack.append({
                    "path": self.root / rec["rel"], "rel": rec["rel"],
                    "old_text": rec.get("old_text", ""),
                    "new_text": rec.get("new_text", ""),
                    "existed": rec.get("existed", False),
                    "tool": rec.get("tool", ""),
                    "ts": rec.get("ts", 0.0),
                    "tag": rec.get("tag", ""),
                })
            self.snapshots = list(session_data.get("snapshots", []))
            self.compactions = list(session_data.get("compactions", []))
            self.audit_log = list(session_data.get("audit_log", []))
            self.todos = list(session_data.get("todos", []))
            self.session_asks = list(session_data.get("asks", []))
            self.session_title = session_data.get("title", "") or ""
            self.title_source = session_data.get("title_source", "") or ""
            s = session_data.get("stats") or {}
            self.stats = {
                "turns": int(s.get("turns", 0)),
                "tool_calls": dict(s.get("tool_calls", {})),
                "write_ops": int(s.get("write_ops", 0)),
                "bash_ops": int(s.get("bash_ops", 0)),
                "bash_failures": int(s.get("bash_failures", 0)),
                "undo_ops": int(s.get("undo_ops", 0)),
                "rollback_ops": int(s.get("rollback_ops", 0)),
                "turn_durations": list(s.get("turn_durations", [])),
                "started_at": float(s.get("started_at", time.time())),
                "total_input_tokens": int(s.get("total_input_tokens", 0)),
                "total_output_tokens": int(s.get("total_output_tokens", 0)),
                "total_cached_tokens": int(s.get("total_cached_tokens", 0)),
            }
        else:
            self.session_id = _new_session_id()
            self.session_created_at = time.time()
            self.messages = [self.system_msg]
            self.undo_stack = []
            self.snapshots = []
            self.audit_log = []
            self.todos = []
            self.session_asks = []
            self.stats = {
                "turns": 0, "tool_calls": {},
                "write_ops": 0, "bash_ops": 0, "bash_failures": 0,
                "undo_ops": 0, "rollback_ops": 0,
                "turn_durations": [], "started_at": time.time(),
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_cached_tokens": 0,
            }

        self._todo_next_id = max(
            [t.get("id", 0) for t in self.todos] + [0]) + 1
        self.bg_jobs: dict = {}

    # ================================================================== #
    # 通用
    # ================================================================== #

    def _bump(self, key: str, delta: int = 1) -> None:
        if key in self.stats:
            self.stats[key] = int(self.stats.get(key, 0)) + delta

    def _bump_tool(self, name: str) -> None:
        d = self.stats.setdefault("tool_calls", {})
        d[name] = int(d.get(name, 0)) + 1

    def _audit(self, kind: str, verdict: str, summary: str, *,
               command: str = "", path: str = "",
               returncode: int | None = None, duration: float = 0.0,
               timeout: int | None = None, detail: str = "") -> None:
        self.audit_log.append({
            "ts": time.time(), "kind": kind, "verdict": verdict,
            "command": command, "path": path, "returncode": returncode,
            "duration": round(duration, 3), "timeout": timeout,
            "summary": summary[:200], "detail": detail[:500],
        })
        if len(self.audit_log) > 500:
            self.audit_log = self.audit_log[-500:]

    def _save_session(self) -> None:
        asks = self.session_asks[-200:] if len(self.session_asks) > 200 \
            else self.session_asks
        ok = save_session_file(
            self.session_id, self.session_created_at, self.root, self.model,
            self.messages, self.undo_stack, self.snapshots, self.compactions,
            self.stats, self.session_title, self.title_source,
            self.audit_log, self.todos, asks,
        )
        if not ok and not self._save_warned:
            self.console.print(
                "[warn]⚠ 无法写入会话文件，本次会话不会被保存。[/]")
            self._save_warned = True

    def _ensure_snapshot(self) -> None:
        if self.snapshot_granularity != "write":
            if self._snapshot_taken_this_turn:
                return
            self._snapshot_taken_this_turn = True
        if not self.git_enabled:
            return
        snap = git_make_snapshot(self.root)
        if not snap:
            return
        self.snapshots.append(snap)
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)

    def reload_tools_config(self) -> None:
        self.disabled_tools = load_tools_config().get("disabled", set())

    # ================================================================== #
    # UI 转发
    # ================================================================== #

    def banner(self) -> None:
        ui.render_banner(
            self.console,
            model=self.model, host=self.host,
            root=self.root, session_id=self.session_id,
            config_path=self.config_path,
            project_config_path=self.project_config_path,
            plan_mode=self.plan_mode, plan_active=self.plan_active,
            preset_tag=self.preset_tag, active_profile=self.active_profile,
            session_title=self.session_title, title_source=self.title_source,
            show_reasoning=self.show_reasoning,
            think_level=self.think_level,
            access_mode=self.access_mode,
        )

    @staticmethod
    def _shorten(s: str, limit: int = 48) -> str:
        s = s.replace("\n", "\\n")
        return s if len(s) <= limit else s[: limit - 1] + "…"

    def _render_diff(self, rel_path: str, old: str, new: str,
                     is_new: bool, tool: str | None = None) -> None:
        ui.render_diff(self.console, rel_path, old, new,
                       is_new=is_new, tool=tool)

    def _log_tool(self, name: str, target: str, result: str,
                  call_id: str = "") -> None:
        call_id = call_id or self._last_tool_call_id
        started = self._tool_started_at.pop(call_id, None) if call_id else None
        duration = round(time.monotonic() - started, 2) \
            if started is not None else None
        if self._last_tool_call_id == call_id:
            self._last_tool_call_id = ""
        summary, status = ui.summarize_result(name, result)
        try:
            from .integrations import run_hooks
            run_hooks("after_tool", {
                "name": name, "summary": summary, "status": status,
            })
        except RuntimeError as exc:
            self.console.print(f"[err]Hook after_tool 失败: {escape(str(exc))}[/]")
            result += f"\n\nERROR: Hook after_tool 失败: {exc}"
        summary, status = ui.summarize_result(name, result)
        try:
            ui.render_tool_line(self.console, name=name, target=target,
                                summary=summary, status=status,
                                result=result)
        except Exception:
            pass
        result_preview = result if len(result) <= 6000 else (
            result[:6000] + f"\n\n… output truncated ({len(result)} chars total)"
        )
        self._stream_event({
            "type": "tool_call",
            "call_id": call_id,
            "name": name,
            "target": target,
            "summary": summary,
            "status": status,
            "result": result_preview,
            "duration": duration,
        })

    def _stream_event(self, event: dict) -> None:
        if self._stream_hook is None:
            return
        try:
            self._stream_hook(event)
        except Exception:
            pass

    def _stream_tool_start(self, tc: dict, name: str, args: dict) -> None:
        call_id = tc.get("id", "")
        if call_id:
            self._tool_started_at[call_id] = time.monotonic()
            self._last_tool_call_id = call_id
        try:
            from .integrations import run_hooks
            run_hooks("before_tool", {"name": name})
        except RuntimeError as exc:
            if call_id:
                self._tool_started_at.pop(call_id, None)
                if self._last_tool_call_id == call_id:
                    self._last_tool_call_id = ""
            self.console.print(f"[err]Hook before_tool 失败: {escape(str(exc))}[/]")
            self._stream_event({
                "type": "error",
                "message": f"Hook before_tool 失败: {exc}",
            })
            raise
        if self._stream_hook is None:
            return
        self._stream_event({
            "type": "tool_start",
            "call_id": call_id,
            "name": name,
            "target": ui.format_tool_call(name, args, self._shorten),
            "status": "running",
        })

    # ================================================================== #
    # API 通信
    # ================================================================== #

    def _is_deepseek_buggy_model(self) -> bool:
        m = self.model.lower()
        return any(k in m for k in DEEPSEEK_BUGGY_MODEL_KEYWORDS)

    def _chat_url(self) -> str:
        base = self.host.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _auth_headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _think_params(self) -> dict:
        try:
            from .ui.screens.models import get_model_override
            ov = get_model_override(self.model)
        except Exception:
            ov = {}

        out: dict = {}
        for k in ("temperature", "top_p", "max_tokens",
                  "frequency_penalty", "presence_penalty"):
            if k in ov:
                out[k] = ov[k]

        m = self.model.lower()
        tl = ov.get("think_level", self.think_level)
        if any(k in m for k in ("o1", "o3", "o4", "gpt-5")):
            out["reasoning_effort"] = THINK_TO_REASONING_EFFORT.get(
                tl, "medium")
        elif "claude" in m or "anthropic" in m:
            if tl != "minimal":
                out["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": THINK_TO_BUDGET.get(tl, 8192),
                }
        return out

    def _system_with_think(self, base_prompt: str) -> str:
        hint = THINK_PROMPT_HINTS.get(self.think_level, "")
        if not hint:
            return base_prompt
        return base_prompt + hint

    def _stream_chat(self, messages: list,
                     tools_override: list | None = None):
        """流式对话。yield (kind, data)。

        kind: "reasoning" / "content" / "final"
        final data: {content, reasoning, tool_calls}
        """
        url = self._chat_url()

        from .memory import to_prompt_block as _mem_block
        mem_block = ""
        try:
            mem_block = _mem_block()
        except Exception:
            mem_block = ""

        patched_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = self._system_with_think(
                    msg.get("content") or "")
                if mem_block:
                    content = content + "\n\n" + mem_block
                patched_messages.append({
                    "role": "system",
                    "content": content,
                })
            else:
                patched_messages.append(msg)

        if tools_override is not None:
            tools_list = tools_override
        else:
            from .integrations import (
                external_tool_schemas, is_mutating_tool,
            )
            tools_list = list(
                TOOLS_READONLY if self.plan_mode else _ALL_TOOLS
            )
            dynamic_tools = external_tool_schemas()
            if self.plan_mode:
                dynamic_tools = [
                    tool for tool in dynamic_tools
                    if not is_mutating_tool(tool["function"]["name"])
                ]
            tools_list.extend(dynamic_tools)
            if self.disabled_tools:
                tools_list = [
                    t for t in tools_list
                    if t["function"]["name"] not in self.disabled_tools
                ]
        self._current_tool_schemas = tools_list

        try:
            from .ui.screens.models import get_model_override
            ov = get_model_override(self.model)
        except Exception:
            ov = {}

        payload = {
            "model": self.model, "messages": patched_messages,
            "tools": tools_list,
            "tool_choice": "auto", "stream": True,
            "temperature": ov.get("temperature", self.temperature),
            "stream_options": {"include_usage": True},
        }
        payload.update(self._think_params())

        try:
            resp = requests.post(
                url, json=payload, headers=self._auth_headers(),
                timeout=(10, 600), stream=True)
        except requests.exceptions.ConnectionError:
            raise SystemExit(f"无法连接到 API（{url}）。请确认服务可用。")
        except requests.exceptions.Timeout:
            raise SystemExit("请求 API 超时。")
        if resp.status_code >= 400:
            body = resp.text[:500]
            hint = ""
            if resp.status_code == 401:
                hint = ("\n提示：API Key 无效或未设置。"
                        "用 --api-key 或 ONE_CEDRIC_API_KEY 环境变量。")
            elif resp.status_code == 404:
                hint = f"\n提示：模型 '{self.model}' 不存在或 API 地址不对。"
            raise SystemExit(
                f"API 返回错误 {resp.status_code}:\n{body}{hint}")

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: dict = {}

        try:
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                usage = chunk.get("usage")
                if usage:
                    self._last_usage = usage

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                reasoning = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                )
                if reasoning:
                    reasoning_parts.append(reasoning)
                    if self._stream_hook is not None:
                        try:
                            self._stream_hook({
                                "type": "reasoning",
                                "delta": reasoning,
                            })
                        except Exception:
                            pass
                    yield ("reasoning", reasoning)

                content = delta.get("content")
                if content:
                    content_parts.append(content)
                    if self._stream_hook is not None:
                        try:
                            self._stream_hook({
                                "type": "content",
                                "delta": content,
                            })
                        except Exception:
                            pass
                    yield ("content", content)

                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    entry = tool_calls.setdefault(idx, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if tc.get("id"):
                        entry["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        entry["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        entry["function"]["arguments"] += fn["arguments"]
        finally:
            resp.close()

        yield ("final", {
            "content": "".join(content_parts),
            "reasoning": "".join(reasoning_parts),
            "tool_calls": [tool_calls[i] for i in sorted(tool_calls)],
        })

    def _once_chat(self, messages: list, temperature: float = 0.2) -> str:
        url = self._chat_url()
        payload = {
            "model": self.model, "messages": messages,
            "stream": False, "temperature": temperature,
        }
        try:
            resp = requests.post(url, json=payload,
                                 headers=self._auth_headers(),
                                 timeout=(10, 300))
        except requests.exceptions.ConnectionError:
            raise SystemExit(f"无法连接到 API（{url}）。")
        except requests.exceptions.Timeout:
            raise SystemExit("请求 API 超时。")
        if resp.status_code >= 400:
            raise SystemExit(
                f"API 返回错误 {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            msg = data["choices"][0]["message"]
            return msg.get("content") or ""
        except (KeyError, IndexError, ValueError):
            return ""

    def _inject_images(self, messages: list) -> list:
        out: list[dict] = []
        for m in messages:
            if (m.get("role") in ("user", "tool")
                    and isinstance(m.get("content"), str)
                    and "__IMAGE__:" in m["content"]):
                parts = re.split(r"__IMAGE__:", m["content"])
                text_part = parts[0].strip()
                images = [p.strip() for p in parts[1:] if p.strip()]

                if self.enable_vision and images:
                    content_blocks = [{"type": "text", "text": text_part}]
                    for b64 in images:
                        content_blocks.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                            },
                        })
                    new_m = dict(m)
                    new_m["content"] = content_blocks
                    out.append(new_m)
                    continue

                new_m = dict(m)
                new_m["content"] = (text_part
                                     + "\n（未开启 vision，图片未传给模型）")
                out.append(new_m)
                continue
            out.append(m)
        return out
    # ================================================================== #
    # 写操作预览
    # ================================================================== #

    def _preview_write(self, name: str, args: dict):
        path = args.get("path", "")
        p, err = _resolve_path(self.root, path)
        if err:
            return None, "", "", False, err
        old_text = ""
        existed = p.exists() and p.is_file()
        if existed:
            try:
                old_text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return None, "", "", False, f"ERROR: 读取失败: {exc}"
        if name == "write_file":
            content = args.get("content", "")
            if not isinstance(content, str):
                return None, "", "", False, "ERROR: content 必须是字符串。"
            if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
                return None, "", "", False, (
                    f"ERROR: 内容超过 {MAX_WRITE_BYTES // 1000}KB 上限。")
            return p, old_text, content, (not existed), ""
        if name == "edit_file":
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")
            if not isinstance(old_string, str) or \
                    not isinstance(new_string, str):
                return None, "", "", False, (
                    "ERROR: old_string/new_string 必须是字符串。")
            if not existed:
                return None, "", "", False, f"ERROR: 文件不存在: {path}"
            from .tools.write import compute_edit
            new_text, _cnt, err2 = compute_edit(
                old_text, old_string, new_string,
                bool(args.get("replace_all", False)))
            if err2:
                return None, "", "", False, err2
            return p, old_text, new_text, False, ""
        return None, "", "", False, f"ERROR: 未知写工具 {name}"

    def _ask_write_action(self, name: str) -> str:
        if name != "python_exec" and self.access_mode in (
                "workspaceyolo", "fullaccess"):
            self.console.print("  [dim]· 当前模式自动确认[/]")
            return "y"
        if name != "python_exec" and self.auto_yes:
            self.console.print("  [dim]· auto-yes，已自动确认[/]")
            return "y"

        try:
            if name == "python_exec":
                if self._stream_hook is not None:
                    answers = self._ask_user_via_gateway(
                        questions=[{
                            "key": "allow",
                            "question": (
                                "允许执行这段 Python 代码吗？它将以当前"
                                "用户权限运行。"
                            ),
                            "options": ["Allow once", "Reject"],
                            "default": "Reject",
                            "allow_custom": False,
                            "show_if": None,
                        }],
                        timeout=300,
                        header="Python execution approval",
                    )
                    return ("y" if answers.get("allow") == "Allow once"
                            else "n")
                from .ui.confirm import confirm_yes_no
                return "y" if confirm_yes_no(
                    self.console,
                    "允许执行这段 Python 代码？它将以当前用户权限运行。",
                    body="执行前请检查上方代码与工作目录。",
                    default_yes=False,
                    show_dog=True,
                ) else "n"
            from .ui.confirm import confirm_5, ConfirmResult
            r = confirm_5(
                self.console,
                title=f"允许执行 {name}？",
                body="",
                allow_always=True,
                allow_edit=True,
                show_dog=True,
            )
            if r in (ConfirmResult.YES, ConfirmResult.ALWAYS):
                return "y"
            if r == ConfirmResult.EDIT:
                return "e"
            return "n"
        except Exception:
            from .ui.confirm import confirm_yes_no
            try:
                if confirm_yes_no(self.console,
                                   f"允许执行 {name}？",
                                   default_yes=False,
                                   show_dog=True):
                    return "y"
                return "n"
            except (EOFError, KeyboardInterrupt):
                return "n"

    def _ask_shell_action(self, command: str, base_cmd: str,
                          level: str, extra_warn: str = "") -> str:
        if self.access_mode == "fullaccess":
            self.console.print("  [dim]· fullaccess，已自动确认[/]")
            return "yes"
        try:
            from .ui.confirm import confirm_5, ConfirmResult
            r = confirm_5(
                self.console,
                title=f"shell · Level {level}",
                body=f"命令: {command[:160]}",
                extra_warn=extra_warn,
                allow_always=True,
                allow_edit=True,
                show_dog=True,
            )
            if r == ConfirmResult.YES:
                return "yes"
            if r == ConfirmResult.ALWAYS:
                return "always"
            if r == ConfirmResult.EDIT:
                return "edit"
            return "no"
        except Exception:
            try:
                ans = self.console.input(
                    "  [warn]允许执行？[/]  [dim]y/N[/] ")
            except (EOFError, KeyboardInterrupt):
                return "no"
            return "yes" if ans.strip().lower() in ("y", "yes") else "no"

    def _execute_write(self, name: str, p: Path, old_text: str,
                       new_text: str, existed: bool) -> str:
        rel = str(p.relative_to(self.root))
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return f"ERROR: 写入失败: {exc}"
        self._push_undo(name, p, old_text, new_text, existed)
        self.tool_cache.clear()
        if name == "write_file":
            verb = "已覆盖" if existed else "已创建"
            return f"{verb} {rel}（{len(new_text.splitlines())} 行）"
        if name == "apply_patch":
            return f"已应用补丁到 {rel}"
        return f"已更新 {rel}"

    def _push_undo(self, name: str, p: Path, old_text: str,
                   new_text: str, existed: bool) -> None:
        self.undo_stack.append({
            "path": p, "rel": str(p.relative_to(self.root)),
            "old_text": old_text, "new_text": new_text,
            "existed": existed, "tool": name, "ts": time.time(), "tag": "",
        })
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    # ================================================================== #
    # 写工具 handler
    # ================================================================== #

    def _handle_write_tool(self, tc: dict) -> None:
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        p, old_text, new_text, is_new, err = self._preview_write(name, args)
        if err:
            target = ui.format_tool_call(name, args, self._shorten)
            self._log_tool(name, target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        rel = str(p.relative_to(self.root))
        manual_edit_count = 0
        while True:
            self._render_diff(rel, old_text, new_text,
                              is_new=is_new, tool=name)
            action = self._ask_write_action(name)
            if action == "n":
                result = ("用户拒绝执行该写操作，未做任何修改。"
                          "请不要重复相同的编辑。")
                self.console.print("  [warn]⊘ 已取消[/]")
                self._audit(name, "rejected", f"{rel}（用户拒绝）", path=rel)
                break
            if action == "e":
                suffix = p.suffix or ".txt"
                self.console.print(
                    "  [dim]在 $EDITOR 中编辑（保存退出即返回）…[/]")
                edited = _open_in_editor(new_text, suffix)
                if edited is None:
                    self.console.print(
                        "  [err]✗ 编辑器打开失败，未做修改。[/]")
                    continue
                if edited == new_text:
                    self.console.print("  [dim]内容未变化。[/]")
                    continue
                new_text = edited
                manual_edit_count += 1
                self.console.print(
                    "  [accent]↺ 已更新内容，重新展示差异[/]")
                continue
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, name, rel):
                result = self._execute_write(
                    name, p, old_text, new_text, existed=not is_new)
            if result.startswith("ERROR"):
                self._audit(name, "error", result.splitlines()[0], path=rel)
            else:
                if manual_edit_count:
                    result += f"（用户在编辑器中手改 {manual_edit_count} 次）"
                self._bump("write_ops")
                self._audit(name, "ok", result.splitlines()[0], path=rel)
            self._log_tool(name, rel, result)
            break
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_apply_patch_tool(self, tc: dict) -> None:
        from .tools.write import _parse_unified_diff, _apply_hunks_to_text
        args = json.loads(tc["function"]["arguments"] or "{}")
        patch_text = args.get("patch", "")
        if not isinstance(patch_text, str) or not patch_text.strip():
            result = "ERROR: patch 不能为空。"
            self._log_tool("apply_patch", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        files, err = _parse_unified_diff(patch_text)
        if err:
            self._log_tool("apply_patch", "", f"ERROR: {err}")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": f"ERROR: {err}"})
            return
        changes = []
        for f in files:
            target_rel = f["new_path"] or f["old_path"]
            p, rerr = _resolve_path(self.root, target_rel)
            if rerr:
                self._log_tool("apply_patch", target_rel, rerr)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": rerr})
                return
            existed = p.exists() and p.is_file()
            old_text = ""
            if existed:
                try:
                    old_text = p.read_text(encoding="utf-8",
                                            errors="replace")
                except OSError as exc:
                    msg = f"ERROR: 读取失败 {target_rel}: {exc}"
                    self._log_tool("apply_patch", target_rel, msg)
                    self.messages.append({"role": "tool",
                                           "tool_call_id": tc["id"],
                                           "content": msg})
                    return
            all_new = all(h["old_start"] == 0 and h["old_count"] == 0
                          for h in f["hunks"])
            if not existed and not all_new:
                msg = f"ERROR: 文件不存在但补丁不是纯新增: {target_rel}"
                self._log_tool("apply_patch", target_rel, msg)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": msg})
                return
            new_text, aerr = _apply_hunks_to_text(old_text, f["hunks"])
            if aerr:
                msg = f"ERROR: {target_rel}: {aerr}"
                self._log_tool("apply_patch", target_rel, msg)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": msg})
                return
            changes.append({
                "p": p, "rel": str(p.relative_to(self.root)),
                "old_text": old_text, "new_text": new_text,
                "is_new": (not existed),
            })
        if not changes:
            result = "ERROR: 补丁没有产生任何变更。"
            self._log_tool("apply_patch", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        for c in changes:
            self._render_diff(c["rel"], c["old_text"], c["new_text"],
                              is_new=c["is_new"], tool="apply_patch")
        action = self._ask_write_action("apply_patch")
        if action == "n":
            result = "用户拒绝执行 apply_patch，未做任何修改。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        if action == "e":
            result = ("用户选择了编辑但 apply_patch 不支持，"
                      "已取消。建议改用 edit_file。")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        applied = []
        for c in changes:
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, "apply_patch", c["rel"]):
                r = self._execute_write(
                    "apply_patch", c["p"], c["old_text"],
                    c["new_text"], existed=not c["is_new"])
            if r.startswith("ERROR"):
                self._log_tool("apply_patch", c["rel"], r)
                self._audit("apply_patch", "error",
                            r.splitlines()[0], path=c["rel"])
                result = (f"应用过程中出错：{r}。"
                          f"已成功：{', '.join(applied) or '无'}。"
                          f"建议用 /rollback 回退。")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._bump("write_ops")
            applied.append(c["rel"])
            self._audit("apply_patch", "ok",
                        r.splitlines()[0], path=c["rel"])
            self._log_tool("apply_patch", c["rel"], r)
        summary = (f"已应用补丁到 {len(applied)} 个文件："
                   + "，".join(applied))
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": summary})

    def _handle_file_ops_tool(self, tc: dict) -> None:
        from .tools.fileops import file_ops, _execute_file_ops
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).strip().lower()
        src = str(args.get("src", "") or "")
        dst = str(args.get("dst", "") or "")
        recursive = bool(args.get("recursive", False))
        overwrite = bool(args.get("overwrite", False))
        target = f"{op}  {src} {dst}".strip()
        preview, is_write, err = file_ops(
            self.root, op, src=src, dst=dst,
            recursive=recursive, overwrite=overwrite)
        if err:
            self._log_tool("file_ops", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            self.console.print(Panel(
                Text(preview, style="bold"),
                title="[bold]文件操作[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("file_ops") != "y":
                result = "用户拒绝执行该文件操作，未做任何修改。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, "file_ops", target):
                result = _execute_file_ops(
                    self.root, op, src=src, dst=dst,
                    recursive=recursive, overwrite=overwrite)
            self.tool_cache.clear()
            self._log_tool("file_ops", target, result)
            if not result.startswith("ERROR"):
                self._bump("write_ops")
                self._audit("file_ops", "ok", result, path=src or dst)
        else:
            result = preview
            self._log_tool("file_ops", target, preview)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_find_replace_tool(self, tc: dict) -> None:
        from .tools.text import find_replace as _find_replace_impl
        args = json.loads(tc["function"]["arguments"] or "{}")
        pattern = str(args.get("pattern", ""))
        replacement = str(args.get("replacement", ""))
        glob_pat = str(args.get("glob", "**/*") or "**/*")
        path = str(args.get("path", ".") or ".")
        use_regex = bool(args.get("use_regex", False))
        case_insensitive = bool(args.get("case_insensitive", False))
        max_files = args.get("max_files")

        changes, err = _find_replace_impl(
            self.root, pattern=pattern, replacement=replacement,
            glob=glob_pat, path=path, use_regex=use_regex,
            case_insensitive=case_insensitive, max_files=max_files,
        )
        if err:
            self._log_tool("find_replace", pattern[:40], err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not changes:
            result = f"未找到匹配 {pattern!r}。"
            self._log_tool("find_replace", pattern[:40], result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        total_matches = sum(c["count"] for c in changes)
        self.console.print(
            f"  [bold {TOOL_C}]⚙ find_replace[/] "
            f"[dim]在 {len(changes)} 个文件中替换 {total_matches} 处[/]"
        )
        for c in changes:
            self._render_diff(c["rel"], c["old_text"], c["new_text"],
                              is_new=False, tool="find_replace")

        action = self._ask_write_action("find_replace")
        if action != "y":
            result = (f"用户拒绝。涉及 {len(changes)} 个文件 "
                      f"{total_matches} 处替换，未做任何修改。")
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        applied = []
        for c in changes:
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, "find_replace", c["rel"]):
                r = self._execute_write(
                    "find_replace", c["path"], c["old_text"],
                    c["new_text"], existed=True)
            if r.startswith("ERROR"):
                self._log_tool("find_replace", c["rel"], r)
                result = (f"部分失败：{r}。"
                          f"已成功：{', '.join(applied) or '无'}。"
                          f"建议用 /rollback 回退。")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._bump("write_ops")
            applied.append(c["rel"])

        summary = (f"已替换 {total_matches} 处，涉及 {len(applied)} 个文件："
                   + "，".join(applied[:5])
                   + ("…" if len(applied) > 5 else ""))
        self._log_tool("find_replace", pattern[:40], summary)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": summary})

    # ================================================================== #
    # Shell / Git / Docker / SQLite / Archive / Clipboard
    # ================================================================== #

    def _handle_shell_tool(self, tc: dict) -> None:
        from .tools.shell import (
            _parse_shell_command, classify_command,
        )
        args = json.loads(tc["function"]["arguments"] or "{}")
        command = str(args.get("command", "")).strip()
        if not command:
            result = "ERROR: 缺少必需参数 command。"
            self._log_tool("bash", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        try:
            timeout = int(args.get("timeout_seconds",
                                    DEFAULT_SHELL_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_SHELL_TIMEOUT
        timeout = max(1, min(timeout, 300))
        target = command[:52]

        level, reason = classify_command(command)

        if level == "blocked":
            msg = f"ERROR: 命令被拒绝（{reason}）。"
            self._log_tool("bash", target, msg)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": msg})
            self._audit("bash", "blocked",
                        f"{command[:40]}（{reason}）", command=command)
            return

        argv, err = _parse_shell_command(command)
        if err:
            self._log_tool("bash", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return

        base_cmd = argv[0].lower()
        for suffix in (".exe", ".cmd", ".bat", ".sh", ".ps1"):
            if base_cmd.endswith(suffix):
                base_cmd = base_cmd[: -len(suffix)]
                break

        need_confirm = False
        extra_warn = ""

        if self.access_mode == "fullaccess":
            self.console.print("  [dim]· fullaccess，直接执行[/]")
        elif level == "whitelist":
            if self.access_mode == "workspacesafe":
                need_confirm = True
            elif self.preset_tag == "SAFE":
                need_confirm = True
        elif level == "known":
            if self.access_mode == "workspaceyolo":
                pass
            elif base_cmd in self.session_allowed_cmds:
                pass
            elif self.auto_yes:
                pass
            else:
                need_confirm = True
        else:  # unknown
            if not self.allow_arbitrary_shell:
                msg = (
                    f"ERROR: 命令 '{base_cmd}' 不在白名单中，"
                    f"且未开启任意命令模式。\n"
                    f"如需使用：\n"
                    f"  1. /mode fullaccess 切到完全访问\n"
                    f"  2. 或在设置中开启 'allow_arbitrary_shell'\n"
                    f"  3. 或临时用 /shell on 开启本会话\n"
                    f"如果只是想读文件/搜索/列目录，"
                    f"请用 read_file / search_in_files / list_files。"
                )
                self._log_tool("bash", target, msg)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": msg})
                self._audit("bash", "blocked",
                            f"{base_cmd}（未开启任意命令）", command=command)
                return
            elif base_cmd in self.session_allowed_cmds:
                pass
            else:
                need_confirm = True
                extra_warn = "⚠ Level 3 - 未知命令，可能危险"

        if need_confirm:
            action = self._ask_shell_action(
                command, base_cmd, level, extra_warn)
            if action == "no":
                result = "用户拒绝执行该命令，未做任何操作。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                self._audit("bash", "rejected", command, command=command)
                return
            if action == "always":
                self.session_allowed_cmds.add(base_cmd)
                self.console.print(
                    f"  [dim]· 本会话内允许 '{base_cmd}'[/]")
            if action == "edit":
                edited = _open_in_editor(command, ".txt")
                if not edited or not edited.strip():
                    result = "用户编辑命令后为空，已取消。"
                    self.messages.append({"role": "tool",
                                           "tool_call_id": tc["id"],
                                           "content": result})
                    return
                command = edited.strip()
                argv, err = _parse_shell_command(command)
                if err:
                    self._log_tool("bash", target, err)
                    self.messages.append({"role": "tool",
                                           "tool_call_id": tc["id"],
                                           "content": err})
                    return
                target = command[:52]
        elif self.auto_yes and level in ("whitelist", "known"):
            self.console.print("  [dim]· auto-yes[/]")

        t_start = time.time()
        with ui.ToolStatus(self.console, "bash", target):
            try:
                proc = subprocess.run(
                    argv, cwd=str(self.root),
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=timeout, shell=False,
                )
            except subprocess.TimeoutExpired:
                duration = time.time() - t_start
                result = f"ERROR: 命令执行超时（{timeout}s）。"
                self._audit("bash", "timeout", command, command=command,
                            duration=duration, timeout=timeout)
                self._log_tool("bash", target, result)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            except FileNotFoundError:
                duration = time.time() - t_start
                result = f"ERROR: 找不到命令 '{argv[0]}'。"
                self._audit("bash", "error", command, command=command,
                            duration=duration, detail="command not found")
                self._log_tool("bash", target, result)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            except OSError as exc:
                duration = time.time() - t_start
                result = f"ERROR: 执行失败: {exc}"
                self._audit("bash", "error", command, command=command,
                            duration=duration, detail=str(exc))
                self._log_tool("bash", target, result)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return

        duration = time.time() - t_start
        stdout = (proc.stdout or "").rstrip()
        stderr = (proc.stderr or "").rstrip()

        def _trunc(s):
            return s if len(s) <= SHELL_OUTPUT_LIMIT else \
                s[:SHELL_OUTPUT_LIMIT] + (
                    f"\n... [输出截断，原始共 {len(s)} 字符]")

        parts = [f"退出码: {proc.returncode}"]
        if stdout:
            parts.append(f"--- stdout ---\n{_trunc(stdout)}")
        if stderr:
            parts.append(f"--- stderr ---\n{_trunc(stderr)}")
        if not stdout and not stderr:
            parts.append("(无输出)")
        result = "\n".join(parts)

        self.tool_cache.clear()
        self._bump("bash_ops")
        if proc.returncode != 0:
            self._bump("bash_failures")
        self._audit("bash", "ok", f"{command} · rc={proc.returncode}",
                    command=command, returncode=proc.returncode,
                    duration=duration, timeout=timeout)
        self._log_tool("bash", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_bash_bg_tool(self, tc: dict) -> None:
        from .tools.shell import _parse_shell_command, _match_allow_prefix
        from .ui.confirm import confirm_yes_no
        args = json.loads(tc["function"]["arguments"] or "{}")
        command = str(args.get("command", "")).strip()
        if not command:
            result = "ERROR: 缺少必需参数 command。"
            self._log_tool("bash_bg", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        log_file = str(args.get("log_file") or "").strip()
        if not log_file:
            log_file = (f".one-cedric-bg-{int(time.time())}-"
                        f"{secrets.token_hex(2)}.log")
        target = command[:52]

        argv, err = _parse_shell_command(command)
        if err:
            self._log_tool("bash_bg", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not _match_allow_prefix(argv):
            first = argv[0]
            msg = f"ERROR: 命令 '{first}' 不在白名单中。"
            self._log_tool("bash_bg", target, msg)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": msg})
            return
        p_log, lerr = _resolve_path(self.root, log_file)
        if lerr:
            self._log_tool("bash_bg", target, lerr)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": lerr})
            return
        try:
            p_log.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            msg = f"ERROR: 无法创建日志目录: {exc}"
            self._log_tool("bash_bg", target, msg)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": msg})
            return
        if self.access_mode != "fullaccess" and not self.auto_yes:
            if not confirm_yes_no(self.console,
                                   "允许后台执行？",
                                   body=f"命令: {command[:120]}",
                                   default_yes=False,
                                   show_dog=True):
                result = "用户拒绝执行该后台命令。"
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
        try:
            log_fp = open(p_log, "w", encoding="utf-8")
        except OSError as exc:
            msg = f"ERROR: 无法打开日志文件: {exc}"
            self._log_tool("bash_bg", target, msg)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": msg})
            return
        try:
            proc = subprocess.Popen(
                argv, cwd=str(self.root),
                stdout=log_fp, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError) as exc:
            log_fp.close()
            msg = f"ERROR: 启动失败: {exc}"
            self._log_tool("bash_bg", target, msg)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": msg})
            return
        log_fp.close()
        self.bg_jobs[proc.pid] = {
            "proc": proc, "log_file": str(p_log.relative_to(self.root)),
            "log_abs": str(p_log), "command": command,
            "started_at": time.time(),
        }
        self.tool_cache.clear()
        rel_log = str(p_log.relative_to(self.root))
        result = (f"已在后台启动。PID={proc.pid}\n"
                  f"命令: {command}\n"
                  f"日志: {rel_log}\n"
                  f"查看: /jobs    终止: /kill {proc.pid}")
        self._log_tool("bash_bg", target, result)
        self._audit("bash_bg", "ok",
                    f"PID={proc.pid} · {command}", command=command)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_git_tool(self, tc: dict) -> None:
        from .tools.dev import git_tool, _run_git, _format_git_result
        args = json.loads(tc["function"]["arguments"] or "{}")
        sub = str(args.get("subcommand", "")).strip()
        extra = args.get("args") or []
        if not isinstance(extra, list):
            extra = [str(extra)]
        extra = [str(a) for a in extra]
        preview, is_write, err = git_tool(self.root, sub, extra)
        cmd_display = f"git {sub} {' '.join(extra)}".strip()
        target = cmd_display[:52]
        if err:
            self._log_tool("git", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            self.console.print(Panel(
                Text(cmd_display, style="bold"),
                title="[bold]git 写操作[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("git") != "y":
                result = "用户拒绝执行该 git 操作，未做任何修改。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._ensure_snapshot()
            t0 = time.time()
            with ui.ToolStatus(self.console, "git", target):
                code, out, errout = _run_git(
                    self.root, [sub] + extra, timeout=60)
            duration = time.time() - t0
            result = _format_git_result(
                self.root, sub, extra, code, out, errout)
            self.tool_cache.clear()
            self._bump("write_ops")
            self._audit("git", "ok" if code == 0 else "error",
                        f"{cmd_display} · rc={code}",
                        command=cmd_display, returncode=code,
                        duration=duration)
        else:
            t0 = time.time()
            with ui.ToolStatus(self.console, "git", target):
                code, out, errout = _run_git(
                    self.root, [sub] + extra, timeout=30)
            duration = time.time() - t0
            result = _format_git_result(
                self.root, sub, extra, code, out, errout)
            self._audit("git", "ok" if code == 0 else "error",
                        f"{sub} · rc={code}",
                        command=f"git {sub}",
                        returncode=code, duration=duration)
        self._log_tool("git", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_docker_tool(self, tc: dict) -> None:
        from .tools.dev import docker_tool, _run_docker
        args = json.loads(tc["function"]["arguments"] or "{}")
        sub = str(args.get("subcommand", "")).strip()
        extra = args.get("args") or []
        if not isinstance(extra, list):
            extra = [str(extra)]
        extra = [str(a) for a in extra]
        preview, is_write, err = docker_tool(sub, extra)
        target = preview[:52] if preview else f"docker {sub}"
        if err:
            self._log_tool("docker", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            self.console.print(Panel(
                Text(preview, style="bold"),
                title="[bold]docker 写操作[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("docker") != "y":
                result = "用户拒绝执行该 docker 操作。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            t0 = time.time()
            with ui.ToolStatus(self.console, "docker", target):
                code, out, errout = _run_docker(sub, extra, timeout=120)
            duration = time.time() - t0
            header = f"{preview}（退出码 {code}）"
            body = (out or "").rstrip()
            if errout.strip():
                body += ("\n--- stderr ---\n" + errout.rstrip()) \
                    if body else errout.rstrip()
            result = f"{header}\n{body or '(无输出)'}"
            self.tool_cache.clear()
            self._audit("docker", "ok" if code == 0 else "error",
                        f"{preview} · rc={code}",
                        command=preview, returncode=code,
                        duration=duration)
        else:
            result = preview
        self._log_tool("docker", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_sqlite_tool(self, tc: dict) -> None:
        from .tools.data import sqlite_query
        args = json.loads(tc["function"]["arguments"] or "{}")
        path = str(args.get("path", ""))
        query = str(args.get("query", ""))
        params = args.get("params")
        allow_write = bool(args.get("allow_write", False))
        max_rows = args.get("max_rows")
        preview = query.strip().splitlines()[0][:60] if query.strip() else ""
        target = f"{path}  {preview}"
        result, is_write, err = sqlite_query(
            self.root, path, query, params=params,
            allow_write=allow_write, max_rows=max_rows)
        if err:
            self._log_tool("sqlite", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            self.console.print(Panel(
                Text(query, style="bold"),
                title="[bold]SQL 写操作[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("sqlite") != "y":
                result = "用户拒绝执行该 SQL 写操作。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._ensure_snapshot()
            p, _ = _resolve_path(self.root, path)
            with ui.ToolStatus(self.console, "sqlite", target):
                try:
                    conn = sqlite3.connect(str(p), timeout=10)
                    try:
                        cur = conn.cursor()
                        cur.execute(query, params or [])
                        conn.commit()
                        result = f"执行完成，影响 {cur.rowcount} 行。"
                    finally:
                        conn.close()
                except sqlite3.Error as exc:
                    result = f"ERROR: SQL 执行失败: {exc}"
            self.tool_cache.clear()
            if not result.startswith("ERROR"):
                self._bump("write_ops")
                self._audit("sqlite", "ok", result, path=path)
        else:
            self.tool_cache.put(self.root, "sqlite", args, result)
        self._log_tool("sqlite", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_archive_tool(self, tc: dict) -> None:
        try:
            from .tools.archive import (
                archive_op_v2, archive_extract_apply,
                archive_create_apply,
            )
        except ImportError:
            from .tools.dev import archive_op, _archive_do
            return self._handle_archive_tool_legacy(tc)
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).strip().lower()
        archive = str(args.get("archive", ""))
        dst = str(args.get("dst", "") or "")
        srcs = args.get("srcs") or []
        compression = str(args.get("compression", "") or "")
        overwrite = bool(args.get("overwrite", False))
        target = f"{op}  {archive}"
        preview, is_write, err = archive_op_v2(
            self.root, op=op, archive=archive, dst=dst,
            srcs=srcs, compression=compression, overwrite=overwrite,
        )
        if err:
            self._log_tool("archive", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not is_write:
            result = preview
            self._log_tool("archive", target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        self.console.print(Panel(
            Text(preview, style="bold"),
            title="[bold]archive 操作[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action("archive") != "y":
            result = "用户拒绝执行该压缩包操作。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        self._ensure_snapshot()
        with ui.ToolStatus(self.console, "archive", target):
            if op == "extract":
                result = archive_extract_apply(
                    archive, dst, self.root, overwrite=overwrite)
            elif op == "create":
                result = archive_create_apply(
                    archive, srcs, self.root, compression=compression)
            else:
                result = f"ERROR: 未知写 op: {op}"
        self.tool_cache.clear()
        if not result.startswith("ERROR"):
            self._bump("write_ops")
            self._audit("archive", "ok", result, path=archive)
        self._log_tool("archive", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_archive_tool_legacy(self, tc: dict) -> None:
        from .tools.dev import archive_op, _archive_do
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).strip().lower()
        archive = str(args.get("archive", ""))
        dst = str(args.get("dst", "") or "")
        srcs = args.get("srcs") or []
        target = f"{op}  {archive}"
        preview, is_write, err = archive_op(
            self.root, op, archive, dst=dst, srcs=srcs)
        if err:
            self._log_tool("archive", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            if self._ask_write_action("archive") != "y":
                result = "用户拒绝。"
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, "archive", target):
                result = _archive_do(self.root, op, archive,
                                      dst=dst, srcs=srcs)
        else:
            result = preview
        self._log_tool("archive", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_clipboard_tool(self, tc: dict) -> None:
        from .tools.system import clipboard_op, _clipboard_write
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).strip().lower()
        text = str(args.get("text", "") or "")
        preview, is_write, err = clipboard_op(op, text)
        if err:
            self._log_tool("clipboard", op, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if is_write:
            self.console.print(Panel(
                Text(f"{preview}\n\n内容预览：\n" + text[:500]
                     + ("\n..." if len(text) > 500 else ""), style="dim"),
                title="[bold]写入剪贴板[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("clipboard") != "y":
                result = "用户拒绝写入剪贴板。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            with ui.ToolStatus(self.console, "clipboard", op):
                result = _clipboard_write(text)
        else:
            result = preview
        self._log_tool("clipboard", op, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_todo_tool(self, tc: dict) -> None:
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).strip().lower()
        tid = args.get("id")
        text = str(args.get("text", "") or "").strip()
        if op == "add":
            if not text:
                result = "ERROR: add 需要 text。"
            else:
                tid_new = self._todo_next_id
                self._todo_next_id += 1
                self.todos.append({
                    "id": tid_new, "text": text, "done": False})
                result = f"已添加 #{tid_new}: {text}"
                self._save_session()
        elif op == "list":
            if not self.todos:
                result = "（暂无任务）"
            else:
                lines = []
                for t in self.todos:
                    mark = "x" if t.get("done") else " "
                    lines.append(f"[{mark}] #{t['id']} {t['text']}")
                done = sum(1 for t in self.todos if t.get("done"))
                result = (f"任务 {done}/{len(self.todos)} 完成：\n"
                          + "\n".join(lines))
        elif op in ("done", "undone"):
            if tid is None:
                result = f"ERROR: {op} 需要 id。"
            else:
                t = next((x for x in self.todos if x["id"] == tid), None)
                if not t:
                    result = f"ERROR: 找不到任务 #{tid}"
                else:
                    t["done"] = (op == "done")
                    result = (f"已标记 #{tid} 为"
                              f"{'完成' if op == 'done' else '未完成'}")
                    self._save_session()
        elif op == "update":
            if tid is None or not text:
                result = "ERROR: update 需要 id 和 text。"
            else:
                t = next((x for x in self.todos if x["id"] == tid), None)
                if not t:
                    result = f"ERROR: 找不到任务 #{tid}"
                else:
                    t["text"] = text
                    result = f"已更新 #{tid}"
                    self._save_session()
        elif op == "remove":
            if tid is None:
                result = "ERROR: remove 需要 id。"
            else:
                before = len(self.todos)
                self.todos = [x for x in self.todos if x["id"] != tid]
                if len(self.todos) == before:
                    result = f"ERROR: 找不到任务 #{tid}"
                else:
                    result = f"已删除 #{tid}"
                    self._save_session()
        elif op == "clear":
            n = len(self.todos)
            self.todos = []
            self._todo_next_id = 1
            result = f"已清空 {n} 个任务"
            self._save_session()
        else:
            result = f"ERROR: 不支持的 op: {op}"
        self._log_tool("todo", op, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})
    # ================================================================== #
    # 办公文档
    # ================================================================== #

    def _handle_office_tool(self, tc: dict) -> None:
        from .tools import OFFICE_READ_OPS, office_dispatch
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).lower()
        target = f"{op}  {args.get('path', '')}".strip()

        read_ops = OFFICE_READ_OPS.get(name, set())
        if op in read_ops:
            with ui.ToolStatus(self.console, name, target):
                result = office_dispatch(name, args, self.root)
            self._bump_tool(name)
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        mod_name, apply_fn = self._OFFICE_MODULE.get(name, ("", ""))
        if not mod_name:
            result = f"ERROR: 未知办公工具: {name}"
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        try:
            mod = __import__(
                f"one_cedric.tools.office.{mod_name}",
                fromlist=[f"{name}_op"])
            op_func = getattr(mod, f"{name}_op")
        except (ImportError, AttributeError) as exc:
            result = f"ERROR: 加载 {name} 模块失败: {exc}"
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        preview_result = op_func(self.root, args)
        if isinstance(preview_result, tuple):
            preview, is_write, err = preview_result
        else:
            result = preview_result
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if err:
            self._log_tool(name, target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not is_write:
            result = preview
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        self.console.print(Panel(
            Text(preview, style="bold"),
            title=f"[bold]{name} · {op}[/]",
            title_align="left", border_style=WARN_C,
            box=box.ROUNDED, padding=(0, 1), expand=False,
        ))
        if self._ask_write_action(name) != "y":
            result = f"用户拒绝执行 {name} 的 {op} 操作。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        self._ensure_snapshot()
        try:
            apply_func = getattr(mod, apply_fn)
        except AttributeError as exc:
            result = f"ERROR: 找不到 apply 函数: {exc}"
            self._log_tool(name, target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, name, target):
            result = apply_func(self.root, args)
        self.tool_cache.clear()
        if not result.startswith("ERROR"):
            self._bump("write_ops")
            self._audit(name, "ok", result.splitlines()[0][:80],
                        path=str(args.get("path", "")))
        else:
            self._audit(name, "error", result.splitlines()[0][:80],
                        path=str(args.get("path", "")))
        self._bump_tool(name)
        self._log_tool(name, target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 系统操作
    # ================================================================== #

    def _handle_sysop_tool(self, tc: dict) -> None:
        from .tools.sysops import (
            sysop_op, sysop_apply, READONLY_OPS as SYSOP_READONLY_OPS,
        )
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).lower()
        target = op

        if op in SYSOP_READONLY_OPS:
            with ui.ToolStatus(self.console, "sysop", target):
                result = sysop_op(self.root, args)
            self._bump_tool("sysop")
            self._log_tool("sysop", target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        preview_result = sysop_op(self.root, args)
        if isinstance(preview_result, tuple):
            preview, is_write, err = preview_result
        else:
            result = preview_result
            self._log_tool("sysop", target, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if err:
            self._log_tool("sysop", target, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not is_write:
            self._log_tool("sysop", target, preview)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": preview})
            return

        self.console.print(Panel(
            Text(preview, style="bold"),
            title=f"[bold]sysop · {op}[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action("sysop") != "y":
            result = f"用户拒绝执行 sysop {op}。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "sysop", target):
            result = sysop_apply(self.root, args)
        if not result.startswith("ERROR"):
            self._audit("sysop", "ok", f"{op} · {result[:60]}")
        else:
            self._audit("sysop", "error", result[:80])
        self._bump_tool("sysop")
        self._log_tool("sysop", target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # Computer Use
    # ================================================================== #

    def _computer_confirm(self, prompt: str, extra: bool = False) -> bool:
        if self.access_mode == "fullaccess":
            self.console.print(
                f"  [dim]· fullaccess，自动确认：{prompt}[/]")
            return True
        if extra:
            self.console.print(
                f"  [bold {WARN_C}]⚠ 高危动作[/] {prompt}")
        else:
            self.console.print(f"  [warn]{prompt}[/]")
        try:
            ans = self.console.input(
                "  [warn]确认执行？[/] [dim]y/N[/] ")
        except (EOFError, KeyboardInterrupt):
            return False
        return ans.strip().lower() in ("y", "yes")

    def _handle_screen_capture(self, tc: dict) -> None:
        from .tools import screen_capture as _cu_screen_capture
        args = json.loads(tc["function"]["arguments"] or "{}")
        region = args.get("region")
        return_base64 = bool(args.get("return_base64",
                                       self.enable_vision))
        save_to = str(args.get("save_to", "") or "")
        max_width = args.get("max_width", 1280)
        if not self._computer_confirm(
            "截屏" + (f"（区域 {region}）" if region else "（全屏）")
            + (f"  → {save_to}" if save_to else "")
        ):
            result = "用户拒绝截屏。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "screen_capture", ""):
            result = _cu_screen_capture(
                self.root, region=region, save_to=save_to,
                return_base64=return_base64,
                max_width=int(max_width),
            )
        self._bump_tool("screen_capture")
        self._log_tool("screen_capture", save_to or "屏幕", result)
        self._audit("computer",
                    "ok" if not result.startswith("ERROR") else "error",
                    result.splitlines()[0][:80] if result else
                    "screen_capture")
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_screen_info(self, tc: dict) -> None:
        from .tools import screen_info as _cu_screen_info
        result = _cu_screen_info(self.root)
        self._bump_tool("screen_info")
        self._log_tool("screen_info", "", result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    @staticmethod
    def _describe_mouse(args: dict) -> str:
        a = str(args.get("action", "")).lower()
        x, y = args.get("x"), args.get("y")
        if a == "move":
            return f"移动 → ({x},{y})"
        if a == "click":
            return (f"单击 ({x},{y})"
                    + (f" x{args.get('clicks')}"
                       if args.get("clicks") else ""))
        if a == "right_click":
            return f"右键 ({x},{y})"
        if a == "double_click":
            return f"双击 ({x},{y})"
        if a == "drag":
            return (f"拖拽 ({args.get('x1')},{args.get('y1')}) → "
                    f"({args.get('x2')},{args.get('y2')})")
        if a == "scroll":
            return f"滚轮 {args.get('amount')} 格 @ ({x},{y})"
        return a

    def _handle_mouse_action(self, tc: dict) -> None:
        from .tools import mouse_action as _cu_mouse_action
        args = json.loads(tc["function"]["arguments"] or "{}")
        action = str(args.get("action", ""))
        chk = self._computer_policy.check("mouse_action", args)
        if hasattr(chk, "ok") and not chk.ok:
            result = f"ERROR: {chk.reason}"
            self.console.print(f"  [err]✗ {escape(chk.reason)}[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        desc = self._describe_mouse(args)
        if not self._computer_confirm(
                f"鼠标：{desc}",
                extra=getattr(chk, "needs_extra_confirm", False)):
            result = "用户拒绝执行鼠标操作。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "mouse_action", desc[:50]):
            result = _cu_mouse_action(
                self.root, action=action,
                x=args.get("x"), y=args.get("y"),
                x1=args.get("x1"), y1=args.get("y1"),
                x2=args.get("x2"), y2=args.get("y2"),
                button=str(args.get("button", "left")),
                clicks=int(args.get("clicks", 1) or 1),
                amount=int(args.get("amount", 0) or 0),
                duration=float(args.get("duration", 0.3) or 0.3),
            )
        self._bump_tool("mouse_action")
        self._log_tool("mouse_action", desc[:50], result)
        self._audit("computer",
                    "ok" if not result.startswith("ERROR") else "error",
                    desc[:80])
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_keyboard_action(self, tc: dict) -> None:
        from .tools import keyboard_action as _cu_keyboard_action
        args = json.loads(tc["function"]["arguments"] or "{}")
        action = str(args.get("action", ""))
        chk = self._computer_policy.check("keyboard_action", args)
        if hasattr(chk, "ok") and not chk.ok:
            result = f"ERROR: {chk.reason}"
            self.console.print(f"  [err]✗ {escape(chk.reason)}[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        if action == "type":
            desc = f"输入文本：{str(args.get('text', ''))[:60]!r}"
        elif action == "press":
            desc = f"按键：{args.get('key')}"
        elif action == "hotkey":
            desc = ("快捷键："
                    + "+".join(str(k) for k in (args.get("keys") or [])))
        else:
            desc = action
        if not self._computer_confirm(
                f"键盘：{desc}",
                extra=getattr(chk, "needs_extra_confirm", False)):
            result = "用户拒绝执行键盘操作。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "keyboard_action", desc[:50]):
            result = _cu_keyboard_action(
                self.root, action=action,
                text=str(args.get("text", "") or ""),
                key=str(args.get("key", "") or ""),
                keys=args.get("keys") or [],
                interval=float(args.get("interval", 0.02) or 0.02),
            )
        self._bump_tool("keyboard_action")
        self._log_tool("keyboard_action", desc[:50], result)
        self._audit("computer",
                    "ok" if not result.startswith("ERROR") else "error",
                    desc[:80])
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_window_action(self, tc: dict) -> None:
        from .tools import window_action as _cu_window_action
        args = json.loads(tc["function"]["arguments"] or "{}")
        action = str(args.get("action", "")).lower()
        title = str(args.get("title", "") or "")
        if action == "list":
            result = _cu_window_action(self.root, action, title="")
            self._bump_tool("window_action")
            self._log_tool("window_action", "list", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        desc = f"窗口：{action} {title!r}"
        if not self._computer_confirm(desc):
            result = "用户拒绝执行窗口操作。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "window_action", desc[:50]):
            result = _cu_window_action(self.root, action, title=title)
        self._bump_tool("window_action")
        self._log_tool("window_action", desc[:50], result)
        self._audit("computer",
                    "ok" if not result.startswith("ERROR") else "error",
                    desc[:80])
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 记忆 / 定时 / 梦境 / 通知 / 应用
    # ================================================================== #

    def _handle_memory_tool(self, tc: dict) -> None:
        from .tools import memory_remember, memory_forget
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        if name == "memory_remember":
            key = str(args.get("key", "")).strip()
            value = str(args.get("value", "")).strip()
            category = args.get("category", "preference")
            tags = args.get("tags") or []
            if not key or not value:
                result = "ERROR: key 和 value 不能为空"
            else:
                self.console.print(Panel(
                    Text(f"记住 [{category}] {key}\n  = {value}",
                         style="bold"),
                    title="[bold]长期记忆[/]", title_align="left",
                    border_style=PLAN_C, box=box.ROUNDED,
                    padding=(0, 1), expand=False,
                ))
                if self._ask_write_action("memory_remember") != "y":
                    result = "用户拒绝保存记忆。"
                    self.console.print("  [warn]⊘ 已取消[/]")
                    self.messages.append({"role": "tool",
                                           "tool_call_id": tc["id"],
                                           "content": result})
                    return
                result = memory_remember(key, value, category, tags)
            self._log_tool(name, key, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        if name == "memory_forget":
            token = str(args.get("token", "")).strip()
            if not token:
                result = "ERROR: 需要 token"
            elif self._ask_write_action("memory_forget") != "y":
                result = "用户拒绝删除。"
                self.console.print("  [warn]⊘ 已取消[/]")
            else:
                result = memory_forget(token)
            self._log_tool(name, token, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

    def _handle_cron_tool(self, tc: dict) -> None:
        from .tools import cron_add, cron_remove, cron_enable
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        if name == "cron_add":
            cname = str(args.get("name", "")).strip()
            schedule = str(args.get("schedule", "")).strip()
            prompt = str(args.get("prompt", "")).strip()
            preview = (f"创建定时任务\n  名称: {cname}\n"
                       f"  cron: {schedule}\n  prompt: {prompt[:120]}")
            self.console.print(Panel(
                Text(preview, style="bold"),
                title="[bold]定时任务[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("cron_add") != "y":
                result = "用户拒绝创建任务。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            result = cron_add(cname, schedule, prompt)
            self._ensure_cron_daemon()
        elif name == "cron_remove":
            token = str(args.get("token", "")).strip()
            if self._ask_write_action("cron_remove") != "y":
                result = "用户拒绝删除。"
            else:
                result = cron_remove(token)
        elif name == "cron_enable":
            token = str(args.get("token", "")).strip()
            enabled = bool(args.get("enabled", True))
            result = cron_enable(token, enabled)
            self._ensure_cron_daemon()
        else:
            result = f"ERROR: 未知工具 {name}"
        self._log_tool(name, "", result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_dream_tool(self, tc: dict) -> None:
        from .tools.dream_tool import dream_run
        args = json.loads(tc["function"]["arguments"] or "{}")
        days = args.get("days", 3)
        focus = str(args.get("focus", ""))
        save_memories = bool(args.get("save_memories", False))
        preview = (f"回顾最近 {days} 天的会话\n"
                   f"focus: {focus or '（无）'}\n"
                   f"自动保存记忆: {'是' if save_memories else '否'}")
        self.console.print(Panel(
            Text(preview, style=""),
            title="[bold]🌙 做梦[/]", title_align="left",
            border_style=PLAN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        with ui.ToolStatus(self.console, "dream_run", f"{days} 天"):
            result = dream_run(days=days, focus=focus,
                                save_memories=save_memories, parent=self)
        self._log_tool("dream_run", f"{days}d", result[:200])
        self._audit("dream",
                    "ok" if not result.startswith("ERROR") else "error",
                    f"{days}d · {focus[:40]}")
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_notify_tool(self, tc: dict) -> None:
        from .tools.notify_tool import (
            send_notification, send_notification_with_actions,
            notify_with_buttons_preview,
        )
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        title = str(args.get("title", "One Cedric"))
        body = str(args.get("body", ""))
        level = args.get("level", "info")
        sound = bool(args.get("sound", True))
        timeout = args.get("timeout", 5)
        if name == "notify_actions":
            actions = args.get("actions") or []
            if not isinstance(actions, list):
                actions = []
            image_path = args.get("image_path", "")
            preview, _, err = notify_with_buttons_preview(
                title, body, actions, image_path)
            if err:
                result = err
            else:
                self.console.print(Panel(
                    Text(preview, style="bold"),
                    title="[bold]通知（含按钮）[/]",
                    title_align="left", border_style=WARN_C,
                    box=box.ROUNDED, padding=(0, 1), expand=False,
                ))
                if self._ask_write_action("notify_actions") != "y":
                    result = "用户拒绝发送。"
                else:
                    result = send_notification_with_actions(
                        title, body, actions, image_path,
                        level=level, sound=sound, timeout=timeout,
                    )
        else:
            result = send_notification(title, body, level=level,
                                        sound=sound, timeout=timeout)
        self._log_tool(name, title, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_pkg_tool(self, tc: dict) -> None:
        from .tools.apps import (
            install_preview, install_apply,
            uninstall_preview, uninstall_apply,
        )
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        package = str(args.get("package", "")).strip()
        source = str(args.get("source", "")).strip()
        if name == "pkg_install":
            preview, is_write, err = install_preview(package, source)
            title = "安装包"
            action = install_apply
        elif name == "pkg_uninstall":
            preview, is_write, err = uninstall_preview(package, source)
            title = "卸载包"
            action = uninstall_apply
        else:
            return
        if err:
            result = err
        else:
            self.console.print(Panel(
                Text(preview, style="bold"),
                title=f"[bold]{title}[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action(name) != "y":
                result = "用户拒绝。"
                self.console.print("  [warn]⊘ 已取消[/]")
            else:
                with ui.ToolStatus(self.console, name, package):
                    result = action(package, source)
        self._log_tool(name, package, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_cost_export(self, tc: dict, args: dict) -> None:
        from . import cost_tracker as _ct
        detail = args.get("detail", "turn")
        period = args.get("period", "all")
        path = str(args.get("path", "") or "")
        if detail not in ("turn", "daily", "model", "session"):
            detail = "turn"
        if period not in ("today", "week", "month", "all"):
            period = "all"
        preview_lines = [
            f"粒度: {detail}", f"时间段: {period}",
            f"输出: {path or '（自动命名）'}",
        ]
        self.console.print(Panel(
            Text("\n".join(preview_lines), style="bold"),
            title="[bold]导出成本 CSV[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action("cost_export") != "y":
            result = "用户拒绝导出。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        with ui.ToolStatus(self.console, "cost_export", detail):
            ok, result_path, rows = _ct.export_csv(
                path=path, period=period, detail=detail)
        if ok:
            result = (f"已导出 {rows} 行到 {result_path}\n"
                      f"detail={detail} · period={period}")
        else:
            result = f"ERROR: {result_path}"
        self._log_tool("cost_export", detail, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})
    # ================================================================== #
    # Sub agent / Multi review / Ask user
    # ================================================================== #

    def _handle_spawn_agent(self, tc: dict, args: dict) -> None:
        from .tools.subagent import (
            run_subagent, SUBAGENT_MODES, DEFAULT_MODE,
            DEFAULT_MAX_STEPS, DEFAULT_TIMEOUT,
        )
        task = str(args.get("task", "")).strip()
        if not task:
            result = "ERROR: 缺少必需参数 task。"
            self._log_tool("spawn_agent", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        if self._subagent_depth > 0:
            result = "ERROR: 子 agent 不能再 spawn 子 agent（防递归）。"
            self._log_tool("spawn_agent", task[:30], result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        mode = str(args.get("mode", DEFAULT_MODE)).lower()
        if mode not in SUBAGENT_MODES:
            mode = DEFAULT_MODE
        max_steps = args.get("max_steps", DEFAULT_MAX_STEPS)
        timeout = args.get("timeout", DEFAULT_TIMEOUT)

        self.console.print(Panel(
            Text(
                f"模式: {mode}\n"
                f"步数上限: {max_steps}  超时: {timeout}s\n\n"
                f"{task[:400]}" + ("…" if len(task) > 400 else ""),
                style="",
            ),
            title="[bold]派生子 agent[/]", title_align="left",
            border_style=PLAN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        self._subagent_depth = 1
        try:
            with ui.ToolStatus(self.console, "spawn_agent",
                                f"{mode} · {task[:40]}"):
                r = run_subagent(self, task=task, mode=mode,
                                  max_steps=max_steps, timeout=timeout)
        except Exception as exc:
            r = {
                "ok": False, "answer": "", "tool_calls": [],
                "steps": 0, "duration": 0.0,
                "error": f"{type(exc).__name__}: {exc}", "log": "",
            }
        finally:
            self._subagent_depth = 0

        if r.get("tool_calls"):
            self.console.print(
                f"  [dim]子 agent 调用了 {len(r['tool_calls'])} 个工具：[/]")
            for t in r["tool_calls"][:12]:
                st = "err" if t["status"] == "error" else "dim"
                tgt = f"  {t['target']}" if t["target"] else ""
                self.console.print(
                    f"    [{st}]· {t['name']}{escape(tgt)}[/]")
            if len(r["tool_calls"]) > 12:
                self.console.print(
                    f"    [dim]… 还有 {len(r['tool_calls']) - 12} 条[/]")

        header = (f"[子 agent · {mode} · {r.get('steps', 0)} 步 · "
                  f"{r.get('duration', 0)}s]")
        if r.get("ok"):
            result = f"{header}\n\n{r.get('answer') or '(无输出)'}"
        else:
            err = r.get("error") or "未知错误"
            partial = r.get("answer") or ""
            result = f"{header}\n错误: {err}"
            if partial:
                result += f"\n\n部分结果:\n{partial}"
        self._log_tool("spawn_agent", f"{mode} · {task[:30]}", result)
        self._audit("spawn_agent",
                    "ok" if r.get("ok") else "error",
                    f"{mode} · {task[:60]}")
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_multi_review(self, tc: dict, args: dict) -> None:
        from .tools.multi_review import multi_review as _mr
        path = str(args.get("path", "")).strip()
        if not path:
            result = "ERROR: 缺少必需参数 path。"
            self._log_tool("multi_review", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        dims = args.get("dimensions") or None
        max_steps = args.get("max_steps", 5)
        timeout = args.get("timeout", 180)
        self.console.print(Panel(
            Text(
                f"文件: {path}\n"
                f"维度: "
                f"{', '.join(dims) if dims else 'security, performance, readability'}\n"
                f"每个 sub-agent: {max_steps} 步 / {timeout}s",
                style="",
            ),
            title="[bold]多 agent 审查[/]", title_align="left",
            border_style=PLAN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        self._subagent_depth = 1
        try:
            with ui.ToolStatus(self.console, "multi_review",
                                f"{path[:40]}"):
                r = _mr(path=path, root=self.root, dimensions=dims,
                        max_steps=max_steps, timeout=timeout, parent=self)
        finally:
            self._subagent_depth = 0
        if not r.get("ok") and not r.get("summary"):
            result = f"ERROR: {r.get('error', '未知错误')}"
        else:
            result = r.get("summary", "")
        self._log_tool("multi_review", path, result[:200])
        self._audit("multi_review",
                    "ok" if r.get("ok") else "error",
                    f"{path} · {r.get('duration', 0)}s")
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _normalize_ask_questions(self, args: dict):
        raw_list = args.get("questions")
        if raw_list:
            if not isinstance(raw_list, list):
                return "questions 必须是数组"
            out = []
            for i, q in enumerate(raw_list):
                if not isinstance(q, dict):
                    return f"questions[{i}] 必须是对象"
                text = str(q.get("question", "")).strip()
                if not text:
                    return f"questions[{i}] 缺少 question"
                key = str(q.get("key") or f"q{i+1}").strip()
                options = q.get("options") or []
                if not isinstance(options, list):
                    options = []
                options = [str(o).strip() for o in options
                           if str(o).strip()]
                show_if = q.get("show_if")
                if not (isinstance(show_if, dict) and show_if.get("key")):
                    show_if = None
                out.append({
                    "key": key, "question": text, "options": options,
                    "default": str(q.get("default") or ""),
                    "allow_custom": bool(q.get("allow_custom", True)),
                    "show_if": show_if,
                })
            if not out:
                return "questions 不能为空"
            if len(out) > 10:
                return "单次最多问 10 个问题"

            def _collect_refs(si, acc):
                if not isinstance(si, dict):
                    return
                if "key" in si:
                    acc.add(si["key"])
                for sub_key in ("all", "any"):
                    for x in (si.get(sub_key) or []):
                        _collect_refs(x, acc)

            keys = {q["key"] for q in out}
            for q in out:
                si = q.get("show_if")
                if not si:
                    continue
                refs: set = set()
                _collect_refs(si, refs)
                for ref in refs:
                    if ref not in keys:
                        return (f"questions[{q['key']}] 的 show_if 引用了"
                                f"不存在的 key '{ref}'")
            return out

        q = str(args.get("question", "")).strip()
        if not q:
            return "缺少 question 或 questions"
        options = args.get("options") or []
        if not isinstance(options, list):
            options = []
        options = [str(o).strip() for o in options if str(o).strip()]
        return [{
            "key": "answer", "question": q, "options": options,
            "default": str(args.get("default") or ""),
            "allow_custom": bool(args.get("allow_custom", True)),
            "show_if": None,
        }]

    @staticmethod
    def _eval_show_if(show_if, answers: dict) -> bool:
        if not show_if or not isinstance(show_if, dict):
            return True
        if "all" in show_if:
            items = show_if.get("all") or []
            return all(OneCedric._eval_show_if(x, answers)
                       for x in items)
        if "any" in show_if:
            items = show_if.get("any") or []
            if not items:
                return True
            return any(OneCedric._eval_show_if(x, answers)
                       for x in items)
        dep = show_if.get("key", "")
        if not dep:
            return True
        if dep not in answers:
            return False
        val = str(answers.get(dep, ""))
        if "equals" in show_if:
            return val == str(show_if["equals"])
        if "not_equals" in show_if:
            return val != str(show_if["not_equals"])
        if "in" in show_if:
            allowed = [str(x) for x in (show_if.get("in") or [])]
            return val in allowed
        return True

    def _handle_ask_user(self, tc: dict, args: dict) -> None:
        questions = self._normalize_ask_questions(args)
        if isinstance(questions, str):
            result = f"ERROR: {questions}"
            self._log_tool("ask_user", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        header = str(args.get("header", "") or "")
        try:
            timeout = int(args.get("timeout", 300))
        except (TypeError, ValueError):
            timeout = 300
        timeout = max(0, min(timeout, 3600))
        is_batch = len(questions) > 1

        if self._stream_hook is not None:
            answers = self._ask_user_via_gateway(
                questions=questions, timeout=timeout, header=header)
        else:
            answers = self._ask_user_interactive(
                questions=questions, timeout=timeout, header=header)

        lines = ["[用户回答]"]
        for q in questions:
            key = q["key"]
            ans = answers.get(key, "")
            if not ans:
                ans = q.get("default") or "（用户未回答）"
            lines.append(f"{key}: {ans}")
        lines.append("")
        lines.append("请基于这些回答继续任务。不要重复问同一个问题。")
        result = "\n".join(lines)

        import secrets as _secrets
        ask_id = f"ask_{int(time.time())}_{_secrets.token_hex(3)}"
        cur_turn = int(self.stats.get("turns", 0)) + 1
        prev = self.session_asks[-1] if self.session_asks else None
        if prev and prev.get("turn") == cur_turn:
            thread = prev.get("thread") or prev.get("id") or ask_id
            parent_id = prev.get("id")
        else:
            thread = ask_id
            parent_id = None
        self.session_asks.append({
            "id": ask_id, "ts": time.time(), "turn": cur_turn,
            "thread": thread, "parent_id": parent_id,
            "header": header, "timeout": timeout,
            "questions": [
                {"key": q["key"], "question": q["question"],
                 "options": q.get("options", []),
                 "default": q.get("default", ""),
                 "show_if": q.get("show_if"),
                 "answer": answers.get(q["key"], "")}
                for q in questions
            ],
        })
        self._save_session()

        if not is_batch and self._stream_hook is None:
            short = answers.get(questions[0]["key"], "")
            self._log_tool("ask_user", questions[0]["question"][:40],
                           f"用户回答: {short[:80]}")
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _ask_user_interactive(self, questions: list, timeout: int,
                               header: str) -> dict:
        title = header or "模型提问"
        answers: dict = {}
        total = len(questions)
        for i, q in enumerate(questions, 1):
            si = q.get("show_if")
            if si and not self._eval_show_if(si, answers):
                answers[q["key"]] = q.get("default") or ""
                continue
            opts = q["options"]
            default = q["default"]
            allow_custom = q["allow_custom"]
            prefix = f" ({i}/{total})" if total > 1 else ""
            answer = self._ask_one_question(
                opts, default, allow_custom,
                question=q["question"],
                title=f"{title}{prefix}",
            )
            answers[q["key"]] = answer
            self.console.print(
                f"  [dim]· {q['key']} = {escape(answer[:80])}[/]")
        return answers

    def _ask_one_question(self, options: list, default: str,
                           allow_custom: bool, question: str = "",
                           title: str = "模型提问") -> str:
        if not options:
            self.console.print(Panel(
                Text(question),
                title=f"[bold {PLAN_C}]{escape(title)}[/]",
                title_align="left", border_style=PLAN_C,
                box=box.ROUNDED, padding=(0, 1), expand=False,
            ))
            try:
                raw = self.console.input("  [dim]>[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("  [warn]⊘ 用户取消[/]")
                return default or "（用户取消了提问）"
            return raw or (default or "")
        from .ui.confirm import confirm_choice

        choices = [
            (f"option-{index}", option, "")
            for index, option in enumerate(options)
        ]
        default_key = next(
            (f"option-{index}" for index, option in enumerate(options)
             if option == default),
            "",
        )
        if allow_custom:
            choices.append(("custom", "自定义输入", "输入一段自由文本"))
        selected = confirm_choice(
            self.console, title, choices,
            body=question, default=default_key, show_dog=True,
        )
        if selected == "custom":
            try:
                raw = self.console.input("  [dim]自定义回答 >[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                return default or "（用户取消）"
            return raw or (default or "")
        if selected.startswith("option-"):
            try:
                return options[int(selected.removeprefix("option-"))]
            except (ValueError, IndexError):
                return default or ""
        return default or ""

    def _ask_user_via_gateway(self, questions: list, timeout: int,
                               header: str) -> dict:
        import secrets as _secrets
        ask_id = f"ask_{int(time.time())}_{_secrets.token_hex(3)}"
        evt = threading.Event()
        holder = {"answers": None, "event": evt}
        with self._ask_lock:
            self._ask_registry[ask_id] = holder
        gw = getattr(self, "_gateway_ref", None)
        if gw is not None:
            try:
                gw.register_ask(ask_id, {
                    "header": header, "timeout": timeout,
                    "questions": questions,
                })
            except Exception:
                pass
        try:
            self._stream_hook({
                "type": "ask_user", "id": ask_id,
                "questions": questions,
                "timeout": timeout, "header": header,
            })
        except Exception:
            pass
        answered = evt.wait(None if timeout <= 0 else timeout)
        with self._ask_lock:
            self._ask_registry.pop(ask_id, None)
        if gw is not None:
            try:
                gw.unregister_ask(ask_id)
            except Exception:
                pass
        if not answered:
            return {q["key"]: (q.get("default") or "")
                    for q in questions}
        ans = holder.get("answers") or {}
        out = {}
        for q in questions:
            v = ans.get(q["key"])
            if v is None or v == "":
                v = q.get("default") or ""
            out[q["key"]] = str(v)
        return out

    def answer_ask(self, ask_id: str, answer) -> bool:
        with self._ask_lock:
            holder = self._ask_registry.get(ask_id)
        if not holder:
            return False
        if isinstance(answer, dict):
            holder["answers"] = {str(k): str(v)
                                  for k, v in answer.items()}
        elif isinstance(answer, str):
            holder["answers"] = {"answer": answer}
        else:
            holder["answers"] = {}
        try:
            holder["event"].set()
        except Exception:
            return False
        return True

    # ================================================================== #
    # 二维码 / Python 执行
    # ================================================================== #

    def _handle_qrcode_advanced(self, tc: dict) -> None:
        from .tools import (
            qrcode_styled, qrcode_styled_apply,
            qrcode_batch, qrcode_batch_apply,
            qrcode_wifi, qrcode_vcard, qrcode_email,
            qrcode_sms, qrcode_geo,
        )
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")

        if name in ("qrcode_wifi", "qrcode_vcard", "qrcode_email",
                    "qrcode_sms", "qrcode_geo"):
            func_map = {
                "qrcode_wifi": qrcode_wifi,
                "qrcode_vcard": qrcode_vcard,
                "qrcode_email": qrcode_email,
                "qrcode_sms": qrcode_sms,
                "qrcode_geo": qrcode_geo,
            }
            func = func_map[name]
            kw = {"root": self.root}
            if name == "qrcode_wifi":
                kw.update({
                    "ssid": args.get("ssid", ""),
                    "password": args.get("password", ""),
                    "encryption": args.get("encryption", "WPA"),
                    "hidden": bool(args.get("hidden", False)),
                    "style": args.get("style", "rounded"),
                    "out": args.get("out", ""),
                    "fg": args.get("fg", "#000000"),
                    "bg": args.get("bg", "#ffffff"),
                    "size": args.get("size", 10),
                })
            elif name == "qrcode_vcard":
                kw.update({
                    "name": args.get("name", ""),
                    "phone": args.get("phone", ""),
                    "email": args.get("email", ""),
                    "org": args.get("org", ""),
                    "title": args.get("title", ""),
                    "url": args.get("url", ""),
                    "address": args.get("address", ""),
                    "note": args.get("note", ""),
                    "style": args.get("style", "rounded"),
                    "out": args.get("out", ""),
                    "fg": args.get("fg", "#000000"),
                    "bg": args.get("bg", "#ffffff"),
                    "size": args.get("size", 10),
                })
            elif name == "qrcode_email":
                kw.update({
                    "to": args.get("to", ""),
                    "subject": args.get("subject", ""),
                    "body": args.get("body", ""),
                    "style": args.get("style", "rounded"),
                    "out": args.get("out", ""),
                    "fg": args.get("fg", "#000000"),
                    "bg": args.get("bg", "#ffffff"),
                    "size": args.get("size", 10),
                })
            elif name == "qrcode_sms":
                kw.update({
                    "phone": args.get("phone", ""),
                    "message": args.get("message", ""),
                    "style": args.get("style", "rounded"),
                    "out": args.get("out", ""),
                    "fg": args.get("fg", "#000000"),
                    "bg": args.get("bg", "#ffffff"),
                    "size": args.get("size", 10),
                })
            elif name == "qrcode_geo":
                kw.update({
                    "lat": args.get("lat", 0),
                    "lng": args.get("lng", 0),
                    "style": args.get("style", "rounded"),
                    "out": args.get("out", ""),
                    "fg": args.get("fg", "#000000"),
                    "bg": args.get("bg", "#ffffff"),
                    "size": args.get("size", 10),
                })
            res = func(**kw)
            if len(res) == 4:
                preview, is_write, err, content = res
            else:
                preview, is_write, err = res
                content = ""
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            self.console.print(Panel(
                Text(preview, style="bold"),
                title=f"[bold]{name}[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action(name) != "y":
                result = "用户拒绝生成二维码。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            out_path = args.get("out", "")
            if not out_path:
                safe_src = (args.get("ssid") or args.get("name")
                            or args.get("to") or args.get("phone")
                            or f"{args.get('lat', 0)}_{args.get('lng', 0)}")
                safe = "".join(c if c.isalnum() else "_"
                               for c in str(safe_src))[:24]
                out_path = f"qr_{name.replace('qrcode_', '')}_{safe}.png"
            with ui.ToolStatus(self.console, name, out_path[:40]):
                result = qrcode_styled_apply(
                    content=content, out=out_path,
                    style=args.get("style", "rounded"),
                    fg=args.get("fg", "#000000"),
                    bg=args.get("bg", "#ffffff"),
                    gradient_end="", logo="", logo_scale=20,
                    size=args.get("size", 10),
                    border=4, error_level="H",
                    caption="", caption_color="#333333",
                    module_radius=0.5, root=self.root,
                )
            self._log_tool(name, out_path, result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "qrcode_styled":
            preview, is_write, err = qrcode_styled(
                content=args.get("content", ""),
                out=args.get("out", ""),
                style=args.get("style", "rounded"),
                fg=args.get("fg", "#000000"),
                bg=args.get("bg", "#ffffff"),
                gradient_end=args.get("gradient_end", ""),
                logo=args.get("logo", ""),
                logo_scale=args.get("logo_scale", 22),
                size=args.get("size", 10),
                border=args.get("border", 4),
                error_level=args.get("error_level", "H"),
                caption=args.get("caption", ""),
                caption_color=args.get("caption_color", "#333333"),
                module_radius=args.get("module_radius", 0.5),
                root=self.root,
            )
            if err:
                self._log_tool("qrcode_styled", "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            self.console.print(Panel(
                Text(preview, style="bold"),
                title="[bold]qrcode_styled[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("qrcode_styled") != "y":
                result = "用户拒绝生成。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            with ui.ToolStatus(self.console, "qrcode_styled",
                                args.get("out", "")[:40]):
                result = qrcode_styled_apply(
                    content=args.get("content", ""),
                    out=args.get("out", ""),
                    style=args.get("style", "rounded"),
                    fg=args.get("fg", "#000000"),
                    bg=args.get("bg", "#ffffff"),
                    gradient_end=args.get("gradient_end", ""),
                    logo=args.get("logo", ""),
                    logo_scale=args.get("logo_scale", 22),
                    size=args.get("size", 10),
                    border=args.get("border", 4),
                    error_level=args.get("error_level", "H"),
                    caption=args.get("caption", ""),
                    caption_color=args.get("caption_color", "#333333"),
                    module_radius=args.get("module_radius", 0.5),
                    root=self.root,
                )
            self._log_tool("qrcode_styled", args.get("out", ""), result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "qrcode_batch":
            preview, is_write, err = qrcode_batch(
                items=args.get("items") or [],
                out_dir=args.get("out_dir", "qr_batch"),
                style=args.get("style", "rounded"),
                fg=args.get("fg", "#000000"),
                bg=args.get("bg", "#ffffff"),
                gradient_end=args.get("gradient_end", ""),
                size=args.get("size", 10),
                error_level=args.get("error_level", "M"),
                root=self.root,
            )
            if err:
                self._log_tool("qrcode_batch", "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            self.console.print(Panel(
                Text(preview, style="bold"),
                title="[bold]qrcode_batch[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("qrcode_batch") != "y":
                result = "用户拒绝批量生成。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            with ui.ToolStatus(self.console, "qrcode_batch",
                                args.get("out_dir", "")):
                result = qrcode_batch_apply(
                    items=args.get("items") or [],
                    out_dir=args.get("out_dir", "qr_batch"),
                    style=args.get("style", "rounded"),
                    fg=args.get("fg", "#000000"),
                    bg=args.get("bg", "#ffffff"),
                    gradient_end=args.get("gradient_end", ""),
                    size=args.get("size", 10),
                    error_level=args.get("error_level", "M"),
                    root=self.root,
                )
            self._log_tool("qrcode_batch", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})

    def _handle_python_exec(self, tc: dict) -> None:
        from .tools.python_exec import python_exec_preview, python_exec_apply
        args = json.loads(tc["function"]["arguments"] or "{}")
        code = str(args.get("code", ""))
        work_dir = str(args.get("work_dir", ".") or ".")
        timeout = args.get("timeout", 30)
        save_code = bool(args.get("save_code", False))
        install_packages = args.get("install_packages") or []
        if not isinstance(install_packages, list):
            install_packages = [str(install_packages)]
        auto_install = bool(args.get("auto_install", False))

        preview, _, err, meta = python_exec_preview(
            code=code, work_dir=work_dir, timeout=timeout,
            save_code=save_code, install_packages=install_packages,
            auto_install=auto_install, root=self.root,
        )
        if err:
            self._log_tool("python_exec", "", err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        n_lines = len(code.strip().splitlines())
        self.console.print(Panel(
            Text(preview, style="bold"),
            title="[bold]python_exec · 执行前确认[/]",
            title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action("python_exec") != "y":
            result = "用户拒绝执行 Python 代码。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            self._audit("python_exec", "rejected",
                        f"unknown={meta.get('unknown_modules')}")
            self._log_tool("python_exec", work_dir, result)
            return
        to_install = meta.get("install_list", [])
        with ui.ToolStatus(self.console, "python_exec",
                            f"{n_lines} lines"):
            result = python_exec_apply(
                code=code, work_dir=work_dir, timeout=timeout,
                save_code=save_code,
                install_packages=to_install, root=self.root,
            )
        self.tool_cache.clear()
        if not result.startswith("ERROR"):
            self._bump("bash_ops")
            self._audit("python_exec", "ok",
                        f"{n_lines} lines, {len(result)} output"
                        + (f", installed={' '.join(to_install)}"
                           if to_install else ""))
        else:
            self._audit("python_exec", "error", result[:80])
        self._log_tool("python_exec", work_dir, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 通用写操作（video / audio / pdf_advanced / compose / k8s / image）
    # ================================================================== #

    _SIMPLE_WRITE_DISPATCH = {
        "video_convert": ("video_convert", "video_convert_apply",
                          ("path", "out", "fmt", "video_codec",
                           "audio_codec", "crf", "preset", "scale",
                           "bitrate")),
        "video_clip": ("video_clip", "video_clip_apply",
                       ("path", "out", "start", "duration", "end",
                        "reencode")),
        "video_extract_audio": ("video_extract_audio",
                                 "video_extract_audio_apply",
                                 ("path", "out", "fmt", "bitrate")),
        "video_thumbnail": ("video_thumbnail", "video_thumbnail_apply",
                            ("path", "out", "time", "width")),
        "video_to_gif": ("video_to_gif", "video_to_gif_apply",
                         ("path", "out", "start", "duration", "fps",
                          "width")),
        "video_compress": ("video_compress", "video_compress_apply",
                           ("path", "out", "crf", "preset",
                            "target_height")),
        "video_merge": ("video_merge", "video_merge_apply",
                        ("files", "out")),
        "audio_convert": ("audio_convert", "audio_convert_apply",
                          ("path", "out", "fmt", "bitrate",
                           "sample_rate", "channels")),
        "audio_clip": ("audio_clip", "audio_clip_apply",
                       ("path", "out", "start", "duration", "end")),
        "audio_volume": ("audio_volume", "audio_volume_apply",
                         ("path", "out", "db", "percent",
                          "normalize")),
        "audio_concat": ("audio_concat", "audio_concat_apply",
                         ("files", "out")),
        "pdf_watermark": ("pdf_watermark", "pdf_watermark_apply",
                          ("path", "out", "text", "opacity",
                           "font_size", "angle", "color")),
        "pdf_compress": ("pdf_compress", "pdf_compress_apply",
                         ("path", "out", "quality")),
        "pdf_extract_images": ("pdf_extract_images",
                                "pdf_extract_images_apply",
                                ("path", "out_dir")),
        "pdf_rotate": ("pdf_rotate", "pdf_rotate_apply",
                       ("path", "out", "angle", "pages")),
        "pdf_add_page_numbers": ("pdf_add_page_numbers",
                                  "pdf_add_page_numbers_apply",
                                  ("path", "out", "position", "fmt",
                                   "font_size")),
        "pdf_metadata": ("pdf_metadata", "pdf_metadata_apply",
                         ("path", "out", "title", "author",
                          "subject", "keywords")),
        "compose_up": ("compose_up", "compose_up_apply",
                       ("file", "detach", "service", "build")),
        "compose_down": ("compose_down", "compose_down_apply",
                         ("file", "volumes", "remove_images")),
        "compose_restart": ("compose_restart",
                             "compose_restart_apply",
                             ("file", "service")),
        "compose_exec": ("compose_exec", "compose_exec_apply",
                         ("file", "service", "command")),
        "k8s_apply": ("k8s_apply", "k8s_apply_apply",
                      ("file", "manifest", "namespace")),
        "k8s_delete": ("k8s_delete", "k8s_delete_apply",
                       ("resource", "name", "namespace", "file")),
        "k8s_scale": ("k8s_scale", "k8s_scale_apply",
                      ("resource", "name", "replicas", "namespace")),
        "k8s_exec": ("k8s_exec", "k8s_exec_apply",
                     ("pod", "command", "namespace", "container")),
    }

    def _handle_simple_write(self, tc: dict) -> None:
        import one_cedric.tools as _tools
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        spec = self._SIMPLE_WRITE_DISPATCH.get(name)
        if not spec:
            result = f"ERROR: 未知写操作: {name}"
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        preview_name, apply_name, keys = spec
        preview_func = getattr(_tools, preview_name, None)
        apply_func = getattr(_tools, apply_name, None)
        if not preview_func or not apply_func:
            result = (f"ERROR: 内部错误: 找不到 {preview_name}/"
                      f"{apply_name}")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        kw = {k: args.get(k) for k in keys if k in args}
        kw["root"] = self.root
        try:
            pv = preview_func(**kw)
        except TypeError as exc:
            result = f"ERROR: 参数错误: {exc}"
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        preview, is_write, err = pv
        if err:
            self._log_tool(name, "", err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        if not is_write:
            self._log_tool(name, "", preview)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": preview})
            return
        self.console.print(Panel(
            Text(preview, style="bold"),
            title=f"[bold]{name}[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action(name) != "y":
            result = f"用户拒绝执行 {name}。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return
        self._ensure_snapshot()
        target = (args.get("path") or args.get("pod")
                  or args.get("service") or args.get("name") or "")[:40]
        progress_tools = {
            "video_convert", "video_compress", "video_to_gif",
            "video_merge", "video_clip",
            "audio_convert", "audio_concat",
        }
        apply_kw = dict(kw)
        if name in progress_tools:
            last_reported = [-1]
            def _progress(pct, msg):
                p = int(pct)
                if p != last_reported[0] and (p % 5 == 0 or p == 100):
                    last_reported[0] = p
                    self.console.print(
                        f"    [dim]· {name}: {p}%  {msg}[/]")
            apply_kw["progress_cb"] = _progress
        with ui.ToolStatus(self.console, name, target):
            result = apply_func(**apply_kw)
        self.tool_cache.clear()
        if not result.startswith("ERROR"):
            self._bump("write_ops")
        self._audit(name,
                    "ok" if not result.startswith("ERROR") else "error",
                    result[:80])
        self._log_tool(name, target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    def _handle_media_write_tool(self, tc: dict) -> None:
        from .tools import (
            image_process, image_apply,
            qrcode_generate, qrcode_generate_apply,
            symmetric_encrypt, symmetric_encrypt_apply,
            symmetric_decrypt, symmetric_decrypt_apply,
            rsa_generate_keypair, rsa_generate_keypair_apply,
            rsa_encrypt, rsa_encrypt_apply,
            rsa_decrypt, rsa_decrypt_apply,
        )
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        if name == "image_process":
            op = str(args.get("op", "")).lower()
            if op == "info":
                result = image_process(op="info",
                                        path=args.get("path", ""),
                                        root=self.root)
                if isinstance(result, tuple):
                    result = result[0]
                self._log_tool("image_process",
                               args.get("path", ""), result)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            preview, is_write, err = image_process(
                op=op, path=args.get("path", ""),
                out=args.get("out", ""),
                width=args.get("width"), height=args.get("height"),
                percent=args.get("percent"),
                quality=args.get("quality"),
                box=args.get("box"), angle=args.get("angle"),
                flip=args.get("flip", ""), text=args.get("text", ""),
                position=args.get("position", "br"),
                font_size=args.get("font_size"),
                color=args.get("color", ""),
                to_format=args.get("to_format", ""), root=self.root,
            )
            if err:
                self._log_tool("image_process", "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("图像处理", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            self._ensure_snapshot()
            with ui.ToolStatus(self.console, "image_process",
                                args.get("path", "")[:40]):
                result = image_apply(
                    op=op, path=args.get("path", ""),
                    out=args.get("out", "") or "",
                    width=args.get("width"),
                    height=args.get("height"),
                    percent=args.get("percent"),
                    quality=args.get("quality"),
                    box=args.get("box"), angle=args.get("angle"),
                    flip=args.get("flip", ""),
                    text=args.get("text", ""),
                    position=args.get("position", "br"),
                    font_size=args.get("font_size"),
                    color=args.get("color", ""),
                    to_format=args.get("to_format", ""),
                    root=self.root,
                )
            self.tool_cache.clear()
            self._log_tool("image_process", args.get("path", ""),
                            result)
            if not result.startswith("ERROR"):
                self._bump("write_ops")
            self._audit("image_process",
                        "ok" if not result.startswith("ERROR")
                        else "error", result[:80])
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "qrcode_generate":
            preview, is_write, err = qrcode_generate(
                content=args.get("content", ""), out=args.get("out", ""),
                size=args.get("size", 10), border=args.get("border", 4),
                error_level=args.get("error_level", "M"),
                color=args.get("color", "#000000"),
                bg=args.get("bg", "#ffffff"), root=self.root,
            )
            if err:
                self._log_tool("qrcode_generate", "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("生成二维码", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, "qrcode_generate", ""):
                result = qrcode_generate_apply(
                    content=args.get("content", ""),
                    out=args.get("out", "") or "",
                    size=args.get("size", 10),
                    border=args.get("border", 4),
                    error_level=args.get("error_level", "M"),
                    color=args.get("color", "#000000"),
                    bg=args.get("bg", "#ffffff"), root=self.root,
                )
            self._log_tool("qrcode_generate", "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        # crypto
        if name == "symmetric_encrypt":
            preview, _, err = symmetric_encrypt(
                plaintext=args.get("plaintext", ""),
                file=args.get("file", ""), key=args.get("key", ""),
                password=args.get("password", ""),
                out=args.get("out", ""), root=self.root,
            )
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("AES 加密", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, name, ""):
                result = symmetric_encrypt_apply(
                    plaintext=args.get("plaintext", ""),
                    file=args.get("file", ""), key=args.get("key", ""),
                    password=args.get("password", ""),
                    out=args.get("out", "") or "encrypted.bin",
                    root=self.root,
                )
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "symmetric_decrypt":
            preview, _, err = symmetric_decrypt(
                file=args.get("file", ""), key=args.get("key", ""),
                password=args.get("password", ""),
                out=args.get("out", ""), root=self.root,
            )
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("AES 解密", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, name, ""):
                result = symmetric_decrypt_apply(
                    file=args.get("file", ""), key=args.get("key", ""),
                    password=args.get("password", ""),
                    out=args.get("out", "") or "decrypted.bin",
                    root=self.root,
                )
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "rsa_generate_keypair":
            preview, _, err = rsa_generate_keypair(
                bits=args.get("bits", 2048),
                out_dir=args.get("out_dir", "."),
                name=args.get("name", "rsa_key"),
                password=args.get("password", ""), root=self.root,
            )
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("生成 RSA 密钥", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, name, ""):
                result = rsa_generate_keypair_apply(
                    bits=args.get("bits", 2048),
                    out_dir=args.get("out_dir", "."),
                    name=args.get("name", "rsa_key"),
                    password=args.get("password", ""),
                    root=self.root,
                )
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "rsa_encrypt":
            preview, _, err = rsa_encrypt(
                plaintext=args.get("plaintext", ""),
                file=args.get("file", ""),
                pubkey=args.get("pubkey", ""),
                out=args.get("out", ""), root=self.root,
            )
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("RSA 加密", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, name, ""):
                result = rsa_encrypt_apply(
                    plaintext=args.get("plaintext", ""),
                    file=args.get("file", ""),
                    pubkey=args.get("pubkey", ""),
                    out=args.get("out", "") or "encrypted.bin",
                    root=self.root,
                )
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            return

        if name == "rsa_decrypt":
            preview, _, err = rsa_decrypt(
                file=args.get("file", ""),
                privkey=args.get("privkey", ""),
                password=args.get("password", ""),
                out=args.get("out", ""), root=self.root,
            )
            if err:
                self._log_tool(name, "", err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            if not self._write_confirm_panel("RSA 解密", preview):
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": "用户拒绝。"})
                return
            with ui.ToolStatus(self.console, name, ""):
                result = rsa_decrypt_apply(
                    file=args.get("file", ""),
                    privkey=args.get("privkey", ""),
                    password=args.get("password", ""),
                    out=args.get("out", "") or "decrypted.bin",
                    root=self.root,
                )
            self._log_tool(name, "", result)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})

    def _write_confirm_panel(self, title: str, preview: str) -> bool:
        self.console.print(Panel(
            Text(preview, style="bold"),
            title=f"[bold]{title}[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action(title) != "y":
            self.console.print("  [warn]⊘ 已取消[/]")
            return False
        return True

    # ================================================================== #
    # 邮件
    # ================================================================== #

    def _handle_email_write_tool(self, tc: dict) -> None:
        from .tools import (
            email_send_preview, email_send_apply,
            email_reply_preview, email_reply_apply,
            imap_mark_preview, imap_mark_apply,
            imap_move_preview, imap_move_apply,
            imap_delete_preview, imap_delete_apply,
            imap_download_attachment,
        )
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")
        if name == "email_send":
            preview, _, err, payload = email_send_preview(
                account=args.get("account", ""),
                to=args.get("to", ""), subject=args.get("subject", ""),
                body=args.get("body", ""),
                cc=args.get("cc", ""), bcc=args.get("bcc", ""),
                attachments=args.get("attachments") or [],
                root=self.root,
            )
            if err:
                self._log_tool(name, args.get("to", ""), err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            self.console.print(Panel(
                Text(preview, style=""),
                title="[bold]发邮件[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("email_send") != "y":
                result = "用户拒绝发送，邮件未发出。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            with ui.ToolStatus(self.console, "email_send",
                                args.get("to", "")):
                result = email_send_apply(
                    payload, html=bool(args.get("html", False)))
            self._audit("email",
                        "ok" if not result.startswith("ERROR")
                        else "error", result[:80])
        elif name == "email_reply":
            preview, _, err, payload = email_reply_preview(
                account=args.get("account", ""),
                folder=args.get("folder", "INBOX"),
                uid=str(args.get("uid", "")),
                body=args.get("body", ""),
                reply_all=bool(args.get("reply_all", False)),
                attachments=args.get("attachments") or [],
                root=self.root,
            )
            if err:
                self._log_tool(name, str(args.get("uid", "")), err)
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": err})
                return
            self.console.print(Panel(
                Text(preview, style=""),
                title="[bold]回复邮件[/]", title_align="left",
                border_style=WARN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if self._ask_write_action("email_reply") != "y":
                result = "用户拒绝回复，未发出。"
                self.console.print("  [warn]⊘ 已取消[/]")
                self.messages.append({"role": "tool",
                                       "tool_call_id": tc["id"],
                                       "content": result})
                return
            with ui.ToolStatus(self.console, "email_reply",
                                payload.get("to", "")):
                result = email_reply_apply(payload)
        elif name == "email_mark":
            preview, _, err = imap_mark_preview(
                args.get("account", ""), args.get("folder", "INBOX"),
                str(args.get("uid", "")), args.get("action", ""),
            )
            if err:
                result = err
            elif self._ask_write_action("email_mark") != "y":
                result = "用户拒绝，未修改。"
            else:
                with ui.ToolStatus(self.console, "email_mark",
                                    str(args.get("uid", ""))):
                    result = imap_mark_apply(
                        args.get("account", ""),
                        args.get("folder", "INBOX"),
                        str(args.get("uid", "")),
                        args.get("action", ""),
                    )
        elif name == "email_move":
            preview, _, err = imap_move_preview(
                args.get("account", ""), args.get("folder", "INBOX"),
                str(args.get("uid", "")), args.get("dest", ""),
            )
            if err:
                result = err
            elif self._ask_write_action("email_move") != "y":
                result = "用户拒绝，未移动。"
            else:
                with ui.ToolStatus(self.console, "email_move",
                                    str(args.get("uid", ""))):
                    result = imap_move_apply(
                        args.get("account", ""),
                        args.get("folder", "INBOX"),
                        str(args.get("uid", "")),
                        args.get("dest", ""),
                    )
        elif name == "email_delete":
            preview, _, err = imap_delete_preview(
                args.get("account", ""), args.get("folder", "INBOX"),
                str(args.get("uid", "")),
            )
            if err:
                result = err
            elif self._ask_write_action("email_delete") != "y":
                result = "用户拒绝删除，邮件保留。"
            else:
                with ui.ToolStatus(self.console, "email_delete",
                                    str(args.get("uid", ""))):
                    result = imap_delete_apply(
                        args.get("account", ""),
                        args.get("folder", "INBOX"),
                        str(args.get("uid", "")),
                    )
        elif name == "email_download_attachment":
            data, fname, err = imap_download_attachment(
                account=args.get("account", ""),
                folder=args.get("folder", "INBOX"),
                uid=str(args.get("uid", "")),
                index=args.get("index", -1),
                save_to=args.get("save_to", ""),
                root=self.root,
            )
            if err:
                result = err
            else:
                save_to = args.get("save_to", "") or fname
                p, perr = _resolve_path(self.root, save_to)
                if perr:
                    result = perr
                elif self._ask_write_action(
                        "email_download_attachment") != "y":
                    result = "用户拒绝保存附件。"
                else:
                    try:
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(data)
                        result = (f"已保存附件: "
                                  f"{p.relative_to(self.root)}"
                                  f"（{len(data)} bytes）")
                        self.tool_cache.clear()
                        self._bump("write_ops")
                    except OSError as exc:
                        result = f"ERROR: 写入失败: {exc}"
        else:
            result = f"ERROR: 未知邮件工具: {name}"
        self._log_tool(name, "", result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 文件属性
    # ================================================================== #

    def _handle_file_attrs_tool(self, tc: dict) -> None:
        from .tools import (
            file_attrs_preview, file_attrs_apply,
            file_perms_preview, file_perms_apply,
            file_owner_preview, file_owner_apply,
        )
        args = json.loads(tc["function"]["arguments"] or "{}")
        op = str(args.get("op", "")).lower()
        path = args.get("path", "")
        if op == "attrs":
            preview, _, err = file_attrs_preview(
                path=path, action=args.get("action", ""),
                attrs=args.get("attrs") or [], root=self.root,
            )
            if err:
                result = err
            elif not self._write_confirm_panel("文件属性", preview):
                result = "用户拒绝修改属性。"
            else:
                with ui.ToolStatus(self.console, "file_attrs", path):
                    result = file_attrs_apply(
                        path=path, action=args.get("action", ""),
                        attrs=args.get("attrs") or [],
                        root=self.root,
                    )
        elif op == "perms":
            preview, _, err = file_perms_preview(
                path=path, mode=args.get("mode", ""), root=self.root,
            )
            if err:
                result = err
            elif not self._write_confirm_panel("文件权限", preview):
                result = "用户拒绝修改权限。"
            else:
                with ui.ToolStatus(self.console, "file_attrs", path):
                    result = file_perms_apply(
                        path=path, mode=args.get("mode", ""),
                        recursive=bool(args.get("recursive", False)),
                        root=self.root,
                    )
        elif op == "owner":
            preview, _, err = file_owner_preview(
                path=path, user=args.get("user", ""),
                group=args.get("group", ""), root=self.root,
            )
            if err:
                result = err
            elif not self._write_confirm_panel("文件属主", preview):
                result = "用户拒绝修改属主。"
            else:
                with ui.ToolStatus(self.console, "file_attrs", path):
                    result = file_owner_apply(
                        path=path, user=args.get("user", ""),
                        group=args.get("group", ""),
                        recursive=bool(args.get("recursive", False)),
                        root=self.root,
                    )
        else:
            result = f"ERROR: 未知 op: {op}"
        self._log_tool("file_attrs", path, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 数据库写
    # ================================================================== #

    def _handle_db_write(self, tc: dict, args: dict, name: str,
                          keyword: str) -> None:
        from .tools.database import postgres_query, mysql_query
        query = str(args.get("query", ""))
        target = query.strip().splitlines()[0][:80] if query else ""
        preview = (f"数据库写操作: {keyword}\n工具: {name}\n"
                   f"数据库: {args.get('database') or '(env)'}\n\n"
                   f"SQL:\n{query[:800]}"
                   + ("…" if len(query) > 800 else ""))
        self.console.print(Panel(
            Text(preview, style="bold"),
            title=f"[bold err]{name} · {keyword}[/]",
            title_align="left", border_style=ERR_C,
            box=box.ROUNDED, padding=(0, 1), expand=False,
        ))
        if self._ask_write_action(name) != "y":
            result = f"用户拒绝执行数据库写操作（{keyword}）。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            self._audit("db", "rejected", f"{name} {keyword}")
            return
        self._ensure_snapshot()
        with ui.ToolStatus(self.console, name, target):
            if name == "postgres_query":
                result = postgres_query(
                    args.get("conn", ""), query,
                    args.get("database", ""),
                    args.get("params"), args.get("limit", 100),
                )
            else:
                result = mysql_query(
                    args.get("conn", ""), query,
                    args.get("database", ""),
                    args.get("params"), args.get("limit", 100),
                )
        self._bump("write_ops")
        self._audit("db",
                    "ok" if not result.startswith("ERROR") else "error",
                    f"{name} {keyword} · {result[:60]}")
        self._log_tool(name, target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 下载（多线程）
    # ================================================================== #

    def _download(self, tc: dict, args: dict) -> None:
        from .tools.downloader import download_preview, download
        url = args.get("url", "")
        out = args.get("out", "")
        threads = args.get("threads", 0)
        timeout = args.get("timeout", 60)
        resume = bool(args.get("resume", True))
        preview, is_write, err, meta = download_preview(
            url, out, threads, root=self.root)
        if err:
            self._log_tool("download", url, err)
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": err})
            return
        self.console.print(Panel(
            Text(preview, style="bold"),
            title="[bold]下载[/]", title_align="left",
            border_style=WARN_C, box=box.ROUNDED,
            padding=(0, 1), expand=False,
        ))
        if self._ask_write_action("download") != "y":
            result = "用户拒绝下载。"
            self.console.print("  [warn]⊘ 已取消[/]")
            self.messages.append({"role": "tool",
                                   "tool_call_id": tc["id"],
                                   "content": result})
            self._log_tool("download", url, result)
            return
        filename = meta.get("filename", "download")
        try:
            from alive_progress import alive_bar
        except ImportError:
            self.console.print(
                "[warn]alive-progress 未安装，改用终端状态动画。[/]"
            )
            with ui.ToolStatus(self.console, "download", filename[:40]):
                r = download(url, out or filename, threads=threads,
                             timeout=timeout, resume=resume, root=self.root)
        else:
            progress_lock = threading.Lock()
            highest_progress = [0.0]
            with alive_bar(
                    100, manual=True, title=f"download · {filename[:40]}",
                    length=24, stats=True, enrich_print=False) as bar:
                def update_progress(pct, done, total, speed, eta):
                    with progress_lock:
                        highest_progress[0] = max(
                            highest_progress[0],
                            min(100.0, max(0.0, float(pct))),
                        )
                        bar(highest_progress[0] / 100)
                        bar.text(
                            f"{_human_size(done)} / "
                            f"{_human_size(total)} · "
                            f"{_human_size(speed)}/s · ETA {eta:.0f}s"
                        )
                        self._stream_event({
                            "type": "tool_progress",
                            "name": "download",
                            "percent": highest_progress[0],
                            "done": done,
                            "total": total,
                            "speed": speed,
                            "eta": eta,
                        })

                r = download(
                    url, out or filename, threads=threads,
                    timeout=timeout, resume=resume,
                    progress_cb=update_progress, root=self.root,
                )
        if not r["ok"]:
            result = f"ERROR: {r['error']}"
        else:
            p = Path(r["path"])
            rel = (str(p.relative_to(self.root))
                   if p.is_relative_to(self.root) else str(p))
            result = (f"已下载 → {rel}\n"
                      f"大小: {_human_size(r['size'])}  "
                      f"耗时: {r['duration']}s  "
                      f"线程: {r['threads']}"
                      + ("  (续传)" if r.get("resumed") else ""))
        self.tool_cache.clear()
        if r["ok"]:
            self._bump("write_ops")
        self._log_tool("download", url, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # 撤销 / 回滚 / 历史 / Diff / Replay
    # ================================================================== #

    def _do_undo(self) -> None:
        from .ui.confirm import confirm_yes_no
        if not self.undo_stack:
            self.console.print("[dim]没有可撤销的操作。[/]")
            return
        rec = self.undo_stack[-1]
        p: Path = rec["path"]
        rel = rec["rel"]
        current = None
        if p.exists() and p.is_file():
            try:
                current = p.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self.console.print(
                    f"[err]✗ 读取失败: {escape(str(exc))}[/]")
                return
        if rec["existed"]:
            if current is None:
                self.console.print(
                    f"[warn]⚠ {escape(rel)} 已被删除。撤销将重建。[/]")
            elif current != rec["new_text"]:
                self.console.print(
                    f"[warn]⚠ {escape(rel)} 之后又被改动过。[/]")
                if not self.auto_yes:
                    if not confirm_yes_no(
                        self.console,
                        f"文件已被改动，仍要撤销 {rel}？",
                        default_yes=False, danger=True,
                        show_dog=True,
                    ):
                        self.console.print("[dim]已取消。[/]")
                        return
        try:
            if not rec["existed"]:
                if p.exists() and p.is_file():
                    p.unlink()
                action = f"已删除 {rel}（撤销新建）"
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(rec["old_text"], encoding="utf-8")
                action = f"已恢复 {rel} 到修改前状态"
        except OSError as exc:
            self.console.print(
                f"[err]✗ 撤销失败: {escape(str(exc))}[/]")
            return
        self.undo_stack.pop()
        self.tool_cache.clear()
        self._bump("undo_ops")
        self.console.print(f"[ok]↩ {escape(action)}[/]")
        self.messages.append({
            "role": "system",
            "content": f"[One Cedric] 用户撤销了对 {rel} 的修改。",
        })

    def _do_rollback(self) -> None:
        from .ui.confirm import confirm_yes_no
        if not self.git_enabled:
            self.console.print("[warn]当前工作目录不是 git 仓库。[/]")
            return
        if not self.snapshots:
            self.console.print("[dim]本会话还没有可回滚的快照。[/]")
            return
        snap = self.snapshots[-1]
        t = time.strftime("%H:%M:%S", time.localtime(snap["ts"]))
        self.console.print(
            f"[warn]将回滚到快照[/] [dim]({t})[/][warn]：本轮改动会丢失。[/]")
        if not self.auto_yes:
            if not confirm_yes_no(
                self.console, "确认回滚到快照？",
                body=f"本轮改动会丢失\n快照时间: {t}",
                default_yes=False, danger=True,
                show_dog=True,
            ):
                self.console.print("[dim]已取消。[/]")
                return
        ok, msg, affected = git_rollback(self.root, snap)
        if not ok:
            self.console.print(f"[err]✗ {escape(msg)}[/]")
            return
        self.snapshots.pop()
        self.tool_cache.clear()
        self._bump("rollback_ops")
        self.console.print(f"[ok]↩ {escape(msg)}[/]")
        for rel in affected[:10]:
            self.console.print(f"    [dim]· {escape(rel)}[/]")
        if affected:
            affected_set = set(affected)
            self.undo_stack = [
                r for r in self.undo_stack if r["rel"] not in affected_set
            ]
        self.messages.append({
            "role": "system",
            "content": (f"[One Cedric] 用户执行了 /rollback，"
                        f"受影响文件："
                        f"{', '.join(affected) if affected else '无'}。"),
        })

    def _print_history(self) -> None:
        if not self.undo_stack:
            self.console.print("[dim]暂无修改历史。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("#", style="dim", justify="right")
        tbl.add_column("时间", style="dim")
        tbl.add_column("操作", style="bold")
        tbl.add_column("文件")
        tbl.add_column("标签", style="dim")
        tbl.add_column("", style="dim")
        last = len(self.undo_stack)
        for i, rec in enumerate(self.undo_stack, 1):
            t = time.strftime("%H:%M:%S", time.localtime(rec["ts"]))
            note = f"[bold {BRAND}]↩ 下次撤销[/]" if i == last else ""
            tag = rec.get("tag", "") or ""
            tag_disp = f"[accent]{escape(tag)}[/]" if tag else ""
            tbl.add_row(str(i), t, rec["tool"], rec["rel"],
                        tag_disp, note)
        self.console.print(tbl)

    def _cmd_tag(self, arg: str) -> None:
        arg = arg.strip()
        if not arg:
            tagged = [(i + 1, r) for i, r in enumerate(self.undo_stack)
                      if r.get("tag")]
            if not tagged:
                self.console.print("[dim]暂无带标签的改动。[/]")
                return
            tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
            tbl.add_column("#", style="dim", justify="right")
            tbl.add_column("文件", style="bold")
            tbl.add_column("标签")
            for n, rec in tagged:
                tbl.add_row(str(n), rec["rel"],
                            f"[accent]{escape(rec['tag'])}[/]")
            self.console.print(tbl)
            return
        parts = arg.split(maxsplit=1)
        try:
            n = int(parts[0])
        except ValueError:
            self.console.print("[err]✗ 第一个参数必须是序号数字[/]")
            return
        if n < 1 or n > len(self.undo_stack):
            self.console.print(
                f"[err]✗ 序号超出范围（1-{len(self.undo_stack)}）[/]")
            return
        rec = self.undo_stack[n - 1]
        if len(parts) == 1:
            cur = rec.get("tag") or "(无)"
            self.console.print(
                f"[dim]#{n} · {escape(rec['rel'])} ·[/] "
                f"[accent]{escape(cur)}[/]")
            return
        text = parts[1].strip()
        if not text:
            self.console.print("[err]✗ 标签文本不能为空[/]")
            return
        rec["tag"] = text
        self._save_session()
        self.console.print(
            f"[ok]✓ 已给 #{n}（{escape(rec['rel'])}）打标签：[/]"
            f"[accent]{escape(text)}[/]")

    def _cmd_untag(self, arg: str) -> None:
        try:
            n = int(arg.strip())
        except ValueError:
            self.console.print("[err]✗ 参数必须是序号数字[/]")
            return
        if n < 1 or n > len(self.undo_stack):
            self.console.print(
                f"[err]✗ 序号超出范围（1-{len(self.undo_stack)}）[/]")
            return
        rec = self.undo_stack[n - 1]
        rec["tag"] = ""
        self._save_session()
        self.console.print(f"[ok]✓ 已清除 #{n} 的标签[/]")

    def _do_diff(self, arg: str) -> None:
        if not self.undo_stack:
            self.console.print("[dim]没有可显示的修改记录。[/]")
            return
        n = len(self.undo_stack)
        if arg.strip():
            try:
                n = int(arg.strip())
            except ValueError:
                self.console.print("[err]✗ 参数必须是序号数字[/]")
                return
        if n < 1 or n > len(self.undo_stack):
            self.console.print(
                f"[err]✗ 序号超出范围（1-{len(self.undo_stack)}）[/]")
            return
        rec = self.undo_stack[n - 1]
        t = time.strftime("%H:%M:%S", time.localtime(rec.get("ts", 0)))
        self.console.print(
            f"[dim]#{n} · {t} · {escape(rec.get('tool', '?'))} · "
            f"{escape(rec.get('rel', '?'))}[/]")
        is_new = (rec.get("tool") == "write_file"
                  and not rec.get("existed", True))
        self._render_diff(rec.get("rel", "?"),
                          rec.get("old_text", ""),
                          rec.get("new_text", ""),
                          is_new=is_new,
                          tool=rec.get("tool") or None)

    def _print_snapshots(self) -> None:
        if not self.snapshots:
            self.console.print("[dim]本会话还没有快照。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("#", style="dim", justify="right")
        tbl.add_column("时间", style="dim")
        tbl.add_column("基线", style="dim")
        tbl.add_column("未跟踪文件", justify="right", style="dim")
        last = len(self.snapshots)
        for i, snap in enumerate(self.snapshots, 1):
            t = time.strftime("%H:%M:%S",
                              time.localtime(snap["ts"]))
            base = (snap.get("stash_sha") or snap.get("head_sha")
                    or "?")[:8]
            n_unt = len(snap.get("untracked", []))
            note = f"[bold {BRAND}]↩ 下次回滚[/]" if i == last else ""
            tbl.add_row(str(i), t, base, str(n_unt), note)
        self.console.print(tbl)

    def _do_replay(self, arg: str) -> None:
        from .ui.confirm import confirm_yes_no
        if not arg.strip():
            n_user = sum(1 for m in self.messages
                         if m.get("role") == "user")
            self.console.print(
                f"[dim]用法：[/][bold {BRAND}]/replay <n>[/]"
                f"[dim]，当前共 {n_user} 条 user 消息。[/]")
            return
        try:
            n = int(arg.strip())
        except ValueError:
            self.console.print("[err]✗ 参数必须是数字[/]")
            return
        idx = None
        count = 0
        for i, m in enumerate(self.messages):
            if m.get("role") == "user":
                count += 1
                if count == n:
                    idx = i
                    break
        if idx is None:
            self.console.print(f"[err]✗ 第 {n} 条 user 消息不存在[/]")
            return
        replay_text = str(self.messages[idx].get("content") or "")
        discarded = len(self.messages) - idx
        self.console.print(
            f"[warn]将从第 {n} 条用户消息处回放：[/]"
            f"[dim]丢弃之后 {discarded} 条消息。[/]")
        self.console.print("[warn]⚠ 文件层不回退。[/]")
        if not self.auto_yes:
            if not confirm_yes_no(
                self.console, "确认回放？",
                body=f"将丢弃之后 {discarded} 条消息\n文件层不回退",
                default_yes=False, danger=True,
                show_dog=True,
            ):
                self.console.print("[dim]已取消。[/]")
                return
        self.messages = self.messages[:idx]
        self._save_session()
        self.console.print(f"[ok]✓ 已回退到第 {n} 轮之前[/]")
        self.console.print()
        self.console.print(Panel(
            Text(replay_text or "(空)", style="white"),
            title=f"[bold {USER_C}]原第 {n} 轮提问[/]",
            title_align="left", border_style=USER_C,
            box=box.ROUNDED, padding=(0, 1), expand=False,
        ))


    # ================================================================== #
    # 写工具路由（集中派发）
    # ================================================================== #

    def _dispatch_write_single(self, tc: dict, name: str,
                                args: dict) -> None:
        self._stream_tool_start(tc, name, args)
        if name in ("write_file", "edit_file"):
            self._bump_tool(name)
            self._handle_write_tool(tc)
            return
        if name == "apply_patch":
            self._bump_tool("apply_patch")
            self._handle_apply_patch_tool(tc)
            return
        if name == "file_ops":
            self._bump_tool("file_ops")
            self._handle_file_ops_tool(tc)
            return
        if name == "find_replace":
            self._bump_tool("find_replace")
            self._handle_find_replace_tool(tc)
            return
        if name in ("docx", "pdf", "pptx", "excel"):
            self._handle_office_tool(tc)
            return
        if name == "sysop":
            self._handle_sysop_tool(tc)
            return
        if name == "bash":
            self._bump_tool("bash")
            self._handle_shell_tool(tc)
            return
        if name == "bash_bg":
            self._bump_tool("bash_bg")
            self._handle_bash_bg_tool(tc)
            return
        if name == "git":
            self._bump_tool("git")
            self._handle_git_tool(tc)
            return
        if name == "docker":
            self._bump_tool("docker")
            self._handle_docker_tool(tc)
            return
        if name == "sqlite":
            self._bump_tool("sqlite")
            self._handle_sqlite_tool(tc)
            return
        if name == "archive":
            self._bump_tool("archive")
            self._handle_archive_tool(tc)
            return
        if name == "clipboard":
            self._bump_tool("clipboard")
            self._handle_clipboard_tool(tc)
            return
        if name == "todo":
            self._bump_tool("todo")
            self._handle_todo_tool(tc)
            return
        if name == "screen_capture":
            self._handle_screen_capture(tc)
            return
        if name == "screen_info":
            self._handle_screen_info(tc)
            return
        if name == "mouse_action":
            self._handle_mouse_action(tc)
            return
        if name == "keyboard_action":
            self._handle_keyboard_action(tc)
            return
        if name == "window_action":
            self._handle_window_action(tc)
            return
        if name in ("email_send", "email_reply", "email_mark",
                    "email_move", "email_delete",
                    "email_download_attachment"):
            self._bump_tool(name)
            self._handle_email_write_tool(tc)
            return
        if name == "file_attrs":
            op = str(args.get("op", "")).lower()
            if op not in ("get", "bulk"):
                self._bump_tool("file_attrs")
                self._handle_file_attrs_tool(tc)
                return
        if name == "python_exec":
            self._bump_tool("python_exec")
            self._handle_python_exec(tc)
            return
        if name in ("qrcode_styled", "qrcode_batch", "qrcode_wifi",
                    "qrcode_vcard", "qrcode_email", "qrcode_sms",
                    "qrcode_geo"):
            self._bump_tool(name)
            self._handle_qrcode_advanced(tc)
            return
        if name in ("video_convert", "video_clip",
                    "video_extract_audio", "video_thumbnail",
                    "video_to_gif", "video_compress", "video_merge",
                    "audio_convert", "audio_clip", "audio_volume",
                    "audio_concat",
                    "pdf_watermark", "pdf_compress",
                    "pdf_extract_images", "pdf_rotate",
                    "pdf_add_page_numbers", "pdf_metadata",
                    "compose_up", "compose_down", "compose_restart",
                    "compose_exec", "k8s_apply", "k8s_delete",
                    "k8s_scale", "k8s_exec"):
            self._bump_tool(name)
            self._handle_simple_write(tc)
            return
        if name in ("memory_remember", "memory_forget"):
            self._bump_tool(name)
            self._handle_memory_tool(tc)
            return
        if name in ("cron_add", "cron_remove", "cron_enable"):
            self._bump_tool(name)
            self._handle_cron_tool(tc)
            return
        if name == "spawn_agent":
            self._bump_tool("spawn_agent")
            self._handle_spawn_agent(tc, args)
            return
        if name == "ask_user":
            self._bump_tool("ask_user")
            self._handle_ask_user(tc, args)
            return
        if name == "multi_review":
            self._bump_tool("multi_review")
            self._handle_multi_review(tc, args)
            return
        if name == "dream_run":
            self._bump_tool("dream_run")
            self._handle_dream_tool(tc)
            return
        if name in ("notify", "notify_actions"):
            self._bump_tool(name)
            self._handle_notify_tool(tc)
            return
        if name in ("pkg_install", "pkg_uninstall"):
            self._bump_tool(name)
            self._handle_pkg_tool(tc)
            return
        if name == "download":
            self._bump_tool("download")
            self._download(tc, args)
            return
        if name == "cost_export":
            self._bump_tool("cost_export")
            self._handle_cost_export(tc, args)
            return
        if name == "image_process":
            self._bump_tool("image_process")
            self._handle_media_write_tool(tc)
            return
        if name in ("symmetric_encrypt", "symmetric_decrypt",
                    "rsa_generate_keypair", "rsa_encrypt",
                    "rsa_decrypt", "qrcode_generate"):
            self._bump_tool(name)
            self._handle_media_write_tool(tc)
            return

        from .integrations import is_external_tool
        if is_external_tool(name):
            target = ui.format_tool_call(name, args, self._shorten)
            if self._ask_write_action(name) != "y":
                result = "用户拒绝执行外部工具。"
                self.console.print("  [warn]⊘ 已取消[/]")
            else:
                with ui.ToolStatus(self.console, name, target):
                    result = dispatch_tool(name, args, self.root)
            self._log_tool(name, target, result)
            self.messages.append({
                "role": "tool", "tool_call_id": tc["id"],
                "content": result,
            })
            return

        # 兜底：当只读处理
        target = ui.format_tool_call(name, args, self._shorten)
        with ui.ToolStatus(self.console, name, target):
            result = dispatch_tool(name, args, self.root)
        self._log_tool(name, target, result)
        self.messages.append({"role": "tool",
                               "tool_call_id": tc["id"],
                               "content": result})

    # ================================================================== #
    # Session 管理
    # ================================================================== #

    def _print_sessions(self) -> None:
        sessions = list_session_files(root=self.root)
        if not sessions:
            self.console.print("[dim]本工作目录还没有保存的会话。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("ID", style="bold")
        tbl.add_column("标题", style="accent")
        tbl.add_column("更新时间", style="dim")
        tbl.add_column("模型", style="dim")
        tbl.add_column("消息", justify="right", style="dim")
        tbl.add_column("", style="dim")
        for data in sessions[:20]:
            sid = data["id"]
            title = data.get("title") or "[dim]·[/]"
            if data.get("title_source") == "user":
                title = f"[bold {BRAND}]{escape(data['title'])}[/]"
            ts = time.strftime("%m-%d %H:%M",
                               time.localtime(data.get("updated_at", 0)))
            n = len(data.get("messages", []))
            note = (f"[bold {BRAND}]← 当前[/]"
                    if sid == self.session_id else "")
            tbl.add_row(sid, title, ts, data.get("model", "?"),
                        str(n), note)
        self.console.print(tbl)

    def _do_resume(self, token: str) -> None:
        if token == self.session_id:
            self.console.print("[dim]已经是当前会话。[/]")
            return
        data = find_session_by_id_or_title(token)
        if not data:
            self.console.print(f"[err]✗ 找不到会话: {escape(token)}[/]")
            return
        if data.get("root") != str(self.root):
            self.console.print(
                f"[err]✗ 该会话的工作目录为 "
                f"{escape(data.get('root', '?'))}，与当前不同。[/]")
            return
        self._save_session()
        self.session_id = data["id"]
        self.session_created_at = data.get("created_at", time.time())
        self.model = data.get("model", self.model)
        msgs = data.get("messages") or [self.system_msg]
        if not msgs or msgs[0].get("role") != "system":
            msgs = [self.system_msg] + msgs
        self.messages = msgs
        self.undo_stack = []
        for rec in data.get("undo_stack", []):
            self.undo_stack.append({
                "path": self.root / rec["rel"], "rel": rec["rel"],
                "old_text": rec.get("old_text", ""),
                "new_text": rec.get("new_text", ""),
                "existed": rec.get("existed", False),
                "tool": rec.get("tool", ""),
                "ts": rec.get("ts", 0.0),
                "tag": rec.get("tag", ""),
            })
        self.snapshots = list(data.get("snapshots", []))
        self.compactions = list(data.get("compactions", []))
        self.audit_log = list(data.get("audit_log", []))
        self.todos = list(data.get("todos", []))
        self.session_asks = list(data.get("asks", []))
        self._todo_next_id = max(
            [t.get("id", 0) for t in self.todos] + [0]) + 1
        self.session_title = data.get("title", "") or ""
        self.title_source = data.get("title_source", "") or ""
        s = data.get("stats") or {}
        self.stats = {
            "turns": int(s.get("turns", 0)),
            "tool_calls": dict(s.get("tool_calls", {})),
            "write_ops": int(s.get("write_ops", 0)),
            "bash_ops": int(s.get("bash_ops", 0)),
            "bash_failures": int(s.get("bash_failures", 0)),
            "undo_ops": int(s.get("undo_ops", 0)),
            "rollback_ops": int(s.get("rollback_ops", 0)),
            "turn_durations": list(s.get("turn_durations", [])),
            "started_at": float(s.get("started_at", time.time())),
            "total_input_tokens": int(s.get("total_input_tokens", 0)),
            "total_output_tokens": int(s.get("total_output_tokens", 0)),
            "total_cached_tokens": int(s.get("total_cached_tokens", 0)),
        }
        self.console.print(
            f"[ok]✓ 已恢复会话[/] [accent]{escape(self.session_id)}[/]"
            f" [dim]（{len(self.messages) - 1} 条消息）[/]")

    def _new_session(self) -> None:
        if len(self.messages) > 1 or self.undo_stack or self.snapshots:
            self._save_session()
        else:
            delete_session_file(self.session_id)
        self.session_id = _new_session_id()
        self.session_created_at = time.time()
        self.messages = [self.system_msg]
        self.undo_stack = []
        self.snapshots = []
        self.audit_log = []
        self.todos = []
        self.session_asks = []
        self._todo_next_id = 1
        self.session_title = ""
        self.title_source = ""
        self.plan_mode = False
        self.plan_active = False
        self.plan_items = []
        self.stats = {
            "turns": 0, "tool_calls": {},
            "write_ops": 0, "bash_ops": 0, "bash_failures": 0,
            "undo_ops": 0, "rollback_ops": 0,
            "turn_durations": [], "started_at": time.time(),
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_cached_tokens": 0,
        }
        self.console.print(
            f"[ok]✓ 已开启新会话[/] "
            f"[accent]{escape(self.session_id)}[/]")

    def _do_save_as(self, name: str) -> None:
        name = name.strip()
        if not name:
            self.console.print("[err]✗ 名称不能为空[/]")
            return
        if len(name) > 60:
            self.console.print("[err]✗ 名称过长（最多 60 字符）[/]")
            return
        for s in list_session_files(root=self.root):
            if s.get("title") == name and s.get("id") != self.session_id:
                self.console.print(f"[err]✗ 本目录下已有同名会话[/]")
                return
        self.session_title = name
        self.title_source = "user"
        self._save_session()
        self.console.print(
            f"[ok]✓ 会话已命名为[/] [accent]{escape(name)}[/]")

    # ================================================================== #
    # 标题 / 压缩
    # ================================================================== #

    @staticmethod
    def _clean_title(raw: str) -> str:
        s = (raw or "").strip()
        if len(s) >= 2 and s[0] in "\"'「『" and s[-1] in "\"'」』":
            s = s[1:-1].strip()
        s = s.splitlines()[0].strip() if s else ""
        s = s.rstrip("。.！!？?；;，,")
        if len(s) > 30:
            s = s[:29] + "…"
        return s

    def _maybe_generate_title(self) -> None:
        if self.title_source == "user":
            return
        if self.title_source == "auto" and self.session_title:
            return
        user_count = sum(1 for m in self.messages
                         if m.get("role") == "user")
        if user_count != 1:
            return
        first_user = ""
        first_asst = ""
        for m in self.messages:
            if m.get("role") == "user" and not first_user:
                first_user = str(m.get("content") or "")
            elif m.get("role") == "assistant" and not first_asst:
                c = (m.get("content") or "").strip()
                if c:
                    first_asst = c
            if first_user and first_asst:
                break
        if not first_user:
            return
        snippet = (f"用户：{first_user[:500]}\n\n"
                   f"助手："
                   f"{first_asst[:500] if first_asst else '(未产生文本回复)'}")
        with self.console.status("[dim]生成标题中…[/]", spinner="dots"):
            try:
                raw = self._once_chat(
                    [{"role": "system", "content": TITLE_PROMPT},
                     {"role": "user", "content": snippet}],
                    temperature=0.3)
            except SystemExit:
                return
        title = self._clean_title(raw)
        if not title:
            return
        self.session_title = title
        self.title_source = "auto"
        self.console.print(
            f"[dim]· 会话标题：[/][accent]{escape(title)}[/]"
            f" [dim]（[/][bold {BRAND}]/save-as <名>[/][dim] 可改名）[/]")

    def _render_for_summary(self, messages: list) -> str:
        L = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "user":
                L.append(f"### 用户\n{content}\n")
            elif role == "assistant":
                text = content.strip()
                if text:
                    L.append(f"### 助手\n{text}\n")
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "?")
                    raw = fn.get("arguments", "{}")
                    if len(raw) > 300:
                        raw = raw[:300] + "...(截断)"
                    L.append(f"[工具调用: {name}({raw})]\n")
            elif role == "tool":
                text = content
                if len(text) > 600:
                    text = text[:600] + "...(截断)"
                L.append(f"[工具结果]\n{text}\n")
            elif role == "system":
                if "历史摘要" in content:
                    L.append(f"### 之前的历史摘要\n{content}\n")
        return "\n".join(L)

    def _compact(self, keep_turns: int | None = None) -> None:
        if keep_turns is None:
            keep_turns = self.compact_keep_turns
        if keep_turns < 1:
            self.console.print("[err]✗ keep_turns 至少为 1[/]")
            return
        split = _find_split_index(self.messages, keep_turns)
        if split is None:
            n_user = sum(1 for m in self.messages
                         if m.get("role") == "user")
            self.console.print(
                f"[dim]当前只有 {n_user} 轮对话，不足以压缩。[/]")
            return
        old_msgs = self.messages[1:split]
        if not old_msgs:
            self.console.print("[dim]没有可压缩的内容。[/]")
            return
        before_tokens = _estimate_tokens(self.messages)
        self.console.print(
            f"[dim]正在压缩 {len(old_msgs)} 条历史消息"
            f"（约 {before_tokens} tokens）…[/]")
        summary_messages = [
            {"role": "system", "content": COMPACT_PROMPT},
            {"role": "user",
             "content": "对话历史如下：\n\n"
             + self._render_for_summary(old_msgs)},
        ]
        with self.console.status("[dim]生成摘要中…[/]", spinner="dots"):
            try:
                summary = self._once_chat(summary_messages,
                                           temperature=0.2)
            except SystemExit as exc:
                self.console.print(
                    f"[err]✗ 摘要失败: {escape(str(exc))}[/]")
                return
        summary = (summary or "").strip()
        if not summary:
            self.console.print(
                "[err]✗ 模型返回了空摘要，未做压缩。[/]")
            return
        summary_msg = {
            "role": "system",
            "content": "[历史摘要 · 由 /compact 生成]\n\n" + summary,
        }
        kept_msgs = self.messages[split:]
        new_messages = [self.system_msg, summary_msg] + kept_msgs
        after_tokens = _estimate_tokens(new_messages)
        self.compactions.append({
            "ts": time.time(),
            "before_count": len(self.messages) - 1,
            "after_count": len(new_messages) - 1,
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "keep_turns": keep_turns,
        })
        self.messages = new_messages
        ui.render_summary_panel(self.console, summary)
        saved_pct = ((1 - after_tokens / before_tokens) * 100
                     if before_tokens else 0)
        self.console.print(
            f"[ok]✓ 已压缩[/] "
            f"[dim]消息 {len(old_msgs)} → 1 条摘要，"
            f"token 估算 {before_tokens} → {after_tokens}"
            f"（−{saved_pct:.0f}%）[/]")
        self._save_session()

    def _maybe_auto_compact(self) -> None:
        if self.auto_compact_threshold <= 0:
            return
        tokens = _estimate_tokens(self.messages)
        if tokens < self.auto_compact_threshold:
            return
        self.console.print(
            f"[warn]⚠ 对话已约 {tokens} tokens"
            f"（阈值 {self.auto_compact_threshold}），[/]"
            f"[dim]可运行 [/][bold {BRAND}]/compact[/]"
            f"[dim] 压缩历史。[/]")

    # ================================================================== #
    # 统计 / 审计 / 缓存
    # ================================================================== #

    def _print_turn_metrics(self, *, elapsed: float,
                             input_chars: int, output_chars: int,
                             first_token_at: float | None,
                             first_content_at: float | None,
                             t_start: float) -> None:
        real_usage = self._last_usage or {}
        real_in = _extract_input_tokens(real_usage)
        real_out = _extract_output_tokens(real_usage)
        real_cached = _extract_cached_tokens(real_usage)
        if real_in or real_out:
            in_tok = real_in
            out_tok = real_out
            cached_tok = real_cached
            tag = ""
        else:
            in_tok = int(input_chars / 2.5)
            out_tok = int(output_chars / 2.5)
            cached_tok = 0
            tag = "~"
        speed_base = t_start
        if first_content_at:
            speed_base = first_content_at
        elif first_token_at:
            speed_base = first_token_at
        gen_time = max(0.001, elapsed - (speed_base - t_start))
        speed = out_tok / gen_time if gen_time > 0 else 0
        ttfb = (first_token_at - t_start) if first_token_at else 0
        parts = [f"[dim]输入[/] [accent]{tag}{in_tok}[/][dim] tok[/]"]
        if cached_tok > 0:
            parts.append(f"[dim]缓存[/] [accent]{cached_tok}[/][dim] tok[/]")
        parts.append(f"[dim]输出[/] [accent]{tag}{out_tok}[/][dim] tok[/]")
        parts.append(f"[dim]{speed:.1f} tok/s[/]")
        parts.append(f"[dim]耗时 {elapsed:.1f}s[/]")
        if ttfb > 0:
            parts.append(f"[dim]首字 {ttfb:.1f}s[/]")
        self.stats["total_input_tokens"] = (
            self.stats.get("total_input_tokens", 0) + in_tok)
        self.stats["total_output_tokens"] = (
            self.stats.get("total_output_tokens", 0) + out_tok)
        self.stats["total_cached_tokens"] = (
            self.stats.get("total_cached_tokens", 0) + cached_tok)
        from .pricing import compute_cost
        turn_cost = compute_cost(self.model, in_tok, out_tok, cached_tok)
        if turn_cost > 0:
            parts.append(f"[dim]本轮[/] [accent]${turn_cost:.5f}[/]")
        self.console.print(
            "  [dim]│[/] " + "  [dim]·[/]  ".join(parts))
        try:
            from .cost_tracker import (
                record, check_budget, check_turn_anomaly,
            )
            record(self.model, in_tok, out_tok, cached_tok,
                   turn_cost, session_id=self.session_id)
            budget_info = check_budget()
            for ex in budget_info.get("exceeded", []):
                self.console.print(
                    f"  [err]⚠ 预算超支（{ex['period']}）："
                    f"${ex['spent']:.4f} / ${ex['budget']:.4f} "
                    f"({ex['pct']:.0f}%)[/]")
            for w in budget_info.get("warnings", []):
                self.console.print(
                    f"  [warn]⚠ 预算接近上限（{w['period']}）："
                    f"${w['spent']:.4f} / ${w['budget']:.4f} "
                    f"({w['pct']:.0f}%)[/]")
            anomaly = check_turn_anomaly(turn_cost)
            if anomaly:
                self.console.print(
                    f"  [warn]⚠ 单轮成本异常：本轮 "
                    f"${anomaly['cost']:.5f} 是近期均值的 "
                    f"{anomaly['multiple']:.1f}× "
                    f"（z-score {anomaly['z_score']:.2f}）[/]")
                self._audit("cost_anomaly", "warn",
                            f"${anomaly['cost']:.5f} · "
                            f"{anomaly['multiple']:.1f}×均值")
        except Exception:
            pass
        self._last_usage = None

    def _print_stats(self) -> None:
        s = self.stats
        cache = self.tool_cache.stats()
        cur_tokens = _estimate_tokens(self.messages)
        uptime = time.time() - s.get("started_at", time.time())
        uptime_str = (
            f"{int(uptime // 3600)}h{int(uptime % 3600 // 60)}m"
            if uptime > 3600
            else f"{int(uptime // 60)}m{int(uptime % 60)}s")
        self.console.print(
            f"[bold {BRAND}]会话[/] "
            f"[dim]{escape(self.session_id)}[/]   "
            f"[dim]运行[/] [accent]{uptime_str}[/]   "
            f"[dim]当前上下文约[/] [accent]{cur_tokens}[/] "
            f"[dim]tokens[/]")
        self.console.print()
        g = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        g.add_column(style="dim")
        g.add_column(style="bold")
        total_tool = sum(s.get("tool_calls", {}).values())
        total_dur = sum(s.get("turn_durations", []))
        avg_dur = (total_dur / len(s["turn_durations"])
                   if s["turn_durations"] else 0)
        g.add_row("对话轮数", str(s.get("turns", 0)))
        g.add_row("工具调用", f"{total_tool} 次")
        g.add_row("写操作", f"{s.get('write_ops', 0)} 次")
        g.add_row("Bash 调用",
                  f"{s.get('bash_ops', 0)} 次"
                  f"（失败 {s.get('bash_failures', 0)}）")
        g.add_row("撤销 / 回滚",
                  f"{s.get('undo_ops', 0)} / {s.get('rollback_ops', 0)}")
        g.add_row("总推理耗时",
                  f"{total_dur:.1f}s（均 {avg_dur:.2f}s/轮）")
        g.add_row("缓存命中率", f"[accent]{cache['rate']:.1f}%[/]")
        g.add_row("Plan 模式",
                  f"{'on' if self.plan_mode else 'off'} / "
                  f"{'执行中' if self.plan_active else '未执行'}")
        self.console.print(g)
        tool_calls = s.get("tool_calls", {})
        if tool_calls:
            self.console.print()
            t = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
            t.add_column("工具", style="bold")
            t.add_column("次数", justify="right")
            t.add_column("占比", justify="right", style="dim")
            t.add_column("", style="dim")
            for name, count in sorted(tool_calls.items(),
                                       key=lambda x: -x[1]):
                pct = count / total_tool * 100 if total_tool else 0
                bar = "█" * max(1, int(pct / 5))
                t.add_row(name, str(count), f"{pct:.1f}%",
                          f"[{ACCENT}]{bar}[/]")
            self.console.print(t)

    def _cmd_audit(self, arg: str) -> None:
        arg = arg.strip()
        if not arg:
            self._print_audit("recent")
            return
        parts = arg.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) == 2 else None
        if sub == "all":
            self._print_audit("all")
        elif sub == "export":
            self._export_audit("md", rest)
        elif sub == "csv":
            self._export_audit("csv", rest)
        elif sub == "clear":
            from .ui.confirm import confirm_yes_no
            if not self.auto_yes:
                if not confirm_yes_no(
                    self.console, "清空所有审计记录？",
                    default_yes=False, danger=True,
                    show_dog=True,
                ):
                    self.console.print("[dim]已取消。[/]")
                    return
            n = len(self.audit_log)
            self.audit_log = []
            self._save_session()
            self.console.print(f"[ok]✓ 已清空 {n} 条审计记录。[/]")
        else:
            self.console.print(
                "[dim]用法：/audit [all|export|csv|clear][/]")

    def _print_audit(self, mode: str = "recent") -> None:
        entries = self.audit_log
        if not entries:
            self.console.print("[dim]暂无审计记录。[/]")
            return
        if mode == "recent":
            entries = entries[-30:]
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("时间", style="dim")
        tbl.add_column("类型", style="bold")
        tbl.add_column("结果", style="bold")
        tbl.add_column("对象")
        tbl.add_column("rc", justify="right", style="dim")
        tbl.add_column("耗时", justify="right", style="dim")
        verdict_style = {
            "ok": "ok", "blocked": "warn", "rejected": "warn",
            "timeout": "err", "error": "err", "warn": "warn",
        }
        for e in entries:
            t = time.strftime("%H:%M:%S",
                              time.localtime(e.get("ts", 0)))
            v = e.get("verdict", "?")
            v_style = verdict_style.get(v, "dim")
            obj = e.get("command") or e.get("path") or ""
            if len(obj) > 55:
                obj = obj[:52] + "…"
            rc = e.get("returncode")
            rc_s = str(rc) if rc is not None else "—"
            dur = e.get("duration", 0.0)
            dur_s = f"{dur:.2f}s" if dur else "—"
            tbl.add_row(t, e.get("kind", "?"),
                        f"[{v_style}]{v}[/]",
                        escape(obj), rc_s, dur_s)
        self.console.print(tbl)

    def _export_audit(self, fmt: str, target: str | None) -> None:
        if not self.audit_log:
            self.console.print("[dim]暂无审计记录可导出。[/]")
            return
        ext = ".csv" if fmt == "csv" else ".md"
        if target:
            out = Path(target).expanduser()
            if not out.is_absolute():
                out = Path.cwd() / out
        else:
            out = Path.cwd() / f"audit-{self.session_id}{ext}"
        try:
            if fmt == "csv":
                import csv as _csv
                import io
                buf = io.StringIO()
                w = _csv.writer(buf)
                w.writerow(["time", "kind", "verdict",
                            "command_or_path", "returncode",
                            "duration_s", "timeout", "summary"])
                for e in self.audit_log:
                    w.writerow([
                        time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(e.get("ts", 0))),
                        e.get("kind", ""), e.get("verdict", ""),
                        e.get("command") or e.get("path", ""),
                        e.get("returncode")
                        if e.get("returncode") is not None else "",
                        e.get("duration", 0.0),
                        e.get("timeout") or "",
                        e.get("summary", ""),
                    ])
                content = buf.getvalue()
            else:
                content = self._render_audit_markdown()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        except OSError as exc:
            self.console.print(
                f"[err]✗ 导出失败: {escape(str(exc))}[/]")
            return
        self.console.print(
            f"[ok]✓ 已导出 {len(self.audit_log)} 条审计记录到[/] "
            f"[path]{escape(str(out))}[/]")

    def _render_audit_markdown(self) -> str:
        L = [f"# 审计日志 · "
             f"{self.session_title or self.session_id}", ""]
        L.append(f"- **会话**：`{self.session_id}`")
        L.append(f"- **模型**：`{self.model}`")
        L.append(f"- **导出时间**："
                 f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
        L.append("")
        L.append("| 时间 | 类型 | 结果 | 对象 | rc | 耗时 |")
        L.append("|------|------|------|------|----|----|")
        for e in self.audit_log:
            t = time.strftime("%Y-%m-%d %H:%M:%S",
                              time.localtime(e.get("ts", 0)))
            obj = (e.get("command") or e.get("path") or "").replace(
                "|", "\\|")[:77]
            rc = e.get("returncode")
            rc_s = str(rc) if rc is not None else "—"
            dur = e.get("duration", 0.0)
            dur_s = f"{dur:.2f}s" if dur else "—"
            L.append(f"| {t} | `{e.get('kind', '')}` | "
                     f"{e.get('verdict', '')} | "
                     f"`{obj}` | {rc_s} | {dur_s} |")
        return "\n".join(L)

    def _handle_cache_command(self, arg: str) -> None:
        arg = arg.strip().lower()
        if arg == "clear":
            self.tool_cache.clear()
            self.console.print("[ok]✓ 已清空工具缓存。[/]")
            return
        s = self.tool_cache.stats()
        self.console.print(
            f"[dim]条目:[/] [accent]{s['entries']}[/]"
            f"[dim]/{s['max_entries']}[/]   "
            f"[dim]命中:[/] [ok]{s['hits']}[/]   "
            f"[dim]未命中:[/] [warn]{s['misses']}[/]   "
            f"[dim]命中率:[/] [accent]{s['rate']:.1f}%[/]")

    # ================================================================== #
    # 配置 / Profile
    # ================================================================== #

    def _print_config(self) -> None:
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("键", style="bold")
        tbl.add_column("当前值")
        tbl.add_row("model", escape(str(self.model)))
        tbl.add_row("host", escape(str(self.host)))
        tbl.add_row("api_key", "（已设置）" if self.api_key
                    else "（未设置）")
        tbl.add_row("temperature", str(self.temperature))
        tbl.add_row("max_steps", str(self.max_steps))
        tbl.add_row("auto_yes", "true" if self.auto_yes else "false")
        tbl.add_row("show_reasoning",
                    "true" if self.show_reasoning else "false")
        tbl.add_row("think_level", str(self.think_level))
        tbl.add_row("access_mode", str(self.access_mode))
        tbl.add_row("allow_arbitrary_shell",
                    "开启" if self.allow_arbitrary_shell else "关闭")
        tbl.add_row("computer_use",
                    "开启" if getattr(self._computer_policy, "enabled",
                                       False) else "关闭")
        tbl.add_row("vision", "开启" if self.enable_vision else "关闭")
        tbl.add_row("禁用工具", str(len(self.disabled_tools)) + " 个")
        self.console.print(tbl)
        self.console.print(
            f"[dim]全局配置:[/] "
            f"[path]{escape(str(self.config_path))}[/]")
        self.console.print(
            f"[dim]项目配置:[/] "
            f"[path]{escape(str(self.project_config_path))}[/]")
        self.console.print(
            f"[dim]工具配置:[/] "
            f"[path]{escape(str(tools_config_path()))}[/]")

    def _save_config(self, scope: str) -> None:
        d = self.config.setdefault("default", {})
        d["model"] = self.model
        d["host"] = self.host
        d["temperature"] = self.temperature
        d["max_steps"] = self.max_steps
        d["auto_yes"] = self.auto_yes
        d["show_reasoning"] = self.show_reasoning
        d["think_level"] = self.think_level
        d["allow_arbitrary_shell"] = self.allow_arbitrary_shell
        d["enable_computer_use"] = getattr(
            self._computer_policy, "enabled", False)
        d["enable_vision"] = self.enable_vision
        d["access_mode"] = self.access_mode
        if self.api_key:
            d["api_key"] = self.api_key
        self.config.setdefault("bash", {}).setdefault(
            "extra_prefixes", [])
        if scope == "project":
            target = self.project_config_path
            root_arg = self.root
        elif scope == "global":
            target = self.config_path
            root_arg = None
        else:
            self.console.print(f"[err]✗ 未知范围: {escape(scope)}[/]")
            return
        if save_config_file(target, self.config, root=root_arg):
            self.console.print(
                f"[ok]✓ 已保存配置到[/] "
                f"[path]{escape(str(target))}[/]")

    def _profile_snapshot_current(self) -> dict:
        return {
            "default": {
                "model": self.model, "host": self.host,
                "temperature": self.temperature,
                "auto_yes": self.auto_yes,
                "max_steps": self.max_steps,
                "show_reasoning": self.show_reasoning,
                "snapshot_granularity": self.snapshot_granularity,
            },
            "bash": {
                "extra_prefixes": list(
                    self.config.get("bash", {}).get(
                        "extra_prefixes", [])),
            },
        }

    def _cmd_profile(self, arg: str) -> None:
        arg = arg.strip()
        if not arg or arg.lower() in ("list", "ls"):
            self._print_profiles()
            return
        parts = arg.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) == 2 else ""
        if sub == "save" and rest:
            self._profile_save(rest)
        elif sub == "load" and rest:
            self._profile_load(rest)
        elif sub == "show" and rest:
            self._profile_show(rest)
        elif sub in ("delete", "rm", "del") and rest:
            self._profile_delete(rest)
        else:
            self.console.print(
                "[dim]用法：/profile [save|load|show|delete] <名>[/]")

    def _print_profiles(self) -> None:
        profiles = list_profiles()
        if not profiles:
            self.console.print("[dim]还没有保存的工作画像。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("名称", style="bold")
        tbl.add_column("模型", style="dim")
        tbl.add_column("快照", style="dim")
        tbl.add_column("", style="dim")
        for p in profiles:
            note = (f"[bold {BRAND}]← 当前[/]"
                    if p["name"] == self.active_profile else "")
            tbl.add_row(p["name"], p.get("model", "?"),
                        p.get("snapshot_granularity", "turn"), note)
        self.console.print(tbl)

    def _profile_save(self, name: str) -> None:
        if not PROFILE_NAME_RE.match(name):
            self.console.print(
                "[err]✗ 名称只能包含字母、数字、下划线、连字符[/]")
            return
        snap = self._profile_snapshot_current()
        if not save_profile(name, snap, preset_tag=self.preset_tag):
            self.console.print("[err]✗ 保存画像失败。[/]")
            return
        self.active_profile = name
        self.console.print(
            f"[ok]✓ 已保存画像[/] [accent]{escape(name)}[/]")

    def _profile_load(self, name: str) -> None:
        from .tools.shell import merge_bash_prefixes
        raw = load_profile(name)
        if raw is None:
            self.console.print(f"[err]✗ 找不到画像: {escape(name)}[/]")
            return
        d = raw.get("default") or {}
        if "model" in d and isinstance(d["model"], str):
            self.model = d["model"].strip() or self.model
        if "host" in d and isinstance(d["host"], str):
            self.host = d["host"].strip() or self.host
        if isinstance(d.get("temperature"), (int, float)):
            self.temperature = float(d["temperature"])
        if isinstance(d.get("max_steps"), int):
            self.max_steps = max(1, int(d["max_steps"]))
        if isinstance(d.get("auto_yes"), bool):
            self.auto_yes = d["auto_yes"]
        if isinstance(d.get("show_reasoning"), bool):
            self.show_reasoning = d["show_reasoning"]
        if isinstance(d.get("snapshot_granularity"), str):
            g = d["snapshot_granularity"]
            if g in ("turn", "write"):
                self.snapshot_granularity = g
        extra = (raw.get("bash") or {}).get("extra_prefixes") or []
        existing = self.config.setdefault("bash", {}).setdefault(
            "extra_prefixes", [])
        newly = []
        for x in extra:
            s = str(x).strip()
            if s and s not in existing:
                existing.append(s)
                newly.append(s)
        if newly:
            merge_bash_prefixes(newly)
        self.preset_tag = profile_preset_tag(raw)
        self.active_profile = name
        self.messages = [self.system_msg]
        self._save_session()
        self.console.print(
            f"[ok]✓ 已加载画像[/] [accent]{escape(name)}[/]")

    def _profile_show(self, name: str) -> None:
        raw = load_profile(name)
        if raw is None:
            self.console.print(f"[err]✗ 找不到画像: {escape(name)}[/]")
            return
        d = raw.get("default") or {}
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        tbl.add_column(style="dim")
        tbl.add_column(style="bold")
        tbl.add_row("名称", f"[accent]{escape(name)}[/]")
        tbl.add_row("模型", escape(str(d.get("model", "—"))))
        tbl.add_row("Host", escape(str(d.get("host", "—"))))
        tbl.add_row("温度", str(d.get("temperature", "—")))
        tbl.add_row("最大步数", str(d.get("max_steps", "—")))
        tbl.add_row("自动确认", "是" if d.get("auto_yes") else "否")
        tbl.add_row("快照粒度", str(d.get("snapshot_granularity",
                                        "turn")))
        self.console.print(tbl)

    def _profile_delete(self, name: str) -> None:
        from .ui.confirm import confirm_yes_no
        if not profile_path(name).exists():
            self.console.print(f"[err]✗ 找不到画像: {escape(name)}[/]")
            return
        if not self.auto_yes:
            if not confirm_yes_no(
                self.console, f"删除画像 {name}？",
                default_yes=False, danger=True,
                show_dog=True,
            ):
                self.console.print("[dim]已取消。[/]")
                return
        if delete_profile(name):
            if self.active_profile == name:
                self.active_profile = ""
            self.console.print(
                f"[ok]✓ 已删除画像[/] [accent]{escape(name)}[/]")

    # ================================================================== #
    # 后台任务
    # ================================================================== #

    def _cmd_jobs(self) -> None:
        dead = [pid for pid, j in self.bg_jobs.items()
                if j["proc"].poll() is not None]
        for pid in dead:
            self.bg_jobs.pop(pid, None)
        if not self.bg_jobs:
            self.console.print(
                "[dim]没有正在运行的后台任务。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("PID", style="bold", justify="right")
        tbl.add_column("命令")
        tbl.add_column("运行时长", style="dim", justify="right")
        tbl.add_column("日志", style="dim")
        for pid, j in sorted(self.bg_jobs.items()):
            dur = time.time() - j.get("started_at", time.time())
            tbl.add_row(str(pid), escape(j["command"][:60]),
                        f"{int(dur)}s", escape(j["log_file"]))
        self.console.print(tbl)

    def _cmd_kill(self, arg: str) -> None:
        try:
            pid = int(arg.strip())
        except (ValueError, AttributeError):
            self.console.print("[err]✗ 用法：/kill <pid>[/]")
            return
        j = self.bg_jobs.get(pid)
        if not j:
            self.console.print(f"[err]✗ 找不到 PID {pid}[/]")
            return
        proc = j["proc"]
        if proc.poll() is not None:
            self.bg_jobs.pop(pid, None)
            self.console.print(f"[dim]PID {pid} 已自行退出。[/]")
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError as exc:
            self.console.print(
                f"[err]✗ 终止失败: {escape(str(exc))}[/]")
            return
        self.bg_jobs.pop(pid, None)
        self.console.print(f"[ok]✓ 已终止 PID {pid}[/]")

    def _cmd_log(self, arg: str) -> None:
        try:
            pid = int(arg.strip())
        except (ValueError, AttributeError):
            self.console.print("[err]✗ 用法：/log <pid>[/]")
            return
        j = self.bg_jobs.get(pid)
        if not j:
            self.console.print(f"[err]✗ 找不到 PID {pid}[/]")
            return
        try:
            text = Path(j["log_abs"]).read_text(
                encoding="utf-8", errors="replace")
        except OSError as exc:
            self.console.print(
                f"[err]✗ 读取日志失败: {escape(str(exc))}[/]")
            return
        tail = text[-8000:]
        self.console.print(Panel(
            Text(tail or "(空)", style="dim"),
            title=f"[bold]PID {pid} · {escape(j['log_file'])}[/]",
            title_align="left", border_style=DIM_C,
            box=box.ROUNDED, padding=(0, 1), expand=False,
        ))

    def _cmd_todos(self) -> None:
        if not self.todos:
            self.console.print("[dim]暂无任务。[/]")
            return
        tbl = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
        tbl.add_column("ID", style="dim", justify="right")
        tbl.add_column("状态", justify="center")
        tbl.add_column("任务")
        for t in self.todos:
            mark = "[ok]✓[/]" if t.get("done") else "[dim]○[/]"
            text = escape(t["text"])
            if t.get("done"):
                text = f"[dim strike]{text}[/]"
            tbl.add_row(f"#{t['id']}", mark, text)
        self.console.print(tbl)

    # ================================================================== #
    # Cron daemon
    # ================================================================== #

    def _ensure_cron_daemon(self):
        if self._cron_daemon is None:
            from .cron import CronDaemon
            self._cron_daemon = CronDaemon(self)
        if not self._cron_daemon.is_running():
            self._cron_daemon.start()

    def _stop_cron_daemon(self):
        if self._cron_daemon is not None:
            try:
                self._cron_daemon.stop()
            except Exception:
                pass

    # ================================================================== #
    # Plan 模式
    # ================================================================== #

    def _enter_plan_mode(self) -> None:
        self.plan_mode = True
        self.plan_active = False
        self.plan_items = []
        self.console.print("[ok]✓ 已进入计划模式[/]")

    def _exit_plan_mode(self, execute: bool,
                         confirmed_items: list | None = None) -> None:
        self.plan_mode = False
        if not execute:
            self.plan_active = False
            self.plan_items = []
            self.console.print("[dim]已退出计划模式，未执行。[/]")
            return
        items = confirmed_items or self.plan_items
        if not items:
            self.plan_active = False
            self.console.print("[dim]没有可执行的计划项。[/]")
            return
        checklist = "\n".join(f"- [ ] {it}" for it in items)
        self.messages.append({
            "role": "system",
            "content": ("[One Cedric] 用户已确认以下计划，开始执行。"
                        "每完成一项后，在回复里用 `- [x]` 标注该项。\n\n"
                        + checklist),
        })
        self.plan_active = True
        self.plan_items = list(items)
        self.console.print(
            f"[ok]✓ 计划已确认，开始执行[/] [dim]（{len(items)} 项）[/]")

    def _prompt_plan_approval(self) -> str:
        if self.auto_yes:
            self.console.print("  [dim]· auto-yes，已自动批准[/]")
            return "y"
        while True:
            ui.render_plan_prompt(self.console)
            try:
                ans = self.console.input("  [dim]>[/] ")
            except (EOFError, KeyboardInterrupt):
                return "n"
            a = ans.strip().lower()
            if a in ("", "n", "no"):
                return "n"
            if a in ("y", "yes"):
                return "y"
            if a == "e":
                return "e"
            if a == "?":
                self.console.print(
                    "    [ok]y[/] 批准  [err]n[/] 放弃  "
                    "[accent]e[/] 编辑")
                continue

    def _cmd_plan(self, arg: str) -> None:
        arg = arg.strip().lower()
        if arg in ("off", "exit", "stop"):
            self._exit_plan_mode(execute=False)
            return
        if arg in ("on", "start", ""):
            if self.plan_mode:
                self.console.print("[dim]已经在计划模式。[/]")
                return
            self._enter_plan_mode()
            return
        if arg == "show":
            if self.plan_items:
                ui.render_plan_panel(self.console, self.plan_items)
            return
    # ================================================================== #
    # Agent 主循环
    # ================================================================== #

    def agent_turn(self, prompt: str) -> str:
        self._snapshot_taken_this_turn = False
        t0 = time.time()
        self.messages.append({"role": "user", "content": prompt})

        turn_input_chars = sum(
            len(m.get("content") or "") for m in self.messages)
        turn_output_chars = 0
        turn_first_token_at = None
        turn_first_content_at = None

        if self.plan_mode:
            api_messages = (
                [{"role": "system", "content": PLAN_SYSTEM_PROMPT}]
                + self.messages[1:]
            )
        else:
            api_messages = list(self.messages)

        try:
            for _step in range(self.max_steps):
                content_buf: list[str] = []
                reasoning_buf: list[str] = []
                final_content = ""
                final_reasoning = ""
                tool_calls: list = []
                phase = "reasoning"
                last_render = 0.0
                reasoning_frozen = False

                api_messages = self._inject_images(api_messages)

                with Live(ui.get_spinner("_thinking"),
                          console=self.console,
                          refresh_per_second=20,
                          transient=True) as live:
                    for kind, data in self._stream_chat(api_messages):
                        if turn_first_token_at is None:
                            turn_first_token_at = time.time()

                        if kind == "reasoning":
                            reasoning_buf.append(data)
                            if self.show_reasoning and phase == "reasoning":
                                acc = "".join(reasoning_buf)
                                preview = (acc if len(acc) <= 800
                                           else "…" + acc[-800:])
                                live.update(Panel(
                                    Text(preview, style="dim italic"),
                                    title=f"[dim]思考中… {len(acc)} 字[/]",
                                    title_align="left",
                                    border_style=DIM_C,
                                    box=box.ROUNDED,
                                    padding=(0, 1),
                                    expand=False,
                                ))
                        elif kind == "content":
                            if phase == "reasoning":
                                phase = "content"
                                if turn_first_content_at is None:
                                    turn_first_content_at = time.time()
                                if (self.show_reasoning and reasoning_buf
                                        and not reasoning_frozen):
                                    reasoning_frozen = True
                                    acc = "".join(reasoning_buf)
                                    live.console.print(Panel(
                                        Text(acc, style="dim italic"),
                                        title=f"[dim]思考过程（{len(acc)} 字）[/]",
                                        title_align="left",
                                        border_style=DIM_C,
                                        box=box.ROUNDED,
                                        padding=(0, 1),
                                        expand=False,
                                    ))
                            content_buf.append(data)
                            text = "".join(content_buf)
                            now = time.time()
                            if (now - last_render >= 0.12
                                    and text.strip()):
                                last_render = now
                                live.update(Markdown(text,
                                                     code_theme="monokai"))
                        elif kind == "final":
                            final_content = data["content"]
                            final_reasoning = data.get("reasoning", "")
                            tool_calls = data["tool_calls"]

                            if (not final_content.strip()
                                    and final_reasoning.strip()
                                    and not tool_calls
                                    and self._is_deepseek_buggy_model()):
                                final_content = final_reasoning
                                self.console.print(
                                    "  [warn]⚠ 检测到 DeepSeek 答案"
                                    "落在 reasoning_content，"
                                    "已自动恢复为回答[/]")

                            turn_output_chars = (len(final_content)
                                                 + len(final_reasoning))

                            if final_content.strip():
                                live.update(Markdown(final_content,
                                                     code_theme="monokai"))
                            elif final_reasoning.strip():
                                live.update(Panel(
                                    Text(
                                        "模型只输出了思考过程，"
                                        "未生成最终回答。\n"
                                        "可能是 max_tokens 太小，"
                                        "或提示词触发了纯推理。",
                                        style="warn"),
                                    title="[warn]警告[/]",
                                    title_align="left",
                                    border_style=WARN_C,
                                    box=box.ROUNDED,
                                    padding=(0, 1),
                                    expand=False,
                                ))
                            else:
                                live.update(Text(""))

                if (self.show_reasoning and reasoning_buf
                        and not reasoning_frozen and phase == "reasoning"):
                    reasoning_frozen = True
                    acc = "".join(reasoning_buf)
                    self.console.print(Panel(
                        Text(acc, style="dim italic"),
                        title=f"[dim]思考过程（{len(acc)} 字）[/]",
                        title_align="left",
                        border_style=DIM_C,
                        box=box.ROUNDED,
                        padding=(0, 1),
                        expand=False,
                    ))

                assistant_msg: dict = {
                    "role": "assistant", "content": final_content,
                }
                if (final_reasoning and tool_calls
                        and self._is_deepseek_buggy_model()):
                    assistant_msg["reasoning_content"] = final_reasoning
                if tool_calls:
                    normalized = []
                    for i, tc in enumerate(tool_calls):
                        normalized.append({
                            "id": tc["id"] or f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": (tc["function"]["arguments"]
                                              or "{}"),
                            },
                        })
                    assistant_msg["tool_calls"] = normalized
                self.messages.append(assistant_msg)

                if not tool_calls and final_content:
                    recovered = _scan_text_tool_calls(final_content)
                    if recovered:
                        self.console.print(
                            f"  [warn]⚠ 模型把 {len(recovered)} 个"
                            f"工具调用写成了文本，已自动恢复[/]")
                        tool_calls = recovered
                        assistant_msg["tool_calls"] = recovered
                        cleaned = _strip_text_tool_calls(final_content)
                        assistant_msg["content"] = cleaned
                        final_content = cleaned

                if not tool_calls:
                    text = final_content or "(模型返回了空回复)"
                    if self.plan_mode:
                        items = parse_plan_items(text)
                        if items:
                            self.plan_items = items
                            self.console.print()
                            ui.render_plan_panel(self.console, items)
                            action = self._prompt_plan_approval()
                            if action == "n":
                                self._exit_plan_mode(execute=False)
                                return text
                            if action == "e":
                                edited = _open_in_editor(
                                    "\n".join(items), ".md")
                                if edited is not None:
                                    new_items = [
                                        ln.strip()
                                        for ln in edited.splitlines()
                                        if ln.strip()
                                    ]
                                    if new_items:
                                        items = new_items
                                        self.plan_items = items
                                        ui.render_plan_panel(
                                            self.console, items)
                                        if (self._prompt_plan_approval()
                                                != "y"):
                                            self._exit_plan_mode(
                                                execute=False)
                                            return text
                                else:
                                    self._exit_plan_mode(execute=False)
                                    return text
                            self._exit_plan_mode(
                                execute=True, confirmed_items=items)
                            self.messages.append({
                                "role": "user",
                                "content": "（已批准，开始执行计划）",
                            })
                            api_messages = self.messages
                            continue
                        else:
                            self.console.print(
                                "[warn]⚠ 未从回复中解析出计划列表。[/]")
                            return text
                    ui.render_answer_header(self.console)
                    if (text.strip()
                            and text != "(模型返回了空回复)"):
                        self.console.print(
                            Markdown(text, code_theme="monokai"))
                    else:
                        self.console.print(f"[dim]{text}[/]")
                    return text

                if final_content.strip():
                    self.console.print()

                # ====================================================== #
                # 分类工具调用：error / dup / write / readonly
                # ====================================================== #
                seen_calls: set = set()
                tasks: list = []

                for tc in assistant_msg["tool_calls"]:
                    name, args, nerr = prepare_tool_call(tc)

                    if nerr or not name:
                        tasks.append({
                            "tc": tc, "name": "", "args": {},
                            "err": nerr or "无法识别工具名",
                            "kind": "error",
                        })
                        continue

                    call_sig = (
                        name,
                        json.dumps(args, sort_keys=True,
                                   ensure_ascii=False),
                    )
                    if call_sig in seen_calls:
                        tasks.append({
                            "tc": tc, "name": name, "args": args,
                            "err": (f"同一轮里 {name} 参数完全相同，"
                                    f"已跳过重复调用。"),
                            "kind": "dup",
                        })
                        continue
                    seen_calls.add(call_sig)

                    raw_name = (tc.get("function") or {}).get("name", "")
                    if raw_name and raw_name != name:
                        self.messages.append({
                            "role": "system",
                            "content": (f"[One Cedric] 你刚才调用了 "
                                        f"'{raw_name}'，"
                                        f"标准工具名是 '{name}'。"
                                        f"请下次直接使用标准名。"),
                        })

                    has_missing = False
                    for t in self._current_tool_schemas:
                        if t["function"]["name"] == name:
                            req = (t["function"]
                                   .get("parameters", {})
                                   .get("required", []))
                            miss = [
                                r for r in req
                                if r not in args
                                or args[r] in ("", None)
                            ]
                            if miss:
                                has_missing = True
                                tasks.append({
                                    "tc": tc, "name": name,
                                    "args": args,
                                    "err": (f"缺少必需参数 "
                                            f"{', '.join(miss)}。"
                                            f"请重新调用 {name} 并补全。"),
                                    "kind": "error",
                                })
                            break
                    if has_missing:
                        continue

                    tc["function"]["name"] = name
                    tc["function"]["arguments"] = json.dumps(
                        args, ensure_ascii=False)

                    is_write = self._classify_is_write(name, args)

                    tasks.append({
                        "tc": tc, "name": name, "args": args,
                        "err": "",
                        "kind": "write" if is_write else "readonly",
                    })

                # 分批：连续 readonly 合批
                batches: list = []
                for t in tasks:
                    if t["kind"] == "readonly":
                        if (batches
                                and batches[-1]["kind"] == "readonly"):
                            batches[-1]["items"].append(t)
                        else:
                            batches.append({
                                "kind": "readonly",
                                "items": [t],
                            })
                    else:
                        batches.append({
                            "kind": t["kind"], "items": [t],
                        })

                # ====================================================== #
                # 执行各批次
                # ====================================================== #
                from concurrent.futures import (
                    ThreadPoolExecutor, as_completed,
                )

                for batch in batches:
                    kind = batch["kind"]
                    items = batch["items"]

                    if kind == "error":
                        for t in items:
                            result = f"ERROR: {t['err']}"
                            self.console.print(
                                f"  [err]✗ {escape(result)}[/]")
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": t["tc"]["id"],
                                "content": result,
                            })
                        continue

                    if kind == "dup":
                        for t in items:
                            result = f"ERROR: {t['err']}"
                            self.console.print(
                                f"  [warn]⊘ {escape(result)}[/]")
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": t["tc"]["id"],
                                "content": result,
                            })
                        continue

                    if kind == "write":
                        for t in items:
                            self._dispatch_write_single(
                                t["tc"], t["name"], t["args"])
                        continue

                    # readonly 批次
                    if not items:
                        continue

                    # 单工具：走原路径，视觉更简洁
                    if len(items) == 1:
                        t = items[0]
                        tc = t["tc"]
                        name = t["name"]
                        args = t["args"]
                        target = ui.format_tool_call(
                            name, args, self._shorten)
                        self._bump_tool(name)
                        self._stream_tool_start(tc, name, args)

                        cached = None
                        if name in CACHEABLE_TOOLS:
                            cached = self.tool_cache.get(
                                self.root, name, args)

                        if cached is not None:
                            result = cached
                            self._log_tool(
                                name, target, result,
                                call_id=tc.get("id", ""),
                            )
                        else:
                            with ui.ToolStatus(
                                    self.console, name, target):
                                result = dispatch_tool(
                                    name, args, self.root)
                            self._log_tool(
                                name, target, result,
                                call_id=tc.get("id", ""),
                            )
                            if name in CACHEABLE_TOOLS:
                                self.tool_cache.put(
                                    self.root, name, args, result)

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                        continue

                    # 多工具：并行
                    try:
                        from .ui.progress import ProgressMatrix
                    except Exception:
                        ProgressMatrix = None

                    if ProgressMatrix is None:
                        # 降级：串行
                        for t in items:
                            tc = t["tc"]
                            name = t["name"]
                            args = t["args"]
                            target = ui.format_tool_call(
                                name, args, self._shorten)
                            self._bump_tool(name)
                            self._stream_tool_start(tc, name, args)
                            with ui.ToolStatus(
                                    self.console, name, target):
                                result = dispatch_tool(
                                    name, args, self.root)
                            self._log_tool(
                                name, target, result,
                                call_id=tc.get("id", ""),
                            )
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result,
                            })
                        continue

                    with ProgressMatrix(
                            self.console,
                            f"执行只读工具 ({len(items)})") as pm:
                        tid_map: dict = {}
                        for t in items:
                            target = ui.format_tool_call(
                                t["name"], t["args"], self._shorten)
                            tid = pm.add(t["name"], target)
                            tid_map[t["tc"]["id"]] = (tid, t)

                        def _run_one(t, tid):
                            n = t["name"]
                            a = t["args"]
                            self._stream_tool_start(t["tc"], n, a)
                            pm.update(tid, progress=0.1)
                            cached = None
                            if n in CACHEABLE_TOOLS:
                                cached = self.tool_cache.get(
                                    self.root, n, a)
                            if cached is not None:
                                result = cached
                            else:
                                try:
                                    result = dispatch_tool(
                                        n, a, self.root)
                                except Exception as exc:
                                    result = (f"ERROR: "
                                              f"{type(exc).__name__}: "
                                              f"{exc}")
                                if (n in CACHEABLE_TOOLS
                                        and not result.startswith(
                                            "ERROR")):
                                    try:
                                        self.tool_cache.put(
                                            self.root, n, a, result)
                                    except Exception:
                                        pass
                            pm.update(tid, progress=0.9)
                            return result

                        results_by_id: dict = {}
                        with ThreadPoolExecutor(
                                max_workers=min(4, len(items))) as pool:
                            futures = {}
                            for t in items:
                                tc_id = t["tc"]["id"]
                                tid, _ = tid_map[tc_id]
                                fut = pool.submit(_run_one, t, tid)
                                futures[fut] = tc_id

                            for fut in as_completed(futures):
                                tc_id = futures[fut]
                                tid, t = tid_map[tc_id]
                                try:
                                    result = fut.result()
                                except Exception as exc:
                                    result = (f"ERROR: "
                                              f"{type(exc).__name__}: "
                                              f"{exc}")
                                self._bump_tool(t["name"])
                                summary, stat = ui.summarize_result(
                                    t["name"], result)
                                pm.done(tid, summary[:30], stat)
                                results_by_id[tc_id] = (result, t)

                        for t in items:
                            tc_id = t["tc"]["id"]
                            if tc_id in results_by_id:
                                result, task = results_by_id[tc_id]
                            else:
                                result = "ERROR: 任务未完成"
                                task = t
                            target = ui.format_tool_call(
                                task["name"], task["args"], self._shorten)
                            self._log_tool(
                                task["name"], target, result,
                                call_id=tc_id,
                            )
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": result,
                            })

                self.console.print()
                api_messages = (
                    [{"role": "system",
                      "content": PLAN_SYSTEM_PROMPT}]
                    + self.messages[1:]
                    if self.plan_mode
                    else list(self.messages)
                )

            return "(已达到最大工具调用步数，请简化问题后重试)"
        finally:
            elapsed = time.time() - t0
            self._bump("turns")
            self.stats.setdefault("turn_durations", []).append(
                round(elapsed, 2))
            if len(self.stats["turn_durations"]) > 100:
                self.stats["turn_durations"] = (
                    self.stats["turn_durations"][-100:])
            try:
                self._print_turn_metrics(
                    elapsed=elapsed,
                    input_chars=turn_input_chars,
                    output_chars=turn_output_chars,
                    first_token_at=turn_first_token_at,
                    first_content_at=turn_first_content_at,
                    t_start=t0,
                )
            except Exception:
                pass
            self._maybe_generate_title()
            self._save_session()

    def _classify_is_write(self, name: str, args: dict) -> bool:
        """判断工具调用是否写操作。"""
        from .integrations import is_external_tool, is_mutating_tool
        if is_external_tool(name):
            return is_mutating_tool(name)
        WRITE_NAMES = set(WRITE_TOOLS) | {
            "apply_patch", "file_ops", "find_replace",
            "docx", "pdf", "pptx", "excel",
            "sysop", "bash", "bash_bg", "git", "docker",
            "sqlite", "archive", "clipboard", "todo",
            "screen_capture", "screen_info",
            "mouse_action", "keyboard_action", "window_action",
            "email_send", "email_reply", "email_mark",
            "email_move", "email_delete",
            "email_download_attachment",
            "file_attrs", "python_exec",
            "qrcode_styled", "qrcode_batch", "qrcode_wifi",
            "qrcode_vcard", "qrcode_email", "qrcode_sms",
            "qrcode_geo",
            "video_convert", "video_clip", "video_extract_audio",
            "video_thumbnail", "video_to_gif", "video_compress",
            "video_merge", "audio_convert", "audio_clip",
            "audio_volume", "audio_concat",
            "pdf_watermark", "pdf_compress", "pdf_extract_images",
            "pdf_rotate", "pdf_add_page_numbers", "pdf_metadata",
            "compose_up", "compose_down", "compose_restart",
            "compose_exec", "k8s_apply", "k8s_delete",
            "k8s_scale", "k8s_exec",
            "memory_remember", "memory_forget",
            "cron_add", "cron_remove", "cron_enable",
            "spawn_agent", "ask_user", "multi_review",
            "dream_run", "notify", "notify_actions",
            "pkg_install", "pkg_uninstall",
            "download", "cost_export",
            "image_process", "qrcode_generate",
            "symmetric_encrypt", "symmetric_decrypt",
            "rsa_generate_keypair", "rsa_encrypt", "rsa_decrypt",
        }
        if name not in WRITE_NAMES:
            return False
        # 只读 op 例外
        if name == "image_process" \
                and str(args.get("op", "")).lower() == "info":
            return False
        if name == "pdf_metadata" \
                and str(args.get("op", "get")).lower() == "get":
            return False
        if name == "file_attrs" \
                and str(args.get("op", "")).lower() in ("get", "bulk"):
            return False
        if name in ("postgres_query", "mysql_query"):
            try:
                from .tools.database import sql_is_write
                if not sql_is_write(str(args.get("query", "")))[0]:
                    return False
            except Exception:
                pass
        return True

    # ================================================================== #
    # 无 UI（Gateway 用）
    # ================================================================== #

    def ask_no_ui(self, prompt: str,
                   auto_approve: bool = False) -> dict:
        from io import StringIO
        from rich.console import Console as _Console

        old_console = self.console
        old_auto_yes = self.auto_yes
        old_write = self._ask_write_action
        old_shell = self._ask_shell_action
        old_log = self._log_tool

        buf = StringIO()
        self.console = _Console(
            file=buf, width=120, no_color=True,
            force_terminal=False, soft_wrap=True)
        self.auto_yes = auto_approve

        tool_calls: list[dict] = []

        def _wrap_write(name):
            if name == "python_exec" and self._stream_hook is not None:
                return old_write(name)
            return "y" if auto_approve else "n"

        def _wrap_shell(cmd, base, level, warn=""):
            if level == "blocked":
                return "no"
            if level == "whitelist":
                return "yes"
            return "yes" if auto_approve else "no"

        def _wrap_log(name, target, result):
            summary = (result.splitlines()[0][:200]
                       if result else "")
            tool_calls.append({
                "name": name, "target": target, "summary": summary,
                "status": ("error"
                           if result and result.startswith("ERROR")
                           else "ok"),
            })
            try:
                old_log(name, target, result)
            except Exception:
                pass

        self._ask_write_action = _wrap_write
        self._ask_shell_action = _wrap_shell
        self._log_tool = _wrap_log

        answer = ""
        try:
            answer = self.agent_turn(prompt)
        except Exception as exc:
            answer = f"ERROR: {exc}"
        finally:
            self.console = old_console
            self.auto_yes = old_auto_yes
            self._ask_write_action = old_write
            self._ask_shell_action = old_shell
            self._log_tool = old_log

        log = buf.getvalue()
        if len(log) > 8000:
            log = "…（截断）\n" + log[-8000:]

        return {
            "answer": answer,
            "tool_calls": tool_calls,
            "console_log": log,
        }

    def ask_no_ui_stream(self, prompt: str,
                          auto_approve: bool = False):
        import queue
        import threading

        q: "queue.Queue" = queue.Queue()

        def _hook(evt: dict):
            try:
                q.put(evt)
            except Exception:
                pass

        old_hook = self._stream_hook
        self._stream_hook = _hook

        result_box: dict = {}

        def _runner():
            t0 = time.time()
            try:
                r = self.ask_no_ui(prompt, auto_approve=auto_approve)
                result_box["answer"] = r.get("answer", "")
                result_box["duration"] = round(time.time() - t0, 2)
            except Exception as exc:
                result_box["error"] = str(exc)
            finally:
                q.put(None)

        t = threading.Thread(target=_runner, daemon=True,
                             name="cedric-ask")
        t.start()

        try:
            while True:
                evt = q.get()
                if evt is None:
                    break
                yield evt
        finally:
            self._stream_hook = old_hook

        if "error" in result_box:
            yield {"type": "error",
                   "message": result_box["error"]}
        else:
            yield {
                "type": "done",
                "answer": result_box.get("answer", ""),
                "duration": result_box.get("duration", 0.0),
            }
    # ================================================================== #
    # HELP
    # ================================================================== #

    HELP_ZH = (
        f"[bold {BRAND}]可用命令[/]\n"
        f"  [bold {BRAND}]/help[/]                显示帮助\n"
        f"  [bold {BRAND}]/menu[/]                返回主菜单\n"
        f"  [bold {BRAND}]/lang[/] [dim][zh|en][/]     切换界面语言\n"
        f"  [bold {BRAND}]/clear[/]               清空对话历史\n"
        f"  [bold {BRAND}]/new[/]                 开启新会话\n"
        f"  [bold {BRAND}]/sessions[/]            会话管理界面\n"
        f"  [bold {BRAND}]/resume[/] [dim]<ID>[/]       恢复某个会话\n"
        f"  [bold {BRAND}]/save-as[/] [dim]<名>[/]      给会话命名\n"
        f"  [bold {BRAND}]/export[/] [dim]<路径>[/]     导出会话为 Markdown\n"
        f"  [bold {BRAND}]/model[/] [dim][名][/]        模型管理界面\n"
        f"  [bold {BRAND}]/think[/] [dim][档位][/]      思考模式\n"
        f"  [bold {BRAND}]/reasoning[/] [dim][on|off][/]   显示/隐藏推理过程\n"
        f"  [bold {BRAND}]/mode[/] [dim][模式][/]       访问模式\n"
        f"  [bold {BRAND}]/yes[/]                 切换自动确认写操作\n"
        f"  [bold {BRAND}]/shell[/] [dim][on|off|clear][/]   任意命令开关\n"
        f"  [bold {BRAND}]/computer[/] [dim][on|off][/]   切换 computer use\n"
        f"  [bold {BRAND}]/tools[/]               工具管理界面\n"
        f"  [bold {BRAND}]/allow[/]               查看 bash 白名单\n"
        f"  [bold {BRAND}]/plan[/] [dim][on|off|show][/]  计划模式\n"
        f"  [bold {BRAND}]/todos[/]              查看任务清单\n"
        f"  [bold {BRAND}]/history[/]             文件修改历史\n"
        f"  [bold {BRAND}]/diff[/] [dim][n][/]         查看第 n 条修改的 diff\n"
        f"  [bold {BRAND}]/tag[/] [dim]<n> <文本>[/]    打标签\n"
        f"  [bold {BRAND}]/untag[/] [dim]<n>[/]         清除标签\n"
        f"  [bold {BRAND}]/undo[/]                撤销最近一次文件修改\n"
        f"  [bold {BRAND}]/rollback[/]            回滚到 git 快照\n"
        f"  [bold {BRAND}]/snapshots[/]           查看 git 快照列表\n"
        f"  [bold {BRAND}]/replay[/] [dim]<n>[/]        回放到第 n 轮提问之前\n"
        f"  [bold {BRAND}]/stats[/]               会话统计\n"
        f"  [bold {BRAND}]/audit[/] [dim][all|export|csv|clear][/]  审计日志\n"
        f"  [bold {BRAND}]/cache[/] [dim][clear][/]     查看或清空工具缓存\n"
        f"  [bold {BRAND}]/compact[/] [dim][n][/]       压缩历史\n"
        f"  [bold {BRAND}]/config[/] / [bold {BRAND}]/save-config[/] [dim][global|project][/]\n"
        f"  [bold {BRAND}]/profile[/] [dim][save|load|show|delete] <名>[/]  工作画像\n"
        f"  [bold {BRAND}]/jobs[/] [dim]| /log <pid> | /kill <pid>[/]   后台任务\n"
        f"  [bold {BRAND}]/amap-key[/] [dim][key][/]    设置高德地图 API Key\n"
        f"  [bold {BRAND}]/email[/] [dim][reload][/]     邮箱账号状态\n"
        f"  [bold {BRAND}]/email-key[/] [dim]<acc> <pwd>[/]  临时设置邮箱密码\n"
        f"  [bold {BRAND}]/office-check[/]        检查办公文档依赖\n"
        f"  [bold {BRAND}]/agent[/] [dim]<任务> [--mode explore|code|plan][/]  派生子 agent\n"
        f"  [bold {BRAND}]/review[/] [dim]<file>[/]      多 agent 代码审查\n"
        f"  [bold {BRAND}]/mem[/] [dim][list|add|rm|search|batch|clear][/]  长期记忆\n"
        f"  [bold {BRAND}]/cron[/] [dim][list|add|rm|enable|disable|run|log|start|stop|batch][/]  定时任务\n"
        f"  [bold {BRAND}]/dream[/] [dim][run|list|read|stats|cron][/]  梦境回顾\n"
        f"  [bold {BRAND}]/asks[/] [dim][export [md|json|csv]|clear][/]  问答历史\n"
        f"  [bold {BRAND}]/pricing[/] [dim][list|grouped|set|rm|import|preset|show|stats|export|import-json][/]  模型价格\n"
        f"  [bold {BRAND}]/cost[/] [dim][today|week|month|all|chart|hourly|anomaly|forecast|export|clear][/]  成本\n"
        f"  [bold {BRAND}]/budget[/] [dim][show|set <period> <amt>|clear|reset][/]  预算\n"
        f"  [bold {BRAND}]/dog[/] [dim][show|reload|edit|export|preview][/]  小狗帧配置\n"
        f"  [bold {BRAND}]/exit[/] [dim]/q[/]          退出\n"
        f"\n[dim]· 输入 [/][accent]@文件路径[/][dim] 可自动加载文件到上下文[/]\n"
        f"[dim]   [/][accent]@README.md[/][dim]               读整个文件[/]\n"
        f"[dim]   [/][accent]@src/main.py#L10-L20[/][dim]     读第 10-20 行[/]\n"
        f"[dim]   [/][accent]@src/[/][dim]                    列目录[/]\n"
        f"[dim]   [/][accent]@src/**[/][dim]                  递归列目录[/]\n"
    )

    HELP_EN = (
        f"[bold {BRAND}]Commands[/]\n"
        f"  [bold {BRAND}]/help[/]                Show this help\n"
        f"  [bold {BRAND}]/menu[/]                Back to main menu\n"
        f"  [bold {BRAND}]/lang[/] [dim][zh|en][/]     Switch language\n"
        f"  [bold {BRAND}]/clear[/]               Clear conversation\n"
        f"  [bold {BRAND}]/new[/]                 New session\n"
        f"  [bold {BRAND}]/sessions[/]            Session manager\n"
        f"  [bold {BRAND}]/resume[/] [dim]<ID>[/]       Resume session\n"
        f"  [bold {BRAND}]/save-as[/] [dim]<name>[/]    Name this session\n"
        f"  [bold {BRAND}]/export[/] [dim]<path>[/]     Export to Markdown\n"
        f"  [bold {BRAND}]/model[/] [dim][name][/]      Model manager\n"
        f"  [bold {BRAND}]/think[/] [dim][level][/]     Think level\n"
        f"  [bold {BRAND}]/reasoning[/] [dim][on|off][/]   Show reasoning\n"
        f"  [bold {BRAND}]/mode[/] [dim][mode][/]       Access mode\n"
        f"  [bold {BRAND}]/yes[/]                 Toggle auto-confirm\n"
        f"  [bold {BRAND}]/shell[/] [dim][on|off|clear][/]   Arbitrary shell\n"
        f"  [bold {BRAND}]/computer[/] [dim][on|off][/]   Computer use\n"
        f"  [bold {BRAND}]/tools[/]               Tool manager\n"
        f"  [bold {BRAND}]/allow[/]               Show bash allowlist\n"
        f"  [bold {BRAND}]/plan[/] [dim][on|off|show][/]  Plan mode\n"
        f"  [bold {BRAND}]/todos[/]              Task list\n"
        f"  [bold {BRAND}]/history[/]             File change history\n"
        f"  [bold {BRAND}]/diff[/] [dim][n][/]         Show diff for entry n\n"
        f"  [bold {BRAND}]/tag[/] [dim]<n> <text>[/]    Tag entry n\n"
        f"  [bold {BRAND}]/untag[/] [dim]<n>[/]         Clear tag\n"
        f"  [bold {BRAND}]/undo[/]                Undo last file change\n"
        f"  [bold {BRAND}]/rollback[/]            Roll back to snapshot\n"
        f"  [bold {BRAND}]/snapshots[/]           List git snapshots\n"
        f"  [bold {BRAND}]/replay[/] [dim]<n>[/]        Replay up to turn n\n"
        f"  [bold {BRAND}]/stats[/]               Session stats\n"
        f"  [bold {BRAND}]/audit[/] [dim][all|export|csv|clear][/]  Audit log\n"
        f"  [bold {BRAND}]/cache[/] [dim][clear][/]     Tool cache\n"
        f"  [bold {BRAND}]/compact[/] [dim][n][/]       Compact history\n"
        f"  [bold {BRAND}]/config[/] / [bold {BRAND}]/save-config[/] [dim][global|project][/]\n"
        f"  [bold {BRAND}]/profile[/] [dim][save|load|show|delete] <name>[/]\n"
        f"  [bold {BRAND}]/jobs[/] [dim]| /log <pid> | /kill <pid>[/]   Background jobs\n"
        f"  [bold {BRAND}]/agent[/] [dim]<task> [--mode explore|code|plan][/]  Sub-agent\n"
        f"  [bold {BRAND}]/review[/] [dim]<file>[/]      Multi-agent review\n"
        f"  [bold {BRAND}]/mem[/] [dim][list|add|rm|search|batch|clear][/]\n"
        f"  [bold {BRAND}]/cron[/] [dim][list|add|rm|enable|disable|run|log|start|stop|batch][/]\n"
        f"  [bold {BRAND}]/dream[/] [dim][run|list|read|stats|cron][/]\n"
        f"  [bold {BRAND}]/asks[/] [dim][export [md|json|csv]|clear][/]\n"
        f"  [bold {BRAND}]/pricing[/] [dim][list|grouped|set|rm|import|preset|show|stats|export|import-json][/]\n"
        f"  [bold {BRAND}]/cost[/] [dim][today|week|month|all|chart|hourly|anomaly|forecast|export|clear][/]\n"
        f"  [bold {BRAND}]/budget[/] [dim][show|set <period> <amt>|clear|reset][/]\n"
        f"  [bold {BRAND}]/dog[/] [dim][show|reload|edit|export|preview][/]\n"
        f"  [bold {BRAND}]/exit[/] [dim]/q[/]          Quit\n"
        f"\n[dim]· Type [/][accent]@path[/][dim] to attach files[/]\n"
    )

    @staticmethod
    def _help_text() -> str:
        from .i18n import get_lang
        return (OneCedric.HELP_EN if get_lang() == "en"
                else OneCedric.HELP_ZH)

    # ================================================================== #
    # 会话导出
    # ================================================================== #

    def _export_session(self, target: str | None) -> None:
        if target:
            out = Path(target).expanduser()
            if not out.is_absolute():
                out = Path.cwd() / out
        else:
            out = Path.cwd() / f"session-{self.session_id}.md"
        md = self._render_session_markdown()
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(md, encoding="utf-8")
        except OSError as exc:
            self.console.print(
                f"[err]✗ 导出失败: {escape(str(exc))}[/]")
            return
        self.console.print(
            f"[ok]✓ 已导出会话到[/] "
            f"[path]{escape(str(out))}[/]")

    def _render_session_markdown(self) -> str:
        L: list[str] = []
        header_title = self.session_title or "（未命名）"
        L.append(f"# One Cedric 会话 · {header_title}")
        L.append("")
        L.append(f"- **会话 ID**：`{self.session_id}`")
        L.append(
            f"- **创建时间**："
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.session_created_at))}")
        L.append(f"- **模型**：`{self.model}`")
        L.append(f"- **工作目录**：`{self.root}`")
        L.append(f"- **消息数**：{len(self.messages) - 1}")
        L.append(f"- **导出时间**："
                 f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
        L.append("")
        L.append("---")
        L.append("")
        for msg in self.messages:
            role = msg.get("role")
            if role == "system":
                continue
            if role == "user":
                L.append("## 👤 用户")
                L.append("")
                L.append(str(msg.get("content", "")))
                L.append("")
            elif role == "assistant":
                content = (msg.get("content") or "").strip()
                tool_calls = msg.get("tool_calls") or []
                if content or not tool_calls:
                    L.append("## 🤖 助手")
                    L.append("")
                    L.append(content or "_(空)_")
                    L.append("")
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "?")
                    raw = fn.get("arguments", "{}")
                    try:
                        pretty = json.dumps(
                            json.loads(raw),
                            ensure_ascii=False, indent=2)
                    except (json.JSONDecodeError, TypeError):
                        pretty = str(raw)
                    L.append(f"### ⚙ `{name}`")
                    L.append("")
                    L.append("<details><summary>参数</summary>")
                    L.append("")
                    L.append("```json")
                    L.append(pretty[:4000])
                    L.append("```")
                    L.append("")
                    L.append("</details>")
                    L.append("")
            elif role == "tool":
                content = str(msg.get("content", ""))
                first = content.splitlines()[0] if content else ""
                L.append(
                    f"<details><summary>工具结果 · "
                    f"{first[:80] if first else '(空)'}</summary>")
                L.append("")
                L.append("```")
                L.append(content[:6000])
                L.append("```")
                L.append("")
                L.append("</details>")
                L.append("")
        if self.undo_stack:
            L.append("---")
            L.append("")
            L.append("## 📚 文件修改记录")
            L.append("")
            L.append("| # | 时间 | 工具 | 文件 | 标签 |")
            L.append("|---|------|------|------|------|")
            for i, rec in enumerate(self.undo_stack, 1):
                t = time.strftime(
                    "%H:%M:%S", time.localtime(rec.get("ts", 0)))
                tag = (rec.get("tag") or "").replace("|", "\\|")
                L.append(f"| {i} | {t} | `{rec.get('tool', '')}` | "
                         f"`{rec.get('rel', '')}` | {tag} |")
            L.append("")
        return "\n".join(L)

    def ask_once(self, prompt: str) -> None:
        try:
            self.agent_turn(prompt)
        except SystemExit as exc:
            self.console.print(f"[err]{escape(str(exc))}[/]")

    # ================================================================== #
    # REPL 主循环
    # ================================================================== #

    def run(self, in_menu: bool = False) -> None:
        from .ui.input_box import ask_with_box
        from .pricing import compute_cost

        self.banner()
        while True:
            ctx_used = _estimate_tokens(self.messages)
            ctx_max = getattr(self, "context_limit", 128000)
            total_in = self.stats.get("total_input_tokens", 0)
            total_out = self.stats.get("total_output_tokens", 0)
            cached_tok = self.stats.get("total_cached_tokens", 0)
            cost = compute_cost(self.model, total_in, total_out,
                                 cached_tok)
            turns = self.stats.get("turns", 0)
            steps = sum(self.stats.get("tool_calls", {}).values())
            dog_state = ("confirm" if self._pending_confirm
                         else "idle")
            try:
                line = ask_with_box(
                    self.console,
                    state=dog_state, model=self.model,
                    turn=turns, steps=steps,
                    ctx_used=ctx_used, ctx_max=ctx_max,
                    cost=cost,
                    cached_tok=cached_tok,
                    total_in=total_in, total_out=total_out,
                ).strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]再见！[/]")
                return

            if not line:
                continue

            # ── 退出 ──
            if line in ("/exit", "/quit", "/q"):
                if self.bg_jobs:
                    alive = [
                        pid for pid, j in self.bg_jobs.items()
                        if j["proc"].poll() is None
                    ]
                    if alive:
                        self.console.print(
                            f"[warn]⚠ 仍有 {len(alive)} 个"
                            f"后台任务在运行[/]")
                self._stop_cron_daemon()
                self._save_session()
                if in_menu:
                    return
                self.console.print("[dim]再见！[/]")
                return

            # ── 返回主菜单 ──
            if line in ("/menu", "/back"):
                self._save_session()
                return

            # ── /help ──
            if line == "/help":
                self.console.print(self._help_text())
                continue

            # ── /clear ──
            if line == "/clear":
                self.messages = [self.system_msg]
                self.console.print("[dim]已清空对话历史。[/]")
                self._save_session()
                continue

            # ── /new ──
            if line == "/new":
                self._new_session()
                continue

            # ── /sessions ──
            if line == "/sessions":
                try:
                    from .ui.screens.sessions import run_sessions_screen
                    run_sessions_screen(self.console, self)
                except Exception as exc:
                    self.console.print(
                        f"[err]✗ 会话界面失败: {escape(str(exc))}[/]")
                continue

            # ── /resume ──
            if line.startswith("/resume"):
                parts = line.split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    self.console.print(
                        "[dim]用法：/resume <ID 或 标题>[/]")
                    continue
                self._do_resume(parts[1].strip())
                continue

            # ── /save-as ──
            if line.startswith("/save-as"):
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    self.console.print(
                        "[dim]用法：/save-as <名称>[/]")
                    continue
                self._do_save_as(parts[1])
                continue

            # ── /export ──
            if line.startswith("/export"):
                parts = line.split(maxsplit=1)
                target = parts[1].strip() if len(parts) == 2 else None
                self._export_session(target)
                continue

            # ── /model ──
            if line == "/model" or line == "/models":
                try:
                    from .ui.screens.models import run_models_screen
                    run_models_screen(self.console, self)
                    self.banner()
                except Exception as exc:
                    self.console.print(
                        f"[err]✗ 模型界面失败: {escape(str(exc))}[/]")
                continue
            if line.startswith("/model "):
                v = line[len("/model "):].strip()
                if v:
                    self.model = v
                    self.messages = [self.system_msg]
                    self.console.print(
                        f"[dim]已切换模型：[/]"
                        f"[accent]{escape(self.model)}[/]")
                    self._save_session()
                continue

            # ── /think ──
            if line.startswith("/think"):
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    cur = self.think_level
                    desc = THINK_LEVEL_DESC.get(cur, "")
                    self.console.print(
                        f"[dim]当前思考模式：[/][accent]{cur}[/]"
                        f"  [dim]（{desc}）[/]")
                    self.console.print(
                        "[dim]可选项：[/]"
                        + "  ".join(
                            f"[accent]{l}[/]" for l in THINK_LEVELS))
                    continue
                arg = parts[1].strip().lower()
                if arg not in THINK_LEVELS:
                    self.console.print(
                        f"[err]✗ 未知档位: {escape(arg)}[/]")
                    continue
                self.think_level = arg
                self.console.print(
                    f"[ok]✓ 思考模式：[/][accent]{arg}[/]")
                continue

            # ── /reasoning ──
            if line.startswith("/reasoning"):
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    self.show_reasoning = not self.show_reasoning
                else:
                    arg = parts[1].strip().lower()
                    if arg in ("on", "true", "1", "yes"):
                        self.show_reasoning = True
                    elif arg in ("off", "false", "0", "no"):
                        self.show_reasoning = False
                state = "[ok]开启[/]" if self.show_reasoning \
                    else "[dim]关闭[/]"
                self.console.print(
                    f"[dim]显示思考过程：{state}")
                continue

            # ── /mode ──
            if line.startswith("/mode"):
                from .tools.sandbox import set_access_mode
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    cur = self.access_mode
                    desc = ACCESS_MODE_DESC.get(cur, "")
                    self.console.print(
                        f"[dim]当前访问模式：[/][accent]{cur}[/]"
                        f"  [dim]（{desc}）[/]")
                    for m in ACCESS_MODES:
                        self.console.print(
                            f"  [accent]{m:<14}[/] "
                            f"[dim]{ACCESS_MODE_DESC[m]}[/]")
                    continue
                arg = parts[1].strip().lower()
                arg = ACCESS_MODE_ALIASES.get(arg, arg)
                if arg not in ACCESS_MODES:
                    self.console.print(
                        f"[err]✗ 未知模式: {escape(arg)}[/]")
                    continue
                self.access_mode = arg
                set_access_mode(arg)
                self.config.setdefault("default", {})["mode"] = arg
                self.console.print(
                    f"[ok]✓ 访问模式：[/][accent]{arg}[/]")
                self.banner()
                continue

            # ── /yes ──
            if line == "/yes":
                self.auto_yes = not self.auto_yes
                self.console.print(
                    f"[dim]自动确认写操作："
                    f"{'开启' if self.auto_yes else '关闭'}[/]")
                continue

            # ── /shell ──
            if line.startswith("/shell"):
                parts = line.split(maxsplit=1)
                arg = parts[1].strip().lower() if len(parts) == 2 else ""
                if arg in ("on", "enable"):
                    self.allow_arbitrary_shell = True
                    self.console.print(
                        "[ok]✓ 任意 shell 命令：开启[/]")
                elif arg in ("off", "disable"):
                    self.allow_arbitrary_shell = False
                    self.console.print(
                        "[dim]任意 shell 命令：关闭[/]")
                elif arg == "clear":
                    n = len(self.session_allowed_cmds)
                    self.session_allowed_cmds.clear()
                    self.console.print(
                        f"[ok]✓ 已清除 {n} 条会话允许命令[/]")
                else:
                    state = ("[ok]开启[/]"
                             if self.allow_arbitrary_shell
                             else "[dim]关闭[/]")
                    self.console.print(
                        f"[dim]任意 shell 命令：{state}[/]")
                continue

            # ── /computer ──
            if line.startswith("/computer"):
                parts = line.split(maxsplit=1)
                arg = parts[1].strip().lower() if len(parts) == 2 else ""
                if arg in ("on", "enable"):
                    self._computer_policy.enabled = True
                    self.console.print(
                        "[ok]✓ Computer use 已开启[/]")
                elif arg in ("off", "disable"):
                    self._computer_policy.enabled = False
                    self.console.print(
                        "[dim]Computer use 已关闭[/]")
                else:
                    state = ("[ok]开启[/]"
                             if getattr(self._computer_policy,
                                        "enabled", False)
                             else "[dim]关闭[/]")
                    self.console.print(
                        f"[dim]Computer use 当前：{state}[/]")
                continue

            # ── /tools ──
            if line == "/tools":
                try:
                    from .ui.screens.tools import run_tools_screen
                    run_tools_screen(self.console, self)
                except Exception as exc:
                    self.console.print(
                        f"[err]✗ 工具界面失败: {escape(str(exc))}[/]")
                continue

            # ── /allow ──
            if line == "/allow":
                ui.allow_table(self.console)
                continue

            # ── /plan ──
            if line.startswith("/plan"):
                parts = line.split(maxsplit=1)
                self._cmd_plan(parts[1] if len(parts) == 2 else "")
                continue

            # ── /todos ──
            if line == "/todos":
                self._cmd_todos()
                continue

            # ── /history ──
            if line == "/history":
                self._print_history()
                continue

            # ── /diff ──
            if line.startswith("/diff"):
                parts = line.split(maxsplit=1)
                self._do_diff(parts[1] if len(parts) == 2 else "")
                continue

            # ── /tag ──
            if line.startswith("/tag"):
                parts = line.split(maxsplit=1)
                self._cmd_tag(parts[1] if len(parts) == 2 else "")
                continue

            # ── /untag ──
            if line.startswith("/untag"):
                parts = line.split(maxsplit=1)
                self._cmd_untag(parts[1] if len(parts) == 2 else "")
                continue

            # ── /undo ──
            if line == "/undo":
                self._do_undo()
                self._save_session()
                continue

            # ── /rollback ──
            if line == "/rollback":
                self._do_rollback()
                self._save_session()
                continue

            # ── /snapshots ──
            if line == "/snapshots":
                self._print_snapshots()
                continue

            # ── /replay ──
            if line.startswith("/replay"):
                parts = line.split(maxsplit=1)
                self._do_replay(parts[1] if len(parts) == 2 else "")
                continue

            # ── /stats ──
            if line == "/stats":
                self._print_stats()
                continue

            # ── /audit ──
            if line.startswith("/audit"):
                parts = line.split(maxsplit=1)
                self._cmd_audit(parts[1] if len(parts) == 2 else "")
                continue

            # ── /cache ──
            if line.startswith("/cache"):
                parts = line.split(maxsplit=1)
                self._handle_cache_command(
                    parts[1] if len(parts) == 2 else "")
                continue

            # ── /compact ──
            if line.startswith("/compact"):
                parts = line.split(maxsplit=1)
                arg = parts[1].strip() if len(parts) == 2 else ""
                keep = None
                if arg:
                    try:
                        keep = int(arg)
                    except ValueError:
                        self.console.print(
                            "[err]✗ 参数必须是数字[/]")
                        continue
                self._compact(keep_turns=keep)
                continue

            # ── /config ──
            if line == "/config":
                self._print_config()
                continue

            # ── /save-config ──
            if line.startswith("/save-config"):
                parts = line.split(maxsplit=1)
                scope = (parts[1].strip().lower()
                         if len(parts) == 2 else "global")
                self._save_config(scope)
                continue

            # ── /profile ──
            if line.startswith("/profile"):
                parts = line.split(maxsplit=1)
                self._cmd_profile(
                    parts[1] if len(parts) == 2 else "")
                continue

            # ── /lang ──
            if line.startswith("/lang"):
                from .i18n import set_lang, get_lang, t
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    self.console.print(
                        f"[dim]{t('lang.current')}[/]")
                else:
                    arg = parts[1].strip().lower()
                    if set_lang(arg):
                        self.config.setdefault(
                            "default", {})["language"] = arg
                        self._save_config("global")
                        self.console.print(
                            f"[ok]✓[/] {t('lang.switched')}")
                    else:
                        self.console.print(
                            f"[err]✗ {t('lang.usage')}[/]")
                continue

            # ── /jobs ──
            if line == "/jobs":
                self._cmd_jobs()
                continue

            # ── /log ──
            if line.startswith("/log "):
                parts = line.split(maxsplit=1)
                self._cmd_log(parts[1] if len(parts) == 2 else "")
                continue

            # ── /kill ──
            if line.startswith("/kill "):
                parts = line.split(maxsplit=1)
                self._cmd_kill(parts[1] if len(parts) == 2 else "")
                continue

            # ── /amap-key ──
            if line.startswith("/amap-key"):
                from .tools import amap_key_status, _set_amap_key
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    self.console.print(
                        f"[dim]{amap_key_status()}[/]")
                    continue
                key = parts[1].strip()
                _set_amap_key(key)
                self.config.setdefault("amap", {})["api_key"] = key
                self._save_config("global")
                self.console.print(
                    "[ok]✓ AMAP API Key 已设置[/]")
                continue

            # ── /email-key ──
            if line.startswith("/email-key"):
                from .tools import _set_email_password
                from .tools import _reset_email_accounts
                parts = line.split(maxsplit=2)
                if len(parts) < 3:
                    self.console.print(
                        "[dim]用法：/email-key <account> <password>[/]")
                    continue
                acc_name = parts[1].strip()
                pwd = parts[2].strip()
                _set_email_password(acc_name, pwd)
                _reset_email_accounts()
                self.console.print(
                    f"[ok]✓ 账号 '{escape(acc_name)}' 密码已设置[/]")
                continue

            # ── /email ──
            if line.startswith("/email"):
                from .tools import email_config_status
                from .tools import _reset_email_accounts
                parts = line.split(maxsplit=1)
                if len(parts) == 1:
                    self.console.print(email_config_status())
                    continue
                sub = parts[1].strip().lower()
                if sub in ("reload", "refresh"):
                    _reset_email_accounts()
                    self.console.print(
                        "[ok]✓ 邮箱配置已重新加载[/]")
                else:
                    self.console.print(
                        "[dim]用法：/email [reload][/]")
                continue

            # ── /office-check ──
            if line == "/office-check":
                deps = [
                    ("docx", "python-docx"),
                    ("pptx", "python-pptx"),
                    ("openpyxl", "openpyxl"),
                    ("pypdf", "pypdf"),
                    ("msoffcrypto", "msoffcrypto-tool"),
                    ("pdf2image", "pdf2image"),
                    ("pytesseract", "pytesseract"),
                    ("win32com", "pywin32"),
                ]
                self.console.print("[bold]办公文档依赖检查[/]")
                for mod_name, pip_name in deps:
                    try:
                        __import__(mod_name)
                        self.console.print(
                            f"  [ok]✓[/] {pip_name}")
                    except ImportError:
                        self.console.print(
                            f"  [err]✗[/] {pip_name}  "
                            f"[dim](pip install {pip_name})[/]")
                continue

            # ── /agent ──
            if line.startswith("/agent"):
                parts = line.split(maxsplit=2)
                if len(parts) < 2 or not parts[1].strip():
                    self.console.print(
                        "[dim]用法：/agent <任务描述> "
                        "[--mode explore|code|plan] "
                        "[--steps N] [--timeout S][/]")
                    continue
                rest = (parts[1] if len(parts) == 2
                        else f"{parts[1]} {parts[2]}")
                mode = "explore"
                steps = 6
                timeout = 300
                tokens = rest.split()
                task_tokens = []
                i = 0
                while i < len(tokens):
                    t = tokens[i]
                    if t == "--mode" and i + 1 < len(tokens):
                        mode = tokens[i + 1].lower()
                        i += 2
                        continue
                    if t == "--steps" and i + 1 < len(tokens):
                        try:
                            steps = int(tokens[i + 1])
                        except ValueError:
                            pass
                        i += 2
                        continue
                    if t == "--timeout" and i + 1 < len(tokens):
                        try:
                            timeout = int(tokens[i + 1])
                        except ValueError:
                            pass
                        i += 2
                        continue
                    task_tokens.append(t)
                    i += 1
                task = " ".join(task_tokens).strip()
                if not task:
                    self.console.print(
                        "[err]✗ 任务描述不能为空[/]")
                    continue
                fake_tc = {
                    "id": "slash_agent",
                    "function": {
                        "name": "spawn_agent",
                        "arguments": json.dumps({
                            "task": task, "mode": mode,
                            "max_steps": steps,
                            "timeout": timeout,
                        }, ensure_ascii=False),
                    },
                }
                self._handle_spawn_agent(fake_tc, {
                    "task": task, "mode": mode,
                    "max_steps": steps, "timeout": timeout,
                })
                if (self.messages
                        and self.messages[-1].get("role") == "tool"):
                    last = self.messages[-1]
                    self.console.print()
                    self.console.print(Panel(
                        Text(last.get("content", ""), style=""),
                        title="[bold]子 agent 结果[/]",
                        title_align="left",
                        border_style=PLAN_C,
                        box=box.ROUNDED,
                        padding=(0, 1), expand=False,
                    ))
                    self.messages.pop()
                continue

            # ── /review ──
            if line.startswith("/review"):
                parts = line.split(maxsplit=2)
                if len(parts) < 2 or not parts[1].strip():
                    self.console.print(
                        "[dim]用法：/review <path> "
                        "[--dim security,performance,readability][/]")
                    continue
                path = parts[1].strip()
                dims = None
                if len(parts) >= 3:
                    rest = parts[2]
                    if "--dim" in rest:
                        dims = [
                            d.strip()
                            for d in rest.split("--dim", 1)[1].strip().split(",")
                            if d.strip()
                        ]
                from .tools.multi_review import multi_review as _mr
                self._subagent_depth = 1
                try:
                    with ui.ToolStatus(self.console,
                                        "multi_review", path):
                        r = _mr(path=path, root=self.root,
                                dimensions=dims,
                                max_steps=5, timeout=180,
                                parent=self)
                finally:
                    self._subagent_depth = 0
                self.console.print()
                self.console.print(Panel(
                    Text(r.get("summary", ""), style=""),
                    title="[bold]审查报告[/]",
                    title_align="left",
                    border_style=PLAN_C, box=box.ROUNDED,
                    padding=(0, 1), expand=False,
                ))
                continue

            # ── /mem ──
            if line == "/mem" or line.startswith("/mem "):
                parts = line.split(maxsplit=2)
                sub = parts[1].strip().lower() if len(parts) >= 2 else ""
                from . import memory as _mem
                if sub in ("", "list"):
                    items = _mem.list_all()
                    if not items:
                        self.console.print(
                            "[dim]暂无记忆。用 /mem add <key> "
                            "<value>[/]")
                        continue
                    tbl = Table(box=box.SIMPLE,
                                header_style=f"bold {BRAND}")
                    tbl.add_column("类别", style="dim")
                    tbl.add_column("Key", style="bold")
                    tbl.add_column("Value")
                    tbl.add_column("更新", style="dim")
                    for it in items[:50]:
                        ts = time.strftime(
                            "%m-%d %H:%M",
                            time.localtime(it.get("updated_at", 0)))
                        tbl.add_row(
                            it.get("category", "other"),
                            escape(it.get("key", "")),
                            escape(str(it.get("value", ""))[:60]),
                            ts)
                    self.console.print(tbl)
                    self.console.print(f"[dim]{_mem.stats()}[/]")
                    continue
                if sub == "add" and len(parts) >= 4:
                    key = parts[2].strip()
                    value = parts[3].strip()
                    _mem.add(key, value)
                    self.console.print(
                        f"[ok]✓ 已记住 {escape(key)} = "
                        f"{escape(value)}[/]")
                    continue
                if sub in ("rm", "remove", "forget") \
                        and len(parts) >= 3:
                    token = parts[2].strip()
                    if _mem.remove(token):
                        self.console.print(
                            f"[ok]✓ 已删除 '{escape(token)}'[/]")
                    else:
                        self.console.print(
                            f"[err]✗ 未找到 '{escape(token)}'[/]")
                    continue
                if sub == "search" and len(parts) >= 3:
                    items = _mem.search(parts[2].strip())
                    if not items:
                        self.console.print("[dim]无匹配[/]")
                        continue
                    for it in items:
                        self.console.print(
                            f"  [{it.get('category')}] "
                            f"{escape(it.get('key'))} = "
                            f"{escape(str(it.get('value')))}")
                    continue
                if sub == "clear":
                    from .ui.confirm import confirm_yes_no
                    if not self.auto_yes:
                        if not confirm_yes_no(
                            self.console, "清空所有记忆？",
                            default_yes=False, danger=True,
                            show_dog=True,
                        ):
                            self.console.print("[dim]已取消。[/]")
                            continue
                    n = _mem.clear()
                    self.console.print(f"[ok]✓ 已清空 {n} 条[/]")
                    continue
                if sub in ("batch", "batch-delete"):
                    from .ui.confirm import multi_delete, confirm_yes_no
                    items = _mem.list_all()
                    if not items:
                        self.console.print("[dim]暂无记忆[/]")
                        continue
                    choices = [
                        (it.get("id", ""),
                         f"[{it.get('category', 'other')}] "
                         f"{it.get('key', '')} = "
                         f"{it.get('value', '')[:50]}", "")
                        for it in items
                    ]
                    chosen = multi_delete(
                        self.console,
                        f"批量删除记忆（{len(choices)} 条）",
                        choices)
                    if not chosen:
                        continue
                    if not confirm_yes_no(
                        self.console,
                        f"确认删除 {len(chosen)} 条记忆？",
                        default_yes=False, danger=True,
                        show_dog=True,
                    ):
                        continue
                    n = 0
                    for mid in chosen:
                        if _mem.remove(mid):
                            n += 1
                    self.console.print(f"[ok]✓ 已删除 {n} 条[/]")
                    continue
                self.console.print(
                    "[dim]用法：/mem [list|add <k> <v>|rm <k>|"
                    "search <q>|batch|clear][/]")
                continue

            # ── /cron ──
            if line.startswith("/cron"):
                self._handle_cron_command(line)
                continue

            # ── /dream ──
            if line.startswith("/dream"):
                self._handle_dream_command(line)
                continue

            # ── /asks ──
            if line.startswith("/asks"):
                self._handle_asks_command(line)
                continue

            # ── /pricing ──
            if line.startswith("/pricing"):
                self._handle_pricing_command(line)
                continue

            # ── /cost ──
            if line.startswith("/cost"):
                self._handle_cost_command(line)
                continue

            # ── /budget ──
            if line.startswith("/budget"):
                self._handle_budget_command(line)
                continue

            # ── /dog ──
            if line.startswith("/dog"):
                self._handle_dog_command(line)
                continue

            # ── @file 引用 ──
            if "@" in line:
                from .at_ref import expand_at_refs
                expanded, ref_warnings, ref_ok = expand_at_refs(
                    self.root, line)
                for w in ref_warnings:
                    self.console.print(
                        f"  [warn]⚠ {escape(w)}[/]")
                if ref_ok:
                    self.console.print(
                        f"  [dim]· 已附加引用:[/] "
                        + "  ".join(
                            f"[accent]@{escape(p)}[/]"
                            for p in ref_ok))
                if expanded != line:
                    line = expanded

            self.console.print()
            try:
                self.agent_turn(line)
                self._maybe_auto_compact()
            except SystemExit as exc:
                self.console.print(
                    f"[err]{escape(str(exc))}[/]")
                self.messages.pop()
                continue
            except KeyboardInterrupt:
                self.console.print(
                    "\n[dim](已中断本轮对话)[/]")
                continue
            self.console.print()

    # ================================================================== #
    # 子命令处理
    # ================================================================== #

    def _handle_cron_command(self, line: str) -> None:
        parts = line.split(maxsplit=3)
        sub = parts[1].strip().lower() if len(parts) >= 2 else "list"
        from . import cron as _cron
        if sub in ("", "list"):
            jobs = _cron.list_jobs()
            if not jobs:
                self.console.print(
                    "[dim]无任务。用 /cron add <name> "
                    "\"<cron>\" \"<prompt>\"[/]")
                return
            for j in jobs:
                self.console.print(_cron.format_job(j))
                self.console.print()
            return
        if sub == "add":
            rest = line[len("/cron add"):].strip()
            import shlex as _shlex
            try:
                toks = _shlex.split(rest)
            except ValueError as exc:
                self.console.print(
                    f"[err]✗ 参数解析失败: {escape(str(exc))}[/]")
                return
            if len(toks) < 3:
                self.console.print(
                    "[dim]用法：/cron add <name> \"<cron>\" "
                    "\"<prompt>\"[/]")
                return
            cname, schedule = toks[0], toks[1]
            prompt = " ".join(toks[2:])
            jid, err = _cron.add_job(cname, schedule, prompt)
            if err:
                self.console.print(f"[err]✗ {escape(err)}[/]")
            else:
                self.console.print(
                    f"[ok]✓ 已创建 {escape(jid)}[/]")
                self._ensure_cron_daemon()
            return
        if sub in ("rm", "remove") and len(parts) >= 3:
            token = parts[2].strip()
            ok = _cron.remove_job(token)
            self.console.print(
                f"[ok]✓ 已删除 '{escape(token)}'[/]" if ok
                else f"[err]✗ 未找到 '{escape(token)}'[/]")
            return
        if sub in ("enable", "disable") and len(parts) >= 3:
            token = parts[2].strip()
            enabled = (sub == "enable")
            ok = _cron.enable_job(token, enabled)
            if ok:
                self.console.print(
                    f"[ok]✓ 已{'启用' if enabled else '禁用'} "
                    f"'{escape(token)}'[/]")
                if enabled:
                    self._ensure_cron_daemon()
            else:
                self.console.print(
                    f"[err]✗ 未找到 '{escape(token)}'[/]")
            return
        if sub == "run" and len(parts) >= 3:
            token = parts[2].strip()
            self._ensure_cron_daemon()
            if self._cron_daemon is None:
                self.console.print("[err]✗ 调度器未启动[/]")
                return
            msg = self._cron_daemon.run_now(token)
            self.console.print(f"[dim]{escape(msg)}[/]")
            return
        if sub == "log" and len(parts) >= 3:
            token = parts[2].strip()
            j = _cron.get_job(token)
            if not j:
                self.console.print(
                    f"[err]✗ 未找到 '{escape(token)}'[/]")
                return
            files = _cron.list_logs(j["id"], limit=3)
            if not files:
                self.console.print("[dim]无日志[/]")
                return
            for f in files:
                self.console.print(
                    f"[bold]── {f.name} ──[/]")
                try:
                    content = f.read_text(encoding="utf-8")
                except OSError:
                    continue
                self.console.print(
                    "\n".join(content.splitlines()[:60]))
                self.console.print()
            return
        if sub == "start":
            self._ensure_cron_daemon()
            self.console.print("[ok]✓ 调度器已启动[/]")
            return
        if sub == "stop":
            self._stop_cron_daemon()
            self.console.print("[dim]调度器已停止[/]")
            return
        if sub in ("batch", "batch-toggle"):
            from .ui.confirm import confirm_multi
            from .ui.progress import celebrate
            jobs = _cron.list_jobs()
            if not jobs:
                self.console.print("[dim]无任务[/]")
                return
            items = [
                (j.get("id", ""), j.get("name", ""),
                 f"{j.get('schedule', '')}  "
                 f"{'启用' if j.get('enabled', True) else '禁用'}")
                for j in jobs
            ]
            preselect = [
                j.get("id", "") for j in jobs
                if j.get("enabled", True)
            ]
            chosen = confirm_multi(
                self.console,
                f"批量选择启用任务（{len(jobs)}）",
                items, preselect=preselect)
            for j in jobs:
                jid = j.get("id", "")
                _cron.enable_job(jid, jid in chosen)
            celebrate(self.console, "已保存", duration=0.2,
                      stats=f"{len(chosen)}/{len(jobs)} 启用")
            return
        self.console.print(
            "[dim]用法：/cron [list|add|rm|enable|disable|"
            "run|log|start|stop|batch][/]")

    def _handle_dream_command(self, line: str) -> None:
        parts = line.split(maxsplit=2)
        sub = parts[1].strip().lower() if len(parts) >= 2 else "run"
        from . import dream as _dream
        if sub in ("run", ""):
            days = 3
            focus = ""
            if len(parts) >= 3:
                rest = parts[2]
                for tok in rest.split():
                    if tok.startswith("--days="):
                        try:
                            days = int(tok.split("=", 1)[1])
                        except ValueError:
                            pass
                    elif not tok.startswith("--"):
                        focus = (focus + " " + tok).strip()
            self.console.print(
                f"[dim]🌙 做梦…（回顾 {days} 天）[/]")
            r = _dream.run_dream(self, days=days, focus=focus)
            if not r.get("ok"):
                self.console.print(
                    f"[err]✗ {escape(r.get('error', '未知'))}[/]")
                return
            self.console.print()
            self.console.print(Panel(
                Text(r["answer"], style=""),
                title=f"[bold]🌙 梦境 · {r['duration']}s[/]",
                title_align="left",
                border_style=PLAN_C, box=box.ROUNDED,
                padding=(0, 1), expand=False,
            ))
            if r.get("memory_candidates"):
                self.console.print()
                self.console.print(
                    f"[dim]💡 {len(r['memory_candidates'])} 条"
                    f"记忆候选[/]")
            self.console.print(f"[dim]已保存: {r['path']}[/]")
            return
        if sub == "list":
            dreams = _dream.list_dreams(limit=20)
            if not dreams:
                self.console.print("[dim]还没有做过梦。[/]")
                return
            tbl = Table(box=box.SIMPLE,
                        header_style=f"bold {BRAND}")
            tbl.add_column("时间", style="dim")
            tbl.add_column("ID", style="bold")
            tbl.add_column("大小", style="dim")
            for d in dreams:
                ts = time.strftime(
                    "%m-%d %H:%M",
                    time.localtime(d["mtime"]))
                tbl.add_row(ts, d["id"], f"{d['size']} B")
            self.console.print(tbl)
            return
        if sub == "read" and len(parts) >= 3:
            did = parts[2].strip()
            text = _dream.read_dream(did)
            if not text:
                self.console.print(
                    f"[err]✗ 未找到 {escape(did)}[/]")
                return
            self.console.print()
            self.console.print(text)
            return
        if sub == "stats":
            self.console.print(_dream.dream_stats())
            return
        if sub == "cron":
            schedule = parts[2].strip() if len(parts) >= 3 \
                else "0 3 * * *"
            from . import cron as _cron
            jid, err = _cron.add_job(
                "夜梦", schedule, "__DREAM__ 回顾最近 3 天")
            if err:
                self.console.print(f"[err]✗ {escape(err)}[/]")
            else:
                self.console.print(
                    f"[ok]✓ 已添加定时梦境 {jid} ({schedule})[/]")
                self._ensure_cron_daemon()
            return
        self.console.print(
            "[dim]用法：/dream [run [--days=N] [focus]|list|"
            "read <id>|stats|cron [schedule]][/]")

    def _handle_asks_command(self, line: str) -> None:
        parts = line.split(maxsplit=3)
        sub = parts[1].strip().lower() if len(parts) >= 2 else ""
        if sub == "clear":
            from .ui.confirm import confirm_yes_no
            if not self.session_asks:
                self.console.print("[dim]无记录。[/]")
                return
            if not self.auto_yes:
                if not confirm_yes_no(
                    self.console, f"清空 {len(self.session_asks)} 条"
                    f"问答历史？",
                    default_yes=False, danger=True,
                    show_dog=True,
                ):
                    self.console.print("[dim]已取消。[/]")
                    return
            n = len(self.session_asks)
            self.session_asks = []
            self._save_session()
            self.console.print(f"[ok]✓ 已清空 {n} 条。[/]")
            return
        if sub == "export":
            fmt = parts[2].strip() if len(parts) >= 3 else "md"
            target = parts[3].strip() if len(parts) >= 4 else None
            self._export_asks(fmt, target)
            return
        if not self.session_asks:
            self.console.print("[dim]暂无问答历史。[/]")
            return
        from rich.tree import Tree
        threads: dict = {}
        order: list = []
        for rec in self.session_asks:
            th = rec.get("thread") or rec.get("id") or "?"
            if th not in threads:
                threads[th] = []
                order.append(th)
            threads[th].append(rec)
        self.console.print(
            f"[bold {BRAND}]问答历史[/]  "
            f"[dim]{len(self.session_asks)} 条 · "
            f"{len(order)} 个 thread[/]")
        self.console.print()
        for ti, th in enumerate(order, 1):
            recs = threads[th]
            root = Tree(
                f"[bold {BRAND}]Thread {ti}[/]  "
                f"[dim]{len(recs)} 条[/]")
            for rec in recs:
                ts = time.strftime(
                    "%H:%M:%S",
                    time.localtime(rec.get("ts", 0)))
                header = rec.get("header", "")
                title = header or "模型提问"
                node = root.add(
                    f"[dim]{ts}[/]  [bold]{escape(title)}[/]")
                for q in rec.get("questions") or []:
                    q_text = escape(str(q.get("question", ""))[:60])
                    a_text = escape(
                        str(q.get("answer") or "（未答）")[:60])
                    node.add(
                        f"[dim]{escape(q.get('key', '?'))}:[/] "
                        f"{q_text}")
                    node.add(f"  [accent]→ {a_text}[/]")
            self.console.print(root)
            self.console.print()
        self.console.print(
            "[dim]/asks export [md|json|csv] [路径]  ·  "
            "/asks clear[/]")

    def _export_asks(self, fmt: str = "md",
                     target: str | None = None) -> None:
        if not self.session_asks:
            self.console.print("[dim]暂无问答历史可导出。[/]")
            return
        fmt = (fmt or "md").lower()
        if fmt in ("markdown", "m"):
            fmt = "md"
        if fmt not in ("md", "json", "csv"):
            self.console.print(
                f"[err]✗ 不支持的格式: {escape(fmt)}[/]")
            return
        ext = {"md": ".md", "json": ".json", "csv": ".csv"}[fmt]
        if target:
            out = Path(target).expanduser()
            if not out.is_absolute():
                out = Path.cwd() / out
        else:
            out = Path.cwd() / f"asks-{self.session_id}{ext}"
        try:
            if fmt == "md":
                content = self._asks_markdown()
            elif fmt == "json":
                content = json.dumps(self.session_asks,
                                     ensure_ascii=False, indent=2)
            else:
                content = self._asks_csv()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        except OSError as exc:
            self.console.print(
                f"[err]✗ 导出失败: {escape(str(exc))}[/]")
            return
        self.console.print(
            f"[ok]✓ 已导出 {len(self.session_asks)} 条到[/] "
            f"[path]{escape(str(out))}[/]  [dim]({fmt})[/]")

    def _asks_markdown(self) -> str:
        lines = [f"# 问答历史 · "
                 f"{self.session_title or self.session_id}", ""]
        lines.append(f"- **会话**：`{self.session_id}`")
        lines.append(f"- **记录数**：{len(self.session_asks)}")
        lines.append("")
        for i, rec in enumerate(self.session_asks, 1):
            ts = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(rec.get("ts", 0)))
            header = rec.get("header", "") or "模型提问"
            lines.append(f"## {i}. {header} · {ts}")
            lines.append("")
            for q in rec.get("questions") or []:
                lines.append(f"**{q.get('key')}**: "
                             f"{q.get('question', '')}")
                lines.append(f"**回答**：{q.get('answer') or '（未答）'}")
                lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def _asks_csv(self) -> str:
        import csv as _csv
        import io
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["ts", "time", "thread", "turn", "parent_id",
                    "header", "question_key", "question", "options",
                    "default", "answer"])
        for rec in self.session_asks:
            t = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(rec.get("ts", 0)))
            for q in rec.get("questions") or []:
                w.writerow([
                    rec.get("ts", ""), t,
                    rec.get("thread", ""), rec.get("turn", ""),
                    rec.get("parent_id") or "",
                    rec.get("header", ""), q.get("key", ""),
                    q.get("question", ""),
                    " | ".join(str(o) for o in (q.get("options") or [])),
                    q.get("default", ""), q.get("answer", ""),
                ])
        return buf.getvalue()

    def _handle_pricing_command(self, line: str) -> None:
        from . import pricing as _pricing
        parts = line.split(maxsplit=5)
        sub = parts[1].strip().lower() if len(parts) >= 2 else ""
        if sub in ("", "list", "ls"):
            user = _pricing.load_user_pricing()
            if not user:
                self.console.print(
                    "[dim]暂无自定义价格。用 /pricing preset "
                    "查看内置。[/]")
                return
            self.console.print()
            self.console.print(
                f"[bold {BRAND}]自定义价格（$/1M tokens）[/]")
            self.console.print()
            self.console.print(_pricing.format_grouped_pricing(user))
            return
        if sub == "preset":
            self.console.print()
            self.console.print(
                f"[bold {BRAND}]内置价格表（$/1M tokens）[/]")
            self.console.print()
            self.console.print(_pricing.format_grouped_pricing(
                _pricing.BUILTIN_PRICING))
            return
        if sub == "grouped":
            user = _pricing.load_user_pricing()
            if not user:
                self.console.print("[dim]暂无自定义价格[/]")
                return
            self.console.print()
            self.console.print(_pricing.format_grouped_pricing(user))
            return
        if sub == "set" and len(parts) >= 6:
            model = parts[2].strip()
            try:
                ic = float(parts[3])
                i = float(parts[4])
                o = float(parts[5])
            except (ValueError, IndexError):
                self.console.print(
                    "[err]✗ 用法：/pricing set <model> "
                    "<cached> <input> <output>[/]")
                return
            user = _pricing.load_user_pricing()
            user[model] = (ic, i, o)
            if _pricing.save_user_pricing(user):
                self.console.print(
                    f"[ok]✓ 已设置 {escape(model)}: "
                    f"cached {ic} / input {i} / output {o}[/]")
            else:
                self.console.print("[err]✗ 保存失败[/]")
            return
        if sub == "rm" and len(parts) >= 3:
            model = parts[2].strip()
            user = _pricing.load_user_pricing()
            if model in user:
                del user[model]
                _pricing.save_user_pricing(user)
                self.console.print(
                    f"[ok]✓ 已删除 {escape(model)}[/]")
            else:
                self.console.print(
                    f"[err]✗ 未找到 {escape(model)}[/]")
            return
        if sub == "import":
            if len(parts) >= 3:
                model = parts[2].strip()
                if _pricing.import_builtin(model):
                    self.console.print(
                        f"[ok]✓ 已导入 {escape(model)}[/]")
                else:
                    self.console.print(
                        f"[err]✗ 内置表里无 {escape(model)}[/]")
            else:
                n = _pricing.import_all_builtin()
                self.console.print(
                    f"[ok]✓ 导入了 {n} 个内置模型[/]")
            return
        if sub == "show":
            model = parts[2].strip() if len(parts) >= 3 else self.model
            self.console.print(_pricing.format_pricing_line(model))
            return
        if sub == "stats":
            self.console.print(_pricing.stats())
            return
        if sub == "export":
            target = parts[2].strip() if len(parts) >= 3 else ""
            if target == "builtin":
                ok, path_or_err, n = _pricing.builtin_export_json()
            else:
                ok, path_or_err, n = _pricing.export_json(target)
            if ok:
                self.console.print(
                    f"[ok]✓ 已导出 {n} 个模型到[/] "
                    f"[path]{escape(path_or_err)}[/]")
            else:
                self.console.print(
                    f"[err]✗ {escape(path_or_err)}[/]")
            return
        if sub == "import-json":
            if len(parts) < 3:
                self.console.print(
                    "[err]✗ 用法：/pricing import-json <file> "
                    "[--replace][/]")
                return
            path = parts[2].strip()
            mode = "merge"
            if len(parts) >= 4 and "--replace" in parts[3]:
                mode = "replace"
            ok, msg, n = _pricing.import_json(path, mode=mode)
            if ok:
                self.console.print(f"[ok]✓ {escape(msg)}[/]")
            else:
                self.console.print(f"[err]✗ {escape(msg)}[/]")
            return
        self.console.print(
            "[dim]用法：/pricing [list|grouped|set|rm|import|"
            "preset|show|stats|export [file|builtin]|"
            "import-json <file> [--replace]][/]")

    def _handle_cost_command(self, line: str) -> None:
        from . import cost_tracker as _ct
        parts = line.split(maxsplit=4)
        sub = parts[1].strip().lower() if len(parts) >= 2 else "today"
        if sub in ("today", "t"):
            info = _ct.today_total()["total"]
            self.console.print(
                f"[bold {BRAND}]今日成本[/]  "
                f"[accent]${info['cost']:.4f}[/]  "
                f"[dim]{info['turns']} 轮 · "
                f"{info['in']}↑ {info['out']}↓ tok · "
                f"缓存 {info['cached']}[/]")
            self.console.print()
            self.console.print(_ct.render_by_model("today"))
            return
        if sub in ("week", "w"):
            info = _ct.week_total()["total"]
            self.console.print(
                f"[bold {BRAND}]本周成本[/]  "
                f"[accent]${info['cost']:.4f}[/]")
            self.console.print()
            self.console.print(_ct.render_by_model("week"))
            return
        if sub in ("month", "m"):
            info = _ct.month_total()["total"]
            self.console.print(
                f"[bold {BRAND}]本月成本[/]  "
                f"[accent]${info['cost']:.4f}[/]")
            self.console.print()
            self.console.print(_ct.render_by_model("month"))
            return
        if sub == "all":
            info = _ct.all_total()["total"]
            self.console.print(
                f"[bold {BRAND}]累计[/]  "
                f"[accent]${info['cost']:.4f}[/]")
            self.console.print()
            self.console.print(_ct.render_by_model("all"))
            return
        if sub in ("chart", "c"):
            days = 30
            if len(parts) >= 3:
                try:
                    days = max(1, min(int(parts[2]), 180))
                except ValueError:
                    pass
            self.console.print()
            self.console.print(_ct.render_daily_chart(days))
            return
        if sub == "hourly":
            hours = 24
            if len(parts) >= 3:
                try:
                    hours = max(1, min(int(parts[2]), 168))
                except ValueError:
                    pass
            self.console.print()
            self.console.print(_ct.render_hourly_chart(hours))
            return
        if sub in ("anomaly", "anom", "a"):
            days = 30
            sens = "medium"
            if len(parts) >= 3:
                try:
                    days = max(7, min(int(parts[2]), 180))
                except ValueError:
                    pass
            if len(parts) >= 4:
                s = parts[3].strip().lower()
                if s in ("low", "medium", "high"):
                    sens = s
            self.console.print()
            self.console.print(
                _ct.format_anomaly_report(days=days,
                                           sensitivity=sens))
            return
        if sub in ("forecast", "f", "predict"):
            days = 30
            if len(parts) >= 3:
                try:
                    days = max(7, min(int(parts[2]), 365))
                except ValueError:
                    pass
            self.console.print()
            self.console.print(_ct.format_forecast(days_ahead=days))
            return
        if sub in ("export", "e", "csv"):
            detail = "turn"
            period_ = "all"
            path = ""
            if len(parts) >= 3:
                detail = parts[2].strip().lower()
                if detail not in ("turn", "daily", "model", "session"):
                    self.console.print(
                        f"[err]✗ 未知 detail: {escape(detail)}[/]")
                    return
            if len(parts) >= 4:
                period_ = parts[3].strip().lower()
                if period_ not in ("today", "week", "month", "all"):
                    self.console.print(
                        f"[err]✗ 未知 period: {escape(period_)}[/]")
                    return
            parts_ext = line.split(maxsplit=5)
            if len(parts_ext) >= 6:
                path = parts_ext[5].strip()
            ok, result_path, rows = _ct.export_csv(
                path=path, period=period_, detail=detail)
            if ok:
                self.console.print(
                    f"[ok]✓ 已导出 {rows} 行到[/] "
                    f"[path]{escape(result_path)}[/]")
            else:
                self.console.print(
                    f"[err]✗ {escape(result_path)}[/]")
            return
        if sub == "clear":
            from .ui.confirm import confirm_yes_no
            if not self.auto_yes:
                if not confirm_yes_no(
                    self.console, "清空成本日志？",
                    default_yes=False, danger=True,
                    show_dog=True,
                ):
                    self.console.print("[dim]已取消。[/]")
                    return
            n = _ct.clear_log()
            self.console.print(f"[ok]✓ 已清空 {n} 条记录[/]")
            return
        self.console.print(
            "[dim]用法：/cost [today|week|month|all|chart [n]|"
            "hourly [n]|anomaly [days] [low|medium|high]|"
            "forecast [days]|export [detail] [period] [path]|"
            "clear][/]")

    def _handle_budget_command(self, line: str) -> None:
        from . import cost_tracker as _ct
        parts = line.split(maxsplit=3)
        sub = parts[1].strip().lower() if len(parts) >= 2 else ""
        if sub in ("", "show", "status"):
            self.console.print()
            self.console.print(_ct.format_budget_status())
            return
        if sub == "set":
            if len(parts) < 4:
                self.console.print(
                    "[err]✗ 用法：/budget set "
                    "<daily|weekly|monthly> <金额>[/]")
                return
            period = parts[2].strip().lower()
            if period not in ("daily", "weekly", "monthly"):
                self.console.print(
                    "[err]✗ period 必须是 daily/weekly/monthly[/]")
                return
            try:
                amount = float(parts[3])
            except ValueError:
                self.console.print("[err]✗ 金额必须是数字[/]")
                return
            if amount < 0:
                self.console.print("[err]✗ 金额不能为负[/]")
                return
            b = _ct.load_budget()
            b[period] = amount
            if _ct.save_budget(b):
                self.console.print(
                    f"[ok]✓ 已设置 {period} 预算 = ${amount:.4f}[/]")
            else:
                self.console.print("[err]✗ 保存失败[/]")
            return
        if sub == "clear":
            if _ct.save_budget({"daily": 0, "weekly": 0,
                                 "monthly": 0}):
                self.console.print("[ok]✓ 已清除所有预算[/]")
            return
        if sub == "reset":
            from .ui.confirm import confirm_yes_no
            if not self.auto_yes:
                if not confirm_yes_no(
                    self.console, "重置成本记录？",
                    default_yes=False, danger=True,
                    show_dog=True,
                ):
                    self.console.print("[dim]已取消。[/]")
                    return
            n = _ct.clear_log()
            self.console.print(f"[ok]✓ 已重置 {n} 条记录[/]")
            return
        self.console.print(
            "[dim]用法：/budget [show|set <period> <amount>|"
            "clear|reset][/]")

    def _handle_dog_command(self, line: str) -> None:
        from .ui import dog as _dog
        parts = line.split(maxsplit=2)
        sub = parts[1].strip().lower() if len(parts) >= 2 else ""
        if sub in ("", "show", "stats"):
            self.console.print(_dog.stats())
            return
        if sub == "reload":
            _dog.reload_frames()
            self.console.print("[ok]✓ 已重新加载[/]")
            return
        if sub == "edit":
            if not _dog.DOG_PATH.exists():
                ok, p = _dog.export_default_toml(str(_dog.DOG_PATH))
                if not ok:
                    self.console.print(f"[err]✗ {p}[/]")
                    return
            editor = os.environ.get("EDITOR", "notepad")
            try:
                subprocess.run([editor, str(_dog.DOG_PATH)])
            except Exception as exc:
                self.console.print(f"[err]✗ {exc}[/]")
                return
            _dog.reload_frames()
            self.console.print("[ok]✓ 已重新加载[/]")
            return
        if sub == "export":
            path = parts[2].strip() if len(parts) >= 3 else ""
            ok, p = _dog.export_default_toml(path)
            if ok:
                self.console.print(f"[ok]✓ 导出到 {p}[/]")
            else:
                self.console.print(f"[err]✗ {p}[/]")
            return
        if sub == "preview":
            state = parts[2].strip() if len(parts) >= 3 else "idle"
            if state not in ("idle", "busy", "confirm", "error"):
                state = "idle"
            self.console.print(f"[dim]预览 {state}：[/]")
            _dog.play_animation(state, cycles=3)
            self.console.print()
            return
        self.console.print(
            "[dim]用法：/dog [show|reload|edit|export [path]|"
            "preview [state]][/]")