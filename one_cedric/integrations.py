"""User-configured MCP, hook, and command-backed tool integrations."""
from __future__ import annotations

import atexit
from collections import deque
import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


CONFIG_PATH = Path.home() / ".one-cedric" / "integrations.json"
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,47}$")
_CLIENTS: dict[str, "_McpProcess"] = {}
_CLIENTS_LOCK = threading.RLock()
_TOOL_MAP: dict[str, tuple[str, str]] = {}


def agents_skills_enabled() -> bool:
    """~/.agents/skills 只读技能开关（integrations.json 可关，默认开）。"""
    data = load_integrations()
    cfg = data.get("agents_skills")
    if isinstance(cfg, dict) and "enabled" in cfg:
        return bool(cfg["enabled"])
    return True


def _agents_skill_schema() -> dict | None:
    if not agents_skills_enabled():
        return None
    try:
        from .agents_skills import list_agents_skills
        count = len(list_agents_skills())
    except Exception:
        return None
    if count == 0:
        return None
    return {
        "type": "function",
        "function": {
            "name": "agents_skill",
            "description": (
                "读取 ~/.agents/skills 中第三方安装的文档型技能（只读）。"
                "先不带 name 调用以枚举可用技能，再传入 name 读取该技能"
                "的完整说明（SKILL.md），并按其中的指引执行（例如调用"
                "技能所需的 CLI 工具）。")
            .replace("\n", " ")[:4000],
            "parameters": {
                "type": "object",
                "properties": {
                    "list": {
                        "type": "boolean",
                        "description": "为 true 或省略 name 时列出所有技能",
                    },
                    "name": {
                        "type": "string",
                        "description": "要读取的技能名",
                    },
                },
            },
        },
    }


def load_integrations() -> dict:
    if not CONFIG_PATH.exists():
        return {"mcp_servers": {}, "hooks": [], "custom_tools": {}}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"读取集成配置失败: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"集成配置格式错误: {CONFIG_PATH}")
    data.setdefault("mcp_servers", {})
    data.setdefault("hooks", [])
    data.setdefault("custom_tools", {})
    if not isinstance(data["mcp_servers"], dict):
        raise RuntimeError("integrations.mcp_servers 必须是对象")
    if not isinstance(data["hooks"], list):
        raise RuntimeError("integrations.hooks 必须是数组")
    if not isinstance(data["custom_tools"], dict):
        raise RuntimeError("integrations.custom_tools 必须是对象")
    if any(not isinstance(entry, dict)
           for entry in data["mcp_servers"].values()):
        raise RuntimeError("每个 MCP server 配置都必须是对象")
    if any(not isinstance(entry, dict) for entry in data["hooks"]):
        raise RuntimeError("每个 Hook 配置都必须是对象")
    if any(not isinstance(entry, dict)
           for entry in data["custom_tools"].values()):
        raise RuntimeError("每个 custom tool 配置都必须是对象")
    return data


def save_integrations(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(CONFIG_PATH)


# ─────────────────────────────────────────────────────────────────────── #
# 自定义工具（custom_tools）管理：安装 / 卸载 / 列表
# ─────────────────────────────────────────────────────────────────────── #

def _tool_name_ok(name: str) -> bool:
    return bool(name) and bool(_NAME_RE.match(name))


def install_custom_tool(name: str, description: str = "",
                        parameters: dict | None = None,
                        command: list | None = None,
                        args: list | None = None,
                        write: bool = True,
                        enabled: bool = True) -> tuple[bool, str]:
    """安装一个命令式自定义工具（写入 integrations.json）。

    返回 (ok, message)。command 为可执行命令参数列表；执行时工具参数
    JSON 会通过 stdin 传入，stdout 作为工具结果返回。
    """
    if not _tool_name_ok(name):
        return False, ("工具名须以字母开头，且只含字母、数字、_、-"
                       "（最长 48 字符）")
    if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part.strip() for part in command):
        return False, "command 必须是非空字符串数组"
    if not isinstance(args, list) or not all(
            isinstance(part, str) for part in args):
        args = []
    if parameters is None:
        parameters = {"type": "object", "properties": {}}
    data = load_integrations()
    tools = data.setdefault("custom_tools", {})
    if name in tools:
        return False, f"自定义工具 '{name}' 已存在"
    tools[name] = {
        "description": str(description or ""),
        "parameters": _clean_schema(parameters),
        "command": command,
        "args": args,
        "write": bool(write),
        "enabled": bool(enabled),
    }
    save_integrations(data)
    return True, f"已安装 custom__{name}"


