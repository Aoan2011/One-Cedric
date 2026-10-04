"""中英文界面切换。"""
from __future__ import annotations

SUPPORTED = ("zh", "en")
_DEFAULT = "zh"
_lang = _DEFAULT

MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "app.title": "One Cedric",
        "menu.chat": "对话",
        "menu.chat.desc": "与模型对话",
        "menu.cli_chat": "CLI Chat",
        "menu.cli_chat.desc": "终端会话、历史与设置",
        "menu.gateway": "网关",
        "menu.gateway.desc": "HTTP 网关 + WebUI",
        "menu.mcp": "MCP servers",
        "menu.mcp.desc": "管理 Model Context Protocol 服务",
        "menu.hooks": "Hooks",
        "menu.hooks.desc": "管理工具生命周期钩子",
        "menu.tools": "工具",
        "menu.tools.desc": "启用 / 禁用工具",
        "menu.models": "模型",
        "menu.models.desc": "模型与 API 设置",
        "menu.settings": "设置",
        "menu.settings.desc": "全局配置",
        "menu.about": "关于",
        "menu.about.desc": "版本与依赖",
        "menu.language": "语言 / Language",
        "menu.language.desc": "切换中文 / English",
        "menu.exit": "退出",
        "menu.exit.desc": "退出程序",

        "menu.hint.arrow": "↑↓ 选择  ·  Enter 确认  ·  q 返回  ·  Esc 退出",
        "menu.hint.number": "输入选项编号 + Enter  ·  q 返回",
        "menu.hint.text": "输入完整选项名称  ·  q 返回",
        "menu.select": "选择编号（q 退出）>",
        "menu.select_text": "输入选项名称（q 返回）>",
        "menu.invalid": "请输入有效编号",
        "menu.disabled": "该选项不可用",
        "menu.disabled_short": "不可用",

        "confirm.yes": "执行这次",
        "confirm.always": "本会话内允许",
        "confirm.no": "拒绝（默认）",
        "confirm.edit": "用 $EDITOR 修改",
        "confirm.help": "查看帮助",
        "confirm.hint": "↑↓←→ 选择  ·  Enter 确认  ·  1-5 快捷  ·  Esc 取消",
        "confirm.prompt": ">",
        "confirm.title": "允许执行 {name}？",

        "lang.current": "当前语言：中文",
        "lang.switched": "已切换为中文",
        "lang.usage": "用法：/lang [zh|en]",

        "common.back": "返回",
        "common.ok": "确定",
        "common.cancel": "取消",
        "common.yes": "是",
        "common.no": "否",
        "common.continue": "按 Enter 继续…",

        "banner.model": "模型",
        "banner.host": "主机",
        "banner.root": "目录",
        "banner.session": "会话",
        "banner.config": "全局配置",
        "banner.project_config": "项目配置",
        "banner.reasoning_on": "推理：开",
        "banner.reasoning_off": "推理：关",
        "banner.think": "思考",
        "banner.plan_off": "计划模式：关",
        "banner.plan_on": "计划模式：开",
        "banner.plan_exec": "计划执行中",
        "banner.preset_safe": "安全模式",
        "banner.preset_yolo": "自动模式",
        "banner.profile": "画像",
        "banner.untitled": "（未命名）",
        "banner.hint": "输入 /help 查看命令，@文件 引用文件，Ctrl+C 中断，Ctrl+D 退出",
        "banner.tools_hint": "已禁用 {n} 个工具",
    },
    "en": {
        "app.title": "One Cedric",
        "menu.chat": "Chat",
        "menu.chat.desc": "Talk to the model",
        "menu.cli_chat": "CLI Chat",
        "menu.cli_chat.desc": "Terminal sessions, history, and settings",
        "menu.gateway": "Gateway",
        "menu.gateway.desc": "HTTP gateway + WebUI",
        "menu.mcp": "MCP servers",
        "menu.mcp.desc": "Manage Model Context Protocol servers",
        "menu.hooks": "Hooks",
        "menu.hooks.desc": "Manage tool lifecycle hooks",
        "menu.tools": "Tools",
        "menu.tools.desc": "Enable / disable tools",
        "menu.models": "Models",
        "menu.models.desc": "Model & API settings",
        "menu.settings": "Settings",
        "menu.settings.desc": "Global configuration",
        "menu.about": "About",
        "menu.about.desc": "Version & dependencies",
        "menu.language": "Language / 语言",
        "menu.language.desc": "Switch Chinese / English",
        "menu.exit": "Exit",
        "menu.exit.desc": "Quit the program",

        "menu.hint.arrow": "↑↓ select  ·  Enter confirm  ·  q back  ·  Esc quit",
        "menu.hint.number": "Type a number + Enter  ·  q back",
        "menu.hint.text": "Type the full option name  ·  q back",
        "menu.select": "Select (q to quit) >",
        "menu.select_text": "Enter option name (q to go back) >",
        "menu.invalid": "Invalid selection",
        "menu.disabled": "Option disabled",
        "menu.disabled_short": "disabled",

        "confirm.yes": "Yes, once",
        "confirm.always": "Yes, always this session",
        "confirm.no": "No (default)",
        "confirm.edit": "Edit in $EDITOR",
        "confirm.help": "Help",
        "confirm.hint": "↑↓←→ select  ·  Enter confirm  ·  1-5 shortcut  ·  Esc cancel",
        "confirm.prompt": ">",
        "confirm.title": "Allow {name}?",

        "lang.current": "Language: English",
        "lang.switched": "Switched to English",
        "lang.usage": "Usage: /lang [zh|en]",

        "common.back": "Back",
        "common.ok": "OK",
        "common.cancel": "Cancel",
        "common.yes": "Yes",
        "common.no": "No",
        "common.continue": "Press Enter to continue…",

        "banner.model": "Model",
        "banner.host": "Host",
        "banner.root": "Root",
        "banner.session": "Session",
        "banner.config": "Config",
        "banner.project_config": "Project config",
        "banner.reasoning_on": "reasoning: on",
        "banner.reasoning_off": "reasoning: off",
        "banner.think": "think",
        "banner.plan_off": "plan: off",
        "banner.plan_on": "plan: on",
        "banner.plan_exec": "plan: executing",
        "banner.preset_safe": "SAFE",
        "banner.preset_yolo": "YOLO",
        "banner.profile": "profile",
        "banner.untitled": "(untitled)",
        "banner.hint": "Type /help for commands, @file to reference, Ctrl+C to interrupt, Ctrl+D to quit",
        "banner.tools_hint": "{n} tool(s) disabled",
    },
}


def set_lang(lang: str) -> bool:
    global _lang
    if lang not in SUPPORTED:
        return False
    _lang = lang
    return True


def get_lang() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    table = MESSAGES.get(_lang) or MESSAGES[_DEFAULT]
    s = table.get(key)
    if s is None:
        s = MESSAGES[_DEFAULT].get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s