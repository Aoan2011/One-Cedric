"""Nerd Font 图标注册表（CLI 与 TUI 共用的唯一图标来源）。

* ``CATALOG`` 把语义键映射到 (Nerd Font 名, 回退字形)；``glyph(key)``
  按当前开关返回字形 —— 开启时是 Nerd Font 码点，关闭时是原来的
  Unicode / ASCII 字形，所以关掉图标后旧版视觉完全不变。
* 开关优先级：环境变量 ``ONE_CEDRIC_NERD_FONT`` > 配置 ``[ui].nerd_font``
  > 默认开启。CLI 由 ``OneCedric.__init__`` 调 ``configure_from_config()``，
  TUI 在 ``on_mount`` 里调一次。
* ``_CODEPOINTS`` 由 ``assets/nf-icons.json`` 生成后硬编码（启动不读盘，
  tests/test_icons.py 逐个复核）；只有未收录的名字才回退去读资产文件。
* ``replace_emoji()`` 把旧 UI 里的 emoji（spinner 帧、工具图标）换成
  Nerd Font 字形；关闭时原样返回，不改变原有行为。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: 未显式配置时的缺省开关。
DEFAULT_ENABLED = True

#: 语义键 -> (Nerd Font 名, 回退字形)。回退字形用于关闭图标时。
CATALOG: dict[str, tuple[str, str]] = {
    "abacus": ("nf-md-abacus", "🧮"),
    "apply_patch": ("nf-md-bandage", "Δ"),
    "arrow_right": ("nf-md-arrow_right", "→"),
    "arrow_up": ("nf-md-arrow_up", "⬆"),
    "bash": ("nf-md-console", "$"),
    "bell": ("nf-md-bell_outline", "🔔"),
    "bell_off": ("nf-md-bell_off_outline", "🔕"),
    "bike": ("nf-md-bike", "🚲"),
    "book": ("nf-md-book_open_page_variant", "📖"),
    "broom": ("nf-md-broom", "🧹"),
    "bulb": ("nf-md-lightbulb_outline", "💡"),
    "bus": ("nf-md-bus", "🚌"),
    "busy": ("nf-md-loading", "⟳"),
    "calendar": ("nf-md-calendar", "📅"),
    "camera": ("nf-md-camera_outline", "📷"),
    "car": ("nf-md-car", "🚗"),
    "card": ("nf-md-card_account_details_outline", "📇"),
    "chart_bar": ("nf-md-chart_bar", "📊"),
    "check": ("nf-md-check", "✔"),
    "clipboard": ("nf-md-clipboard_text", "📋"),
    "clock": ("nf-md-clock_outline", "🕐"),
    "close": ("nf-md-close", "✕"),
    "cloud": ("nf-md-cloud_outline", "☁"),
    "cog": ("nf-md-cog", "⚙"),
    "collapse": ("nf-md-chevron_right", "▸"),
    "collapse_left": ("nf-md-chevron_left", "◂"),
    "comment": ("nf-md-comment_outline", "💬"),
    # 主菜单（ui/menu.py 的语义键）
    "chat": ("nf-md-comment_outline", "◇"),
    "cli-chat": ("nf-md-comment_outline", "◇"),
    "gateway": ("nf-md-access_point", "⌁"),
    "tools": ("nf-md-wrench", "⌘"),
    "models": ("nf-md-brain", "◈"),
    "mcp": ("nf-md-link_variant", "⟡"),
    "hooks": ("nf-md-sync", "⟲"),
    "settings": ("nf-md-cog", "⚙"),
    "language": ("nf-md-translate", "文"),
    "about": ("nf-md-information", "i"),
    "exit": ("nf-md-close", "×"),
    "quit": ("nf-md-close", "×"),
    "cut": ("nf-md-content_cut", "✂"),
    "diamond": ("nf-md-diamond", "◇"),
    "diamond_filled": ("nf-md-diamond", "◆"),
    "dice": ("nf-md-dice_multiple_outline", "🎲"),
    "docker": ("nf-md-docker", "▣"),
    "dolphin": ("nf-md-dolphin", "🐬"),
    "dot": ("nf-md-circle", "●"),
    "bullet": ("nf-md-circle", "•"),
    "radio_on": ("nf-md-record_circle", "◉"),
    "dot_outline": ("nf-md-circle_outline", "○"),
    "download": ("nf-md-download", "↓"),
    "edit_file": ("nf-md-pencil_outline", "✎"),
    "edit_write": ("nf-md-square_edit_outline", "✍"),
    "elephant": ("nf-md-elephant", "🐘"),
    "email": ("nf-md-email_outline", "✉"),
    "error": ("nf-md-close_circle", "✗"),
    "error_thick": ("nf-md-close_circle", "✘"),
    "expand": ("nf-md-chevron_down", "▾"),
    "eye": ("nf-md-eye_outline", "👁"),
    "file_ops": ("nf-md-folder_multiple_outline", "▱"),
    "filmstrip": ("nf-md-filmstrip", "🎞"),
    "find_replace": ("nf-md-find_replace", "↻"),
    "folder_open": ("nf-md-folder_open_outline", "📂"),
    "git": ("nf-md-source_branch", "±"),
    "glob": ("nf-md-file_find_outline", "⌕"),
    "grep_regex": ("nf-md-magnify", "⌕"),
    "hammer": ("nf-md-hammer_screwdriver", "🛠"),
    "hand": ("nf-md-hand_back_right", "✋"),
    "hash": ("nf-md-pound", "#️⃣"),
    "history": ("nf-md-history", "↑"),
    "home": ("nf-md-home", "⌂"),
    "http_request": ("nf-md-access_point", "⇄"),
    "image": ("nf-md-image_outline", "🖼"),
    "inbox": ("nf-md-inbox_arrow_down", "📥"),
    "info": ("nf-md-information", "ℹ"),
    "k8s": ("nf-md-hexagon_outline", "☸"),
    "key": ("nf-md-key", "🔑"),
    "keyboard": ("nf-md-keyboard", "⌨"),
    "leaf": ("nf-md-leaf", "🍃"),
    "left": ("nf-md-chevron_left", "‹"),
    "letters": ("nf-md-format_letter_case", "🔤"),
    "library": ("nf-md-library", "📚"),
    "lightning": ("nf-md-flash", "⚡"),
    "link": ("nf-md-link_variant", "🔗"),
    "list_files": ("nf-md-folder_outline", "L"),
    "lock": ("nf-md-lock", "🔒"),
    "lock_open": ("nf-md-lock_open", "🔓"),
    "mailbox": ("nf-md-mailbox_outline", "📬"),
    "map": ("nf-md-map", "🗺"),
    "marker": ("nf-md-map_marker", "📍"),
    "menu": ("nf-md-menu", "☰"),
    "microscope": ("nf-md-microscope", "🔬"),
    "monitor": ("nf-md-monitor", "🖥"),
    "moon": ("nf-md-weather_night", "🌙"),
    "mouse": ("nf-md-mouse", "🖱"),
    "movie": ("nf-md-movie", "🎬"),
    "music": ("nf-md-music_note", "🎵"),
    "ok": ("nf-md-check_circle", "✓"),
    "package": ("nf-md-package_variant_closed", "📦"),
    "pages": ("nf-md-file_document_multiple_outline", "📑"),
    "palette": ("nf-md-palette", "🎨"),
    "panel": ("nf-md-page_layout_sidebar_left", "▥"),
    "paperclip": ("nf-md-paperclip", "📎"),
    "partly_cloudy": ("nf-md-weather_partly_cloudy", "⛅"),
    "pen": ("nf-md-pen", "🖊"),
    "pencil": ("nf-md-pencil_outline", "✏"),
    "plug": ("nf-md-power_plug", "🔌"),
    "plus": ("nf-md-plus", "+"),
    "prompt": ("nf-md-chevron_right", "❯"),
    "python_exec": ("nf-seti-python", "Py"),
    "rainy": ("nf-md-weather_rainy", "🌧"),
    "read_file": ("nf-md-file_document_outline", "R"),
    "reply": ("nf-md-reply", "↩"),
    "right": ("nf-md-chevron_right", "›"),
    "road": ("nf-md-road_variant", "🛣"),
    "rocket": ("nf-md-rocket", "🚀"),
    "ruler": ("nf-md-ruler", "📏"),
    "running": ("nf-md-sync", "⟳"),
    "running_half": ("nf-md-loading", "◐"),
    "save": ("nf-md-content_save_outline", "💾"),
    "script": ("nf-md-script_text", "📝"),
    "search": ("nf-md-magnify", "⌕"),
    "search_in_files": ("nf-md-text_search_variant", "⌕"),
    "sidebar": ("nf-md-view_split_vertical", "▤"),
    "signal": ("nf-md-signal", "📶"),
    "skip": ("nf-md-cancel", "⊘"),
    "spawn_agent": ("nf-md-robot", "◇"),
    "sqlite": ("nf-md-database_outline", "▤"),
    "square": ("nf-md-square", "🟨"),
    "star": ("nf-md-star_four_points", "✦"),
    "star_filled": ("nf-md-star", "★"),
    "stethoscope": ("nf-md-stethoscope", "🩺"),
    "storm": ("nf-md-weather_lightning", "⛈"),
    "sunny": ("nf-md-weather_sunny", "☀"),
    "symbol": ("nf-md-symbol", "🔣"),
    "sync": ("nf-md-sync", "🔄"),
    "tag": ("nf-md-tag_outline", "🏷"),
    "timer": ("nf-md-timer_outline", "⏰"),
    "todo": ("nf-md-format_list_checks", "☷"),
    "trash": ("nf-md-trash_can_outline", "🗑"),
    "trend_down": ("nf-md-trending_down", "📉"),
    "trend_up": ("nf-md-trending_up", "📈"),
    "volume": ("nf-md-volume_high", "🔊"),
    "walk": ("nf-md-walk", "🚶"),
    "warn": ("nf-md-alert", "⚠"),
    "water": ("nf-md-water", "💧"),
    "web_fetch": ("nf-md-web", "↗"),
    "web": ("nf-md-web", "🌐"),
    "web_research": ("nf-md-microscope", "⌖"),
    "web_search": ("nf-md-web_plus", "⌕"),
    "windows": ("nf-md-microsoft_windows", "🪟"),
    "wrench": ("nf-md-wrench", "🔧"),
    "write_file": ("nf-md-content_save_outline", "✎"),
}

#: Nerd Font 名 -> 码点。数值由 assets/nf-icons.json 生成，tests/test_icons.py 会逐个复核。
_CODEPOINTS: dict[str, int] = {
    "nf-md-abacus": 0xF16E0,
    "nf-md-access_point": 0xF0003,
    "nf-md-alert": 0xF0026,
    "nf-md-arrow_right": 0xF0054,
    "nf-md-arrow_up": 0xF005D,
    "nf-md-bandage": 0xF0DAF,
    "nf-md-bell_off_outline": 0xF0A91,
    "nf-md-bell_outline": 0xF009C,
    "nf-md-brain": 0xF09D1,
    "nf-md-bike": 0xF00A3,
    "nf-md-book_open_page_variant": 0xF05DA,
    "nf-md-broom": 0xF00E2,
    "nf-md-bus": 0xF00E7,
    "nf-md-calendar": 0xF00ED,
    "nf-md-camera_outline": 0xF0D5D,
    "nf-md-cancel": 0xF073A,
    "nf-md-car": 0xF010B,
    "nf-md-card_account_details_outline": 0xF0DAB,
    "nf-md-chart_bar": 0xF0128,
    "nf-md-check": 0xF012C,
    "nf-md-check_circle": 0xF05E0,
    "nf-md-chevron_down": 0xF0140,
    "nf-md-chevron_left": 0xF0141,
    "nf-md-chevron_right": 0xF0142,
    "nf-md-circle": 0xF0765,
    "nf-md-circle_outline": 0xF0766,
    "nf-md-clipboard_text": 0xF014D,
    "nf-md-clock_outline": 0xF0150,
    "nf-md-close": 0xF0156,
    "nf-md-close_circle": 0xF0159,
    "nf-md-cloud_outline": 0xF0163,
    "nf-md-cog": 0xF0493,
    "nf-md-comment_outline": 0xF0182,
    "nf-md-console": 0xF018D,
    "nf-md-content_cut": 0xF0190,
    "nf-md-content_save_outline": 0xF0818,
    "nf-md-database_outline": 0xF1632,
    "nf-md-diamond": 0xF0B8A,
    "nf-md-dice_multiple_outline": 0xF1156,
    "nf-md-docker": 0xF0868,
    "nf-md-dolphin": 0xF18B4,
    "nf-md-download": 0xF01DA,
    "nf-md-elephant": 0xF07C6,
    "nf-md-email_outline": 0xF01F0,
    "nf-md-eye_outline": 0xF06D0,
    "nf-md-file_document_multiple_outline": 0xF1518,
    "nf-md-file_document_outline": 0xF09EE,
    "nf-md-file_find_outline": 0xF0B97,
    "nf-md-filmstrip": 0xF0230,
    "nf-md-find_replace": 0xF06D4,
    "nf-md-flash": 0xF0241,
    "nf-md-folder_multiple_outline": 0xF0255,
    "nf-md-folder_open_outline": 0xF0DCF,
    "nf-md-folder_outline": 0xF0256,
    "nf-md-format_letter_case": 0xF0B34,
    "nf-md-format_list_checks": 0xF0756,
    "nf-md-hammer_screwdriver": 0xF1322,
    "nf-md-hand_back_right": 0xF0E47,
    "nf-md-hexagon_outline": 0xF02D9,
    "nf-md-history": 0xF02DA,
    "nf-md-home": 0xF02DC,
    "nf-md-image_outline": 0xF0976,
    "nf-md-inbox_arrow_down": 0xF02FB,
    "nf-md-information": 0xF02FC,
    "nf-md-key": 0xF0306,
    "nf-md-keyboard": 0xF030C,
    "nf-md-leaf": 0xF032A,
    "nf-md-library": 0xF0331,
    "nf-md-lightbulb_outline": 0xF0336,
    "nf-md-link_variant": 0xF0339,
    "nf-md-loading": 0xF0772,
    "nf-md-lock": 0xF033E,
    "nf-md-lock_open": 0xF033F,
    "nf-md-magnify": 0xF0349,
    "nf-md-mailbox_outline": 0xF0D8C,
    "nf-md-map": 0xF034D,
    "nf-md-map_marker": 0xF034E,
    "nf-md-menu": 0xF035C,
    "nf-md-microscope": 0xF0654,
    "nf-md-microsoft_windows": 0xF05B3,
    "nf-md-monitor": 0xF0379,
    "nf-md-mouse": 0xF037D,
    "nf-md-movie": 0xF0381,
    "nf-md-music_note": 0xF0387,
    "nf-md-package_variant_closed": 0xF03D7,
    "nf-md-page_layout_sidebar_left": 0xF06FD,
    "nf-md-palette": 0xF03D8,
    "nf-md-paperclip": 0xF03E2,
    "nf-md-pen": 0xF03EA,
    "nf-md-pencil_outline": 0xF0CB6,
    "nf-md-plus": 0xF0415,
    "nf-md-pound": 0xF0423,
    "nf-md-power_plug": 0xF06A5,
    "nf-md-reply": 0xF045A,
    "nf-md-road_variant": 0xF0462,
    "nf-md-robot": 0xF06A9,
    "nf-md-record_circle": 0xF0EC2,
    "nf-md-rocket": 0xF0463,
    "nf-md-ruler": 0xF046D,
    "nf-md-script_text": 0xF0BC2,
    "nf-md-signal": 0xF04A2,
    "nf-md-source_branch": 0xF062C,
    "nf-md-square": 0xF0764,
    "nf-md-square_edit_outline": 0xF090C,
    "nf-md-star": 0xF04CE,
    "nf-md-star_four_points": 0xF0AE2,
    "nf-md-stethoscope": 0xF04D9,
    "nf-md-symbol": 0xF1501,
    "nf-md-sync": 0xF04E6,
    "nf-md-tag_outline": 0xF04FC,
    "nf-md-text_search_variant": 0xF1A7E,
    "nf-md-timer_outline": 0xF051B,
    "nf-md-translate": 0xF05CA,
    "nf-md-trash_can_outline": 0xF0A7A,
    "nf-md-trending_down": 0xF0533,
    "nf-md-trending_up": 0xF0535,
    "nf-md-view_split_vertical": 0xF0BCC,
    "nf-md-volume_high": 0xF057E,
    "nf-md-walk": 0xF0583,
    "nf-md-water": 0xF058C,
    "nf-md-weather_lightning": 0xF0593,
    "nf-md-weather_night": 0xF0594,
    "nf-md-weather_partly_cloudy": 0xF0595,
    "nf-md-weather_rainy": 0xF0597,
    "nf-md-weather_sunny": 0xF0599,
    "nf-md-web": 0xF059F,
    "nf-md-web_plus": 0xF0033,
    "nf-md-wrench": 0xF05B7,
    "nf-seti-python": 0xE606,
}

#: 旧 UI 里的 emoji -> 语义键。`replace_emoji` 用它逐字符替换。
_EMOJI_MAP: dict[str, str] = {
    "ℹ": "info",
    "→": "arrow_right",
    "↩": "reply",
    "⌨": "keyboard",
    "⏬": "download",
    "⏰": "timer",
    "☀": "sunny",
    "☁": "cloud",
    "☸": "k8s",
    "⚙": "cog",
    "⚡": "lightning",
    "⚫": "dot",
    "⛅": "partly_cloudy",
    "⛈": "storm",
    "✂": "cut",
    "✉": "email",
    "✍": "edit_write",
    "✏": "pencil",
    "➕": "plus",
    "⬆": "arrow_up",
    "⬇": "download",
    "🌍": "web",
    "🌎": "web",
    "🌏": "web",
    "🌐": "web",
    "🌙": "moon",
    "🌤": "partly_cloudy",
    "🌧": "rainy",
    "🌳": "leaf",
    "🍃": "leaf",
    "🎞": "filmstrip",
    "🎨": "palette",
    "🎬": "movie",
    "🎲": "dice",
    "🎵": "music",
    "🏷": "tag",
    "🐍": "python_exec",
    "🐘": "elephant",
    "🐬": "dolphin",
    "🐳": "docker",
    "👁": "eye",
    "💡": "bulb",
    "💧": "water",
    "💬": "comment",
    "💾": "save",
    "📁": "list_files",
    "📂": "folder_open",
    "📄": "read_file",
    "📅": "calendar",
    "📇": "card",
    "📈": "trend_up",
    "📉": "trend_down",
    "📊": "chart_bar",
    "📋": "clipboard",
    "📍": "marker",
    "📎": "paperclip",
    "📏": "ruler",
    "📐": "ruler",
    "📑": "pages",
    "📕": "book",
    "📖": "book",
    "📚": "library",
    "📜": "script",
    "📝": "script",
    "📡": "signal",
    "📥": "inbox",
    "📦": "package",
    "📧": "email",
    "📬": "mailbox",
    "📶": "signal",
    "📷": "camera",
    "🔄": "sync",
    "🔊": "volume",
    "🔌": "plug",
    "🔍": "search",
    "🔎": "search",
    "🔏": "lock",
    "🔐": "lock",
    "🔑": "key",
    "🔒": "lock",
    "🔓": "lock_open",
    "🔔": "bell",
    "🔕": "bell_off",
    "🔗": "link",
    "🔣": "symbol",
    "🔤": "letters",
    "🔧": "wrench",
    "🔬": "microscope",
    "🕐": "clock",
    "🖊": "pen",
    "🖥": "monitor",
    "🖱": "mouse",
    "🖼": "image",
    "🗂": "file_ops",
    "🗃": "sqlite",
    "🗑": "trash",
    "🗺": "map",
    "🚀": "rocket",
    "🚌": "bus",
    "🚗": "car",
    "🚲": "bike",
    "🚶": "walk",
    "🛠": "hammer",
    "🛣": "road",
    "🟨": "square",
    "🤖": "spawn_agent",
    "🧮": "abacus",
    "🧹": "broom",
    "🩹": "apply_patch",
    "🩺": "stethoscope",
    "🪟": "windows",
}


#: 运行时状态：enabled 为 None 表示还没解析过。
_STATE: dict[str, object] = {"enabled": None, "asset": None}

_TRUTHY = {"1", "true", "yes", "on", "enable", "enabled"}
_FALSY = {"0", "false", "no", "off", "disable", "disabled"}


def _env_flag() -> bool | None:
    raw = os.environ.get("ONE_CEDRIC_NERD_FONT")
    if raw is None or not raw.strip():
        return None
    v = raw.strip().lower()
    if v in _FALSY:
        return False
    if v in _TRUTHY:
        return True
    return None


def _config_flag() -> bool | None:
    try:
        from ..storage import compose_config, default_config_path
        cfg = compose_config(default_config_path())
        raw = (cfg.get("ui") or {}).get("nerd_font")
        if isinstance(raw, bool):
            return raw
    except Exception:
        pass
    return None


def configure(flag: bool) -> None:
    """显式设置开关（测试与调用方用）。"""
    _STATE["enabled"] = bool(flag)


def configure_from_config(config: dict | None = None) -> bool:
    """按 环境变量 > config[ui].nerd_font > 默认开启 解析开关。"""
    env = _env_flag()
    if env is not None:
        _STATE["enabled"] = env
        return env
    raw = None
    if isinstance(config, dict):
        raw = (config.get("ui") or {}).get("nerd_font")
    if not isinstance(raw, bool):
        raw = _config_flag()
    _STATE["enabled"] = DEFAULT_ENABLED if raw is None else raw
    return bool(_STATE["enabled"])


def reset() -> None:
    """恢复「未解析」状态（测试用；下一次 ``enabled()`` 重新解析）。"""
    _STATE["enabled"] = None
    _STATE["asset"] = None


def enabled() -> bool:
    """当前是否使用 Nerd Font 字形（第一次调用时按配置解析）。"""
    if _STATE["enabled"] is None:
        configure_from_config()
    return bool(_STATE["enabled"])


def _asset_path() -> Path:
    # one_cedric/ui/icons.py -> 仓库根 / assets / nf-icons.json
    return Path(__file__).resolve().parents[2] / "assets" / "nf-icons.json"


def _asset() -> dict[str, int]:
    if _STATE["asset"] is None:
        table: dict[str, int] = {}
        try:
            data = json.loads(_asset_path().read_text(encoding="utf-8"))
            for entry in data:
                code = str(entry.get("codepoint") or "")
                if "code=" not in code:
                    continue
                hexstr = code.split("code=")[-1].rstrip("}").split(";")[0]
                try:
                    table[str(entry.get("name"))] = int(hexstr.strip(), 16)
                except ValueError:
                    continue
        except Exception:
            table = {}
        _STATE["asset"] = table
    return _STATE["asset"]  # type: ignore[return-value]


def _lookup(name: str) -> str:
    cp = _CODEPOINTS.get(name)
    if cp is None:
        cp = _asset().get(name)
    return chr(cp) if cp else ""


def glyph(key: str, default: str = "") -> str:
    """取语义键的字形；关闭图标或键不存在时返回回退字形。"""
    entry = CATALOG.get(key)
    if entry is None:
        return default
    fallback = entry[1] or default
    if not enabled():
        return fallback
    return _lookup(entry[0]) or fallback


def replace_emoji(text: str) -> str:
    """把文本里的旧 emoji 换成 Nerd Font 字形（关闭时原样返回）。"""
    if not text or not enabled():
        return text
    # 键帽序列 #️⃣（# + VS16 + U+20E3）整体替换：单个 '#' 是普通文本，
    # 不能进逐字符表。
    for seq in ("#\ufe0f\u20e3", "#\u20e3"):
        if seq in text:
            text = text.replace(seq, glyph("hash"))
    out: list[str] = []
    replaced = False
    for ch in text:
        if ch in ("\ufe0f", "\u20e3") and replaced:
            # emoji 变体选择符 / 键帽组合符：替换掉基字符后一并丢弃
            continue
        key = _EMOJI_MAP.get(ch)
        if key is None:
            out.append(ch)
            replaced = False
        else:
            out.append(glyph(key, ch))
            replaced = True
    return "".join(out)


#: 紧跟在 Rich 标记 ``]`` 后的状态字形 -> 语义键。只处理 ``]✓`` 这种
#: 组合：正文里的字形（例如代码、用户消息）一律不动。
_TAG_GLYPH_KEYS: dict[str, str] = {
    "✓": "ok", "✔": "check", "✗": "error", "✘": "error_thick",
    "⚠": "warn", "⊘": "skip", "ℹ": "info",
    "◆": "diamond_filled", "◇": "diamond", "◈": "models",
    "●": "dot", "○": "dot_outline", "◐": "running_half", "⟳": "running",
    "▸": "collapse", "▶": "collapse", "◂": "collapse_left",
    "›": "right", "‹": "left", "❯": "prompt", "✦": "star", "★": "star",
    "✕": "close", "×": "close", "↩": "reply", "→": "arrow_right",
    "↑": "arrow_up", "⚙": "cog", "💡": "bulb", "🌙": "moon",
}

_TAG_RE = re.compile("]([" + re.escape("".join(_TAG_GLYPH_KEYS)) + "])")


def process_markup(text: str) -> str:
    """把 ``[ok]✓`` 这类状态字形换成 Nerd Font 字形（关闭时原样返回）。

    只匹配紧跟在 ``]`` 后面的字形，所以正文、代码块里的同样字符不受影响。
    CLI 的 ``CedricConsole.print`` 每次打印字符串时都会过这里，于是
    core / cli / screens 里成百处 ``[err]✗`` / ``[ok]✓`` / ``[warn]⚠``
    一次性统一，不需要逐处改写。
    """
    if not text or "]" not in text or not enabled():
        return text
    return _TAG_RE.sub(
        lambda m: "]" + glyph(_TAG_GLYPH_KEYS[m.group(1)], m.group(1)), text)


__all__ = [
    "CATALOG",
    "DEFAULT_ENABLED",
    "configure",
    "configure_from_config",
    "enabled",
    "glyph",
    "process_markup",
    "replace_emoji",
    "reset",
]