def uninstall_custom_tool(name: str) -> tuple[bool, str]:
    """卸载自定义工具（从配置移除；脚本文件保留以便恢复）。"""
    data = load_integrations()
    tools = data.setdefault("custom_tools", {})
    if name not in tools:
        return False, f"自定义工具 '{name}' 不存在"
    del tools[name]
    save_integrations(data)
    return True, f"已卸载 custom__{name}"


def toggle_custom_tool(name: str) -> tuple[bool, str]:
    data = load_integrations()
    tools = data.setdefault("custom_tools", {})
    if name not in tools:
        return False, f"自定义工具 '{name}' 不存在"
    tools[name]["enabled"] = not tools[name].get("enabled", True)
    save_integrations(data)
    state = "启用" if tools[name]["enabled"] else "禁用"
    return True, f"custom__{name} 已{state}"


def list_custom_tools() -> list[dict]:
    data = load_integrations()
    tools = data.get("custom_tools", {})
    out = []
    if isinstance(tools, dict):
        for name, entry in tools.items():
            if not isinstance(entry, dict):
                continue
            out.append({
                "name": name,
                "public_name": "custom__" + name,
                "description": str(entry.get("description", ""))[:300],
                "enabled": bool(entry.get("enabled", True)),
                "write": bool(entry.get("write", True)),
                "command": entry.get("command", []),
            })
    return out


