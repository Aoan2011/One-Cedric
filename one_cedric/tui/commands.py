"""Shell C：命令注册表。

一条命令 = 名字 + 说明 + 处理函数。命令面板（Ctrl+P）与 ``/`` 补全都读
这里，所以新增功能只需要在这里加一行。

命令名对齐 OpenCode 的面板（new session / switch model / toggle theme /
help / exit / sessions / compact / undo / settings / stats 必须都在）；
旧名字（new、theme、quit…）保留在 ``ALIASES`` 里做兼容，``run_command``
会先解析一层别名。
"""
from __future__ import annotations

from typing import Callable

Command = tuple[str, str, Callable[[], None]]


def build_commands(app) -> list[Command]:
    """按当前 App 组装命令表（名称对齐 OpenCode）。"""
    return [
        ("new session",   "Start a new thread",        app.action_new_session),
        ("sessions",      "Switch or search sessions", app.action_focus_sessions),
        ("switch model",  "Change the model",          app.action_pick_model),
        ("mode",          "Toggle Build/Plan mode",    app.action_cycle_mode),
        ("compact",       "Drop old turns & thinking", app.action_compact),
        ("undo",          "Remove last exchange",      app.action_undo),
        ("toggle theme",  "Toggle light/dark theme",   app.action_toggle_theme),
        ("thoughts",      "Expand/collapse thinking",  app.action_toggle_reasoning),
        ("sidebar",       "Toggle session sidebar",    app.action_toggle_sidebar),
        ("context",       "Toggle context panel",      app.action_toggle_context),
        ("stop",          "Stop current generation",   app.action_stop),
        ("clear",         "Clear current session",     app.action_clear),
        ("export",        "Export session (WebUI)",    app.action_export),
        ("settings",      "Show current settings",     app.action_settings),
        ("stats",         "Session statistics",        app.action_stats),
        # ── 内核直连命令（kernel_cmds.SLASH 的零参数入口，参数型
        #    命令在面板里给出用法提示；完整用法走 Composer 的 /）
        ("resume",        "Switch to another session", app.action_resume),
        ("save as",       "Save session under a name", app.action_save_as),
        ("thinking level","Reasoning depth off..ultra",app.action_think),
        ("access mode",   "allow / ask / assisted",    app.action_access_mode),
        ("auto approve",  "Auto-approve writes",       app.action_yes),
        ("shell policy",  "Free-form shell on/off",    app.action_shell),
        ("sandbox",       "Sandboxed terminal on/off", app.action_sandbox),
        ("computer use",  "Computer use on/off",       app.action_computer),
        ("tools",         "List tools",                app.action_tools),
        ("allow",         "Show permission policies",  app.action_allow),
        ("plan mode",     "Plan mode on / off / show", app.action_plan),
        ("todos",         "Todo list",                 app.action_todos),
        ("history",       "Print conversation history",app.action_history),
        ("diff",          "Workspace git diff",        app.action_diff),
        ("tags",          "Session tags",              app.action_tags),
        ("snapshots",     "Snapshot list",             app.action_snapshots),
        ("replay",        "Replay a tool call",        app.action_replay),
        ("audit",         "Security audit log",        app.action_audit),
        ("cache",         "Prompt cache stats",        app.action_cache),
        ("config",        "Print live config",         app.action_config),
        ("save config",   "Persist config (global|project)", app.action_save_config),
        ("profile",       "Show / switch profile",     app.action_profile),
        ("language",      "ui / 内核语言 zh|en",        app.action_lang),
        ("jobs",          "Background jobs",           app.action_jobs),
        ("email",         "Email integration status",  app.action_email),
        ("memory",        "Long-term memory list",     app.action_memory),
        ("cron",          "Cron jobs",                 app.action_cron),
        ("dream",         "Dream mode",                app.action_dream),
        ("asks",          "Question & answer history", app.action_asks),
        ("pricing",       "Model pricing table",       app.action_pricing),
        ("cost",          "Cost report",               app.action_cost),
        ("budget",        "Budget status",             app.action_budget),
        ("dog",           "Dog easter egg",            app.action_dog),
        ("office deps",   "Check office dependencies", app.action_office_check),
        ("help",          "Show shortcuts",            app.action_help),
        ("exit",          "Quit the TUI",              app.action_quit),
    ]


#: 旧名/slash 短名 → 面板命令名。``run_command`` 会先查这里。
ALIASES = {
    "new": "new session",
    "model": "switch model",
    "theme": "toggle theme",
    "think": "thinking level",
    "reasoning": "thoughts",
    "quit": "exit",
}

#: Slash 命令 → 命令名（Composer 里输入 ``/model`` 等同于面板里的
#: switch model）。kernel_cmds.SLASH 的命令在 submit 里优先直连内核，
#: 这里只收纯 UI 命令与需要落回面板命令的名字。
SLASH_ALIASES = {
    "/new": "new session", "/sessions": "sessions",
    "/model": "switch model", "/plan": "mode", "/stop": "stop",
    "/clear": "clear", "/compact": "compact", "/undo": "undo",
    "/export": "export", "/reasoning": "thoughts", "/theme": "toggle theme",
    "/sidebar": "sidebar", "/context": "context",
    "/settings": "settings", "/stats": "stats",
    "/help": "help", "/quit": "exit", "/exit": "exit", "/q": "exit",
    "/menu": "exit", "/back": "exit",
    "/think": "thinking level", "/yes": "auto approve",
    "/shell": "shell policy", "/sandbox": "sandbox",
    "/computer": "computer use", "/tools": "tools", "/allow": "allow",
    "/todos": "todos", "/history": "history", "/diff": "diff",
    "/tag": "tags", "/untag": "tags", "/snapshots": "snapshots",
    "/replay": "replay", "/audit": "audit", "/cache": "cache",
    "/config": "config", "/save-config": "save config",
    "/profile": "profile", "/lang": "language", "/jobs": "jobs",
    "/email": "email", "/mem": "memory", "/cron": "cron",
    "/dream": "dream", "/asks": "asks", "/pricing": "pricing",
    "/peak": "peak pricing", "/cost": "cost", "/budget": "budget",
    "/dog": "dog",
    "/office-check": "office deps",
}
