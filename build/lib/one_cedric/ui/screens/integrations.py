"""CLI management screens for MCP servers, hooks, and custom tools."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests
from rich import box
from rich.panel import Panel
from rich.table import Table

from ...config import BRAND, DIM_C
from ...integrations import (
    CONFIG_PATH, external_tool_schemas, load_integrations,
    save_integrations,
)
from ..keys import wait_for_return
from ..menu import Menu, MenuItem


def _read_json(console, prompt: str, default):
    try:
        raw = console.input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        console.print(f"  [err]✗ JSON 格式错误: {exc}[/]")
        return None


def _read_text(console, prompt: str) -> str | None:
    try:
        return console.input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None


def _load_or_report(console) -> dict | None:
    try:
        return load_integrations()
    except RuntimeError as exc:
        console.print(f"  [err]✗ {exc}[/]")
        wait_for_return(console)
        return None


def run_mcp_screen(console, copilot=None) -> None:
    while True:
        data = _load_or_report(console)
        if data is None:
            return
        servers = data.get("mcp_servers", {})
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ MCP servers[/]")
        console.print(f"  [dim]Config: {CONFIG_PATH}[/]")
        table = Table(box=box.SIMPLE, padding=(0, 1), header_style=BRAND)
        table.add_column("Server", style="bold")
        table.add_column("Status")
        table.add_column("Command", style="dim")
        for name, entry in servers.items():
            table.add_row(
                name,
                "enabled" if entry.get("enabled", True) else "disabled",
                entry.get("command", ""),
            )
        if servers:
            console.print(table)
        else:
            console.print("  [dim]No MCP servers configured.[/]")
        console.print()

        choice = Menu(console, "MCP servers", [
            MenuItem("add", "Add server", "Configure an MCP stdio server"),
            MenuItem("toggle", "Enable / disable", "Select a configured server"),
            MenuItem("test", "Test and discover tools", "Connect and list MCP tools"),
            MenuItem("remove", "Remove server", "Delete a server configuration"),
            MenuItem("back", "Back", "Return to the main menu"),
        ]).run()
        if choice in (None, "back"):
            return
        if choice == "add":
            name = _read_text(console, "  [dim]Server name =[/] ")
            command = _read_text(console, "  [dim]Executable =[/] ")
            if not name or not command:
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", name):
                console.print("  [err]✗ 名称须以字母开头，且只含字母、数字、_、-。[/]")
                wait_for_return(console)
                continue
            if name in servers:
                console.print("  [err]✗ 该名称已存在。[/]")
                wait_for_return(console)
                continue
            args = _read_json(console, "  [dim]Args (JSON array) =[/] ", [])
            if args is None or not isinstance(args, list) or not all(
                    isinstance(value, str) for value in args):
                console.print("  [err]✗ Args 必须是 JSON 字符串数组。[/]")
                wait_for_return(console)
                continue
            env = _read_json(console, "  [dim]Environment (JSON object) =[/] ", {})
            if env is None or not isinstance(env, dict):
                console.print("  [err]✗ Environment 必须是 JSON 对象。[/]")
                wait_for_return(console)
                continue
            servers[name] = {
                "command": command, "args": args, "env": env,
                "enabled": True,
            }
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)
            continue
        if choice == "toggle":
            _toggle_entry(console, servers, "MCP server")
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)
            continue
        if choice == "test":
            try:
                discovered = external_tool_schemas()
                names = [
                    schema["function"]["name"]
                    for schema in discovered
                    if schema["function"]["name"].startswith("mcp__")
                ]
                console.print(f"  [ok]✓ 已发现 {len(names)} 个 MCP 工具[/]")
                for name in names:
                    console.print(f"    [accent]{name}[/]")
            except (OSError, RuntimeError, ValueError) as exc:
                console.print(f"  [err]✗ MCP 连接失败: {exc}[/]")
            wait_for_return(console)
            continue
        if choice == "remove":
            _remove_entry(console, servers, "MCP server")
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)


def run_hooks_screen(console, copilot=None) -> None:
    while True:
        data = _load_or_report(console)
        if data is None:
            return
        hooks = data.get("hooks", [])
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ Hooks[/]")
        console.print(f"  [dim]Config: {CONFIG_PATH}[/]")
        table = Table(box=box.SIMPLE, padding=(0, 1), header_style=BRAND)
        table.add_column("Name", style="bold")
        table.add_column("Events")
        table.add_column("Status")
        for hook in hooks:
            table.add_row(
                hook.get("name", "?"),
                ", ".join(hook.get("events", [])),
                "enabled" if hook.get("enabled", True) else "disabled",
            )
        if hooks:
            console.print(table)
        else:
            console.print("  [dim]No hooks configured.[/]")
        console.print()
        choice = Menu(console, "Hooks", [
            MenuItem("add", "Add hook", "Run a command on tool lifecycle events"),
            MenuItem("toggle", "Enable / disable", "Select a configured hook"),
            MenuItem("remove", "Remove hook", "Delete a hook configuration"),
            MenuItem("back", "Back", "Return to the main menu"),
        ]).run()
        if choice in (None, "back"):
            return
        if choice == "add":
            name = _read_text(console, "  [dim]Hook name =[/] ")
            if not name or any(h.get("name") == name for h in hooks):
                continue
            events = _read_json(
                console,
                "  [dim]Events (JSON array; before_tool, after_tool) =[/] ",
                ["before_tool", "after_tool"],
            )
            command = _read_json(
                console, "  [dim]Command (JSON array) =[/] ", None
            )
            if (not isinstance(events, list)
                    or not events
                    or not set(events) <= {"before_tool", "after_tool"}
                    or not isinstance(command, list)
                    or not command
                    or not all(isinstance(value, str) for value in command)):
                console.print("  [err]✗ Hook event 或 command 无效。[/]")
                wait_for_return(console)
                continue
            args = _read_json(console, "  [dim]Args (JSON array) =[/] ", [])
            if args is None or not isinstance(args, list) or not all(
                    isinstance(value, str) for value in args):
                console.print("  [err]✗ Args 必须是 JSON 字符串数组。[/]")
                wait_for_return(console)
                continue
            hooks.append({
                "name": name, "events": events, "command": command,
                "args": args, "enabled": True,
            })
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)
            continue
        if choice == "toggle":
            _toggle_list_entry(console, hooks, "Hook")
        elif choice == "remove":
            _remove_list_entry(console, hooks, "Hook")
        try:
            save_integrations(data)
        except OSError as exc:
            console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
            wait_for_return(console)


def run_custom_tools_screen(console, copilot) -> None:
    while True:
        data = _load_or_report(console)
        if data is None:
            return
        tools = data.get("custom_tools", {})
        console.clear()
        console.print()
        console.print(f"  [bold {BRAND}]◆ Custom tools[/]")
        console.print(f"  [dim]Config: {CONFIG_PATH}[/]")
        table = Table(box=box.SIMPLE, padding=(0, 1), header_style=BRAND)
        table.add_column("Tool", style="bold")
        table.add_column("Status")
        table.add_column("Confirmation")
        for name, entry in tools.items():
            table.add_row(
                name,
                "enabled" if entry.get("enabled", True) else "disabled",
                "required" if entry.get("write", True) else "not required",
            )
        if tools:
            console.print(table)
        else:
            console.print("  [dim]No custom tools configured.[/]")
        console.print()
        choice = Menu(console, "Custom tools", [
            MenuItem("generate", "Generate with AI", "Create a tool schema and Python implementation"),
            MenuItem("toggle", "Enable / disable", "Select a custom tool"),
            MenuItem("remove", "Remove tool", "Delete a tool configuration"),
            MenuItem("back", "Back", "Return to the main menu"),
        ]).run()
        if choice in (None, "back"):
            return
        if choice == "generate":
            _generate_custom_tool(console, copilot, data)
        elif choice == "toggle":
            _toggle_entry(console, tools, "custom tool")
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)
        elif choice == "remove":
            _remove_entry(console, tools, "custom tool")
            try:
                save_integrations(data)
            except OSError as exc:
                console.print(f"  [err]✗ 保存配置失败: {exc}[/]")
                wait_for_return(console)


def _toggle_entry(console, entries: dict, label: str) -> None:
    names = list(entries)
    if not names:
        console.print(f"  [dim]没有已配置的 {label}。[/]")
        wait_for_return(console)
        return
    selected = Menu(console, f"Toggle {label}", [
        MenuItem(name, name, "enabled" if entries[name].get("enabled", True)
                 else "disabled") for name in names
    ]).run()
    if selected:
        entries[selected]["enabled"] = not entries[selected].get("enabled", True)


def _remove_entry(console, entries: dict, label: str) -> None:
    names = list(entries)
    if not names:
        console.print(f"  [dim]没有已配置的 {label}。[/]")
        wait_for_return(console)
        return
    selected = Menu(console, f"Remove {label}", [
        MenuItem(name, name) for name in names
    ]).run()
    if selected:
        from ..confirm import confirm_yes_no
        if confirm_yes_no(console, f"删除 {label} '{selected}'？",
                          default_yes=False, danger=True):
            del entries[selected]


def _toggle_list_entry(console, entries: list, label: str) -> None:
    if not entries:
        return
    selected = Menu(console, f"Toggle {label}", [
        MenuItem(entry["name"], entry["name"],
                 "enabled" if entry.get("enabled", True) else "disabled")
        for entry in entries
    ]).run()
    if selected is not None:
        entry = next(item for item in entries if item["name"] == selected)
        entry["enabled"] = not entry.get("enabled", True)


def _remove_list_entry(console, entries: list, label: str) -> None:
    if not entries:
        return
    selected = Menu(console, f"Remove {label}", [
        MenuItem(entry["name"], entry["name"]) for entry in entries
    ]).run()
    if selected is None:
        return
    entry = next(item for item in entries if item["name"] == selected)
    from ..confirm import confirm_yes_no
    if confirm_yes_no(console, f"删除 {label} '{entry['name']}'？",
                      default_yes=False, danger=True):
        entries.remove(entry)


def _generate_custom_tool(console, copilot, data: dict) -> None:
    description = _read_text(
        console, "  [dim]Describe the tool to generate =[/] "
    )
    if not description:
        return
    prompt = (
        "Design a custom function-calling tool for One Cedric. Return only "
        "valid JSON with keys name, description, parameters, and python. "
        "parameters must be an OpenAI-compatible JSON Schema object schema. "
        "python must be a complete Python script that reads a JSON object "
        "from stdin and writes its result to stdout. Use no markdown fences. "
        "Tool request: " + description
    )
    try:
        with console.status("[accent]Generating tool schema and code…[/]",
                            spinner="dots"):
            generated = copilot._once_chat([
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ])
        generated = generated.strip()
        if generated.startswith("```"):
            generated = generated.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(generated)
    except (
        json.JSONDecodeError, OSError, RuntimeError, ValueError,
        requests.exceptions.RequestException,
    ) as exc:
        console.print(f"  [err]✗ 无法生成工具: {exc}[/]")
        wait_for_return(console)
        return
    name = result.get("name")
    code = result.get("python")
    schema = result.get("parameters")
    if (not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", name)
            or not isinstance(code, str) or not code.strip()
            or not isinstance(schema, dict)
            or schema.get("type", "object") != "object"):
        console.print("  [err]✗ 生成结果的工具名、Schema 或 Python 代码无效。[/]")
        wait_for_return(console)
        return
    tools = data.setdefault("custom_tools", {})
    if name in tools:
        console.print(f"  [err]✗ 工具 '{name}' 已存在。[/]")
        wait_for_return(console)
        return
    scripts = Path.home() / ".one-cedric" / "custom_tools"
    script = scripts / f"{name}.py"
    if script.exists():
        console.print(f"  [err]✗ 脚本已存在，不会覆盖: {script}[/]")
        wait_for_return(console)
        return
    try:
        scripts.mkdir(parents=True, exist_ok=True)
        script.write_text(code, encoding="utf-8")
        tools[name] = {
            "description": str(result.get("description") or description),
            "parameters": schema,
            "command": [sys.executable, str(script)],
            "args": [],
            "enabled": True,
            "write": True,
        }
        save_integrations(data)
    except OSError as exc:
        try:
            script.unlink(missing_ok=True)
        except OSError:
            pass
        console.print(f"  [err]✗ 保存自定义工具失败: {exc}[/]")
        wait_for_return(console)
        return
    console.print(f"  [ok]✓ 已创建并启用 custom__{name}[/]")
    console.print(f"  [dim]脚本: {script}[/]")
    console.print("  [warn]工具以当前用户权限运行；执行前会请求确认。[/]")
    wait_for_return(console)
