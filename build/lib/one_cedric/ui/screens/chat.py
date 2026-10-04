"""CLI chat entry menu and per-session execution preferences."""
from __future__ import annotations

from ...config import ACCESS_MODE_DESC, ACCESS_MODES
from ..menu import Menu, MenuItem


def run_cli_chat_menu(console, copilot) -> str | None:
    items = [
        MenuItem("new-session", "New session", "Start a clean conversation"),
        MenuItem("my-sessions", "My sessions", "Browse and resume saved chats"),
        MenuItem("settings", "Chat settings", "Model, access mode, and tools"),
        MenuItem("back", "Back", "Return to the main menu"),
    ]
    subtitle = f"{copilot.model}  ·  {copilot.session_id[-8:]}"
    return Menu(console, "CLI Chat", items, subtitle=subtitle).run()


def configure_new_session(console, copilot) -> bool:
    modes = [
        MenuItem(mode, mode, ACCESS_MODE_DESC.get(mode, ""))
        for mode in ACCESS_MODES
    ]
    mode = Menu(
        console, "New session · Access mode", modes,
        subtitle="Choose the workspace access policy",
    ).run()
    if mode is None:
        return False

    if mode in ("workspaceyolo", "fullaccess"):
        confirm = "auto"
    else:
        confirm = Menu(
            console, "New session · Confirmations", [
                MenuItem("ask", "Ask before actions",
                         "Confirm each write or execution"),
                MenuItem("auto", "Auto-confirm actions",
                         "Allow actions without prompting"),
            ],
            subtitle="Python execution always asks before it runs",
        ).run()
        if confirm is None:
            return False

    copilot.access_mode = mode
    copilot.auto_yes = confirm == "auto"
    copilot._new_session()
    return True