def _clean_schema(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("type", "object") != "object":
        return {"type": "object", "properties": {}}
    schema = dict(value)
    schema["type"] = "object"
    schema["properties"] = (
        schema.get("properties")
        if isinstance(schema.get("properties"), dict) else {}
    )
    required = schema.get("required", [])
    schema["required"] = [
        name for name in required
        if isinstance(name, str) and name in schema["properties"]
    ] if isinstance(required, list) else []
    return schema


class _McpProcess:
    def __init__(self, name: str, config: dict):
        command = config.get("command")
        args = config.get("args", [])
        if not isinstance(command, str) or not command.strip():
            raise RuntimeError(f"MCP server '{name}' 缺少 command")
        if not isinstance(args, list) or not all(
                isinstance(arg, str) for arg in args):
            raise RuntimeError(f"MCP server '{name}' 的 args 必须是字符串数组")
        env = os.environ.copy()
        extra_env = config.get("env", {})
        if not isinstance(extra_env, dict):
            raise RuntimeError(f"MCP server '{name}' 的 env 必须是对象")
        env.update({str(k): str(v) for k, v in extra_env.items()})
        try:
            self.proc = subprocess.Popen(
                [command, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except OSError as exc:
            raise RuntimeError(
                f"启动 MCP server '{name}' 失败: {exc}"
            ) from exc
        self._responses: queue.Queue = queue.Queue()
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=20)
        assert self.proc.stderr is not None
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, daemon=True,
            name=f"mcp-stderr-{name}",
        )
        self._stderr_reader.start()
        self._next_id = 0
        self._reader = threading.Thread(
            target=self._read_messages, daemon=True,
            name=f"mcp-reader-{name}",
        )
        self._reader.start()
        try:
            self._request("initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "One Cedric", "version": "0.17.0"},
            })
            self._notify("notifications/initialized")
        except Exception:
            self.close()
            raise

    def _read_messages(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._responses.put(json.loads(line))
            except json.JSONDecodeError:
                self._responses.put({
                    "_invalid_message": line[:500],
                })
        self._responses.put({"_closed": True})

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def _send(self, message: dict) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise RuntimeError("MCP server process is not running")
        payload = json.dumps(message, ensure_ascii=False)
        with self._write_lock:
            self.proc.stdin.write(payload + "\n")
            self.proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        message: dict[str, Any] = {
            "jsonrpc": "2.0", "method": method,
        }
        if params is not None:
            message["params"] = params
        self._send(message)

    def _request(self, method: str, params: dict | None = None) -> dict:
        with self._request_lock:
            self._next_id += 1
            request_id = self._next_id
            message: dict[str, Any] = {
                "jsonrpc": "2.0", "id": request_id, "method": method,
            }
            if params is not None:
                message["params"] = params
            self._send(message)
            deadline = time.monotonic() + 20
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"MCP request timed out: {method}")
                try:
                    response = self._responses.get(timeout=remaining)
                except queue.Empty as exc:
                    raise RuntimeError(
                        f"MCP request timed out: {method}"
                    ) from exc
                if response.get("_closed"):
                    detail = "\n".join(self._stderr_lines)
                    suffix = f": {detail}" if detail else ""
                    raise RuntimeError(
                        f"MCP server closed its output stream{suffix}"
                    )
                if "_invalid_message" in response:
                    raise RuntimeError(
                        "MCP server wrote non-JSON data to stdout: "
                        + response["_invalid_message"]
                    )
                if response.get("id") != request_id:
                    continue
                if response.get("error"):
                    error = response["error"]
                    raise RuntimeError(
                        f"MCP {method} failed: "
                        f"{error.get('message', error)}"
                    )
                result = response.get("result")
                return result if isinstance(result, dict) else {}

    def tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("MCP tools/list returned an invalid result")
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        content = result.get("content", [])
        output = []
        for part in content if isinstance(content, list) else []:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    output.append(str(part.get("text", "")))
                elif part.get("type") == "image":
                    output.append("[MCP image result]")
                else:
                    output.append(json.dumps(part, ensure_ascii=False))
        if result.get("isError"):
            return "ERROR: MCP tool failed\n" + "\n".join(output)
        return "\n".join(output) or json.dumps(result, ensure_ascii=False)

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def _client(server_name: str, config: dict) -> _McpProcess:
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(server_name)
        if client and client.proc.poll() is None:
            return client
        if client:
            client.close()
            _CLIENTS.pop(server_name, None)
        client = _McpProcess(server_name, config)
        _CLIENTS[server_name] = client
        return client


def close_mcp_servers() -> None:
    with _CLIENTS_LOCK:
        clients = list(_CLIENTS.values())
        _CLIENTS.clear()
    for client in clients:
        client.close()


atexit.register(close_mcp_servers)


def external_tool_schemas() -> list[dict]:
    config = load_integrations()
    schemas = []
    tool_map: dict[str, tuple[str, str]] = {}
    servers = config.get("mcp_servers", {})
    active_servers = set()
    if isinstance(servers, dict):
        for server_name, server in servers.items():
            if not isinstance(server, dict) or server.get("enabled") is False:
                continue
            active_servers.add(str(server_name))
            client = _client(str(server_name), server)
            for remote in client.tools():
                remote_name = remote.get("name")
                if not isinstance(remote_name, str) or not remote_name:
                    continue
                safe_server = re.sub(r"[^a-zA-Z0-9_]", "_",
                                     str(server_name))[:14]
                safe_tool = re.sub(r"[^a-zA-Z0-9_]", "_",
                                   remote_name)[:40]
                name = f"mcp__{safe_server}__{safe_tool}"
                if name in tool_map:
                    raise RuntimeError(
                        f"MCP tool name collision: {name}"
                    )
                schema = remote.get("inputSchema")
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(remote.get("description", ""))[:4000],
                        "parameters": _clean_schema(schema),
                    },
                })
                tool_map[name] = (str(server_name), remote_name)
    with _CLIENTS_LOCK:
        stale = [
            name for name in _CLIENTS
            if name not in active_servers
        ]
        for name in stale:
            _CLIENTS.pop(name).close()

    custom = config.get("custom_tools", {})
    if isinstance(custom, dict):
        for name, tool in custom.items():
            if not isinstance(tool, dict) or tool.get("enabled") is False:
                continue
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))[:48]
            public_name = "custom__" + safe_name
            schemas.append({
                "type": "function",
                "function": {
                    "name": public_name,
                    "description": str(tool.get("description", ""))[:4000],
                    "parameters": _clean_schema(tool.get("parameters")),
                },
            })
    _TOOL_MAP.clear()
    _TOOL_MAP.update(tool_map)

    skill_schema = _agents_skill_schema()
    if skill_schema is not None:
        schemas.append(skill_schema)
    return schemas


