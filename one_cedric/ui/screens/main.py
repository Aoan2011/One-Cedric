"""主菜单。"""
from __future__ import annotations

from ..menu import Menu, MenuItem
from ...i18n import t


def run_main_menu(console, copilot) -> str:
    items = [
        MenuItem("cli-chat", t("menu.cli_chat"), t("menu.cli_chat.desc")),
        MenuItem("gateway", t("menu.gateway"), t("menu.gateway.desc")),
        MenuItem("models", t("menu.models"), t("menu.models.desc")),
        MenuItem("mcp", t("menu.mcp"), t("menu.mcp.desc")),
        MenuItem("hooks", t("menu.hooks"), t("menu.hooks.desc")),
        MenuItem("tools", t("menu.tools"), t("menu.tools.desc")),
        MenuItem("diagnose", t("menu.diagnose"), t("menu.diagnose.desc")),
        MenuItem("about", t("menu.about"), t("menu.about.desc")),
        MenuItem("quit", t("menu.exit"), t("menu.exit.desc")),
    ]

    subtitle = (f"{copilot.model}  ·  {copilot.host}  ·  "
                f"session {copilot.session_id[-4:]}")

    m = Menu(console, t("app.title"), items, subtitle=subtitle)
    return m.run() or "exit"