def is_external_tool(name: str) -> bool:
    return name.startswith(("mcp__", "custom__")) or name == "agents_skill"


def is_mutating_tool(name: str) -> bool:
    if name == "agents_skill":
        return False
    if name.startswith("mcp__"):
        return True
    if not name.startswith("custom__"):
        return False
    public = name[len("custom__"):]
    tool = load_integrations().get("custom_tools", {}).get(public, {})
    return bool(tool.get("write", True))


def call_external_tool(name: str, arguments: dict,
                       root: Path | None = None) -> str:
    if name == "agents_skill":
        from .agents_skills import agents_skill_tool
        if not agents_skills_enabled():
            return "ERROR: ~/.agents/skills 只读技能已关闭"
        return agents_skill_tool(arguments)

    if name.startswith("mcp__"):
        if name not in _TOOL_MAP:
            external_tool_schemas()
        target = _TOOL_MAP.get(name)
        if not target:
            return f"ERROR: 未找到 MCP 工具 '{name}'"
        server_name, remote_name = target
        server = load_integrations().get("mcp_servers", {}).get(
            server_name, {}
        )
        return _client(server_name, server).call_tool(remote_name, arguments)

    public = name[len("custom__"):] if name.startswith("custom__") else ""
    tool = load_integrations().get("custom_tools", {}).get(public)
    if not isinstance(tool, dict) or tool.get("enabled") is False:
        return f"ERROR: 未找到自定义工具 '{name}'"
    command = tool.get("command")
    args = tool.get("args", [])
    if (not isinstance(command, list) or not command
            or not isinstance(args, list)
            or not all(isinstance(part, str) for part in command + args)):
        return f"ERROR: 自定义工具 '{public}' command 配置无效"
    try:
        result = subprocess.run(
            [*command, *args],
            input=json.dumps(arguments, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: 自定义工具 '{public}' 执行失败: {exc}"
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        return f"ERROR: 自定义工具 '{public}' 退出码 {result.returncode}\n{detail}"
    return result.stdout.strip() or "(no output)"


def run_hooks(event: str, payload: dict) -> None:
    config = load_integrations()
    hooks = config.get("hooks", [])
    if not isinstance(hooks, list):
        raise RuntimeError("Hooks 配置必须是数组")
    message = json.dumps({"event": event, **payload}, ensure_ascii=False)
    for hook in hooks:
        if not isinstance(hook, dict) or not hook.get("enabled", True):
            continue
        events = hook.get("events", [])
        if event not in events:
            continue
        command = hook.get("command")
        args = hook.get("args", [])
        if not isinstance(command, list) or not command or not all(
                isinstance(part, str) for part in command + args):
            raise RuntimeError(f"Hook '{hook.get('name', '?')}' command 无效")
        try:
            result = subprocess.run(
                [*command, *args],
                input=message,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"Hook '{hook.get('name', '?')}' 执行失败: {exc}"
            ) from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-1000:]
            raise RuntimeError(
                f"Hook '{hook.get('name', '?')}' 返回 "
                f"{result.returncode}: {detail}"
            )
