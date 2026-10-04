"""原 ui.py —— rich UI 渲染：banner / diff / 工具行 / 动画 / 表格。"""
from __future__ import annotations

import difflib
import math
import re
import threading
import time
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Group
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ..config import (
    BRAND, ACCENT, USER_C, TOOL_C, WARN_C, PLAN_C, OK_C, ERR_C, DIM_C,
    BETA_VERSION, DIFF_CONTEXT, REASONING_MODEL_KEYWORDS,
)
from ..tools.schema import TOOLS, WRITE_TOOLS as SCHEMA_WRITE_TOOLS
from ..tools.shell import _shell_allow_display
from ..i18n import t
from .accessibility import motion_enabled


# ═══════════════════════════════════════════════════════════════════════ #
# 工具图标 / 动词 / spinner
# ═══════════════════════════════════════════════════════════════════════ #

TOOL_SPINNERS = {
    "read_file":     {"frames": ["📖", "📖", "📄", "📄"], "interval": 0.3},
    "list_files":    {"frames": ["📁", "📂", "📁", "📂"], "interval": 0.3},
    "glob":          {"frames": ["🔍", "🔎", "🔍", "🔎"], "interval": 0.15},
    "grep_regex":    {"frames": ["🔍", "🔎", "🔍", "🔎"], "interval": 0.15},
    "search_in_files": {"frames": ["🔍", "🔎", "🔍", "🔎"], "interval": 0.15},
    "file_info":     {"frames": ["ℹ️ ", "ℹ️ ", "ℹ️ "], "interval": 0.5},
    "web_fetch":     {"frames": ["🌐", "🌍", "🌎", "🌏"], "interval": 0.25},
    "http_request":  {"frames": ["🌐", "🌍", "🌎", "🌏"], "interval": 0.25},
    "web_search":    {"frames": ["🔍", "🔎", "🔍", "🔎"], "interval": 0.15},
    "web_research":  {"frames": ["🔬", "🔬", "🔬"], "interval": 0.3},
    "download":      {"frames": ["⬇️ ", "⏬", "⬇️ ", "⏬"], "interval": 0.22},
    "download_info": {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "bash":          {"frames": ["⚡ ", "⚡", "⚡⚡", " ⚡"], "interval": 0.16},
    "bash_bg":       {"frames": ["⚡ ", "⚡", "⚡⚡", " ⚡"], "interval": 0.16},
    "python_exec":   {"frames": ["🐍", "🐍", "🐍", "🐍"], "interval": 0.25},
    "python_check":  {"frames": ["🔎", "🔎", "🔎"], "interval": 0.4},
    "python_libs":   {"frames": ["📚", "📚", "📚"], "interval": 0.5},
    "git":           {"frames": ["⎇ ", "⎇ ", "⎇ "], "interval": 0.5},
    "docker":        {"frames": ["🐳", "🐳", "🐳"], "interval": 0.4},
    "sqlite":        {"frames": ["🗃️ ", "🗃️ ", "🗃️ "], "interval": 0.5},
    "json_query":    {"frames": ["🗂️ ", "🗂️ ", "🗂️ "], "interval": 0.5},
    "csv_query":     {"frames": ["🗂️ ", "🗂️ ", "🗂️ "], "interval": 0.5},
    "env_info":      {"frames": ["🔧", "🔧", "🔧"], "interval": 0.5},
    "process_info":  {"frames": ["📊", "📊", "📊"], "interval": 0.4},
    "calculate":     {"frames": ["🧮", "🧮", "🧮"], "interval": 0.5},
    "clipboard":     {"frames": ["📋", "📋", "📋"], "interval": 0.5},
    "diff_files":    {"frames": ["📑", "📑", "📑"], "interval": 0.5},
    "archive":       {"frames": ["📦", "📦", "📦"], "interval": 0.4},
    "todo":          {"frames": ["📝", "📝", "📝"], "interval": 0.5},
    "edit_file":     {"frames": ["✏️ ", "🖊️", "✏️ ", "🖊️"], "interval": 0.2},
    "write_file":    {"frames": ["✏️ ", "🖊️", "✏️ ", "🖊️"], "interval": 0.2},
    "apply_patch":   {"frames": ["🩹", "🩹", "🩹"], "interval": 0.4},
    "file_ops":      {"frames": ["📦", "📦", "📦"], "interval": 0.4},
    "find_replace":  {"frames": ["🔄", "🔄", "🔄"], "interval": 0.4},
    "docx":          {"frames": ["📄", "📄", "📄"], "interval": 0.5},
    "pdf":           {"frames": ["📕", "📕", "📕"], "interval": 0.5},
    "pptx":          {"frames": ["📊", "📊", "📊"], "interval": 0.5},
    "excel":         {"frames": ["📊", "📊", "📊"], "interval": 0.5},
    "sysop":         {"frames": ["⚙️ ", "🛠️", "⚙️ ", "🔧"], "interval": 0.2},
    "lsp_hover":     {"frames": ["💡", "💡", "💡"], "interval": 0.5},
    "lsp_definition":{"frames": ["→", "→", "→"], "interval": 0.4},
    "lsp_references":{"frames": ["🔗", "🔗", "🔗"], "interval": 0.4},
    "lsp_diagnostics":{"frames": ["🩺", "🩺", "🩺"], "interval": 0.5},
    "lsp_symbols":   {"frames": ["🔣", "🔣", "🔣"], "interval": 0.5},
    "lsp_status":    {"frames": ["🔌", "🔌", "🔌"], "interval": 0.5},
    "screen_capture":{"frames": ["📷", "📷", "📷"], "interval": 0.4},
    "screen_info":   {"frames": ["🖥️ ", "🖥️ ", "🖥️ "], "interval": 0.5},
    "mouse_action":  {"frames": ["🖱️ ", "🖱️ ", "🖱️ "], "interval": 0.4},
    "keyboard_action":{"frames": ["⌨️ ", "⌨️ ", "⌨️ "], "interval": 0.4},
    "window_action": {"frames": ["🪟", "🪟", "🪟"], "interval": 0.5},
    # 编码 / 时间 / 转换
    "base64_codec":  {"frames": ["🔤", "🔤", "🔤"], "interval": 0.5},
    "hash_text":     {"frames": ["#️⃣ ", "#️⃣ ", "#️⃣ "], "interval": 0.5},
    "url_codec":     {"frames": ["🔗", "🔗", "🔗"], "interval": 0.5},
    "password_gen":  {"frames": ["🔐", "🔐", "🔐"], "interval": 0.4},
    "jwt_decode":    {"frames": ["🔑", "🔑", "🔑"], "interval": 0.5},
    "now_info":      {"frames": ["🕐", "🕐", "🕐"], "interval": 0.5},
    "date_calc":     {"frames": ["📅", "📅", "📅"], "interval": 0.5},
    "timezone_convert":{"frames": ["🌍", "🌍", "🌍"], "interval": 0.5},
    "cron_next":     {"frames": ["⏰", "⏰", "⏰"], "interval": 0.5},
    "json_format":   {"frames": ["📐", "📐", "📐"], "interval": 0.5},
    "json_diff":     {"frames": ["📑", "📑", "📑"], "interval": 0.5},
    "csv_to_json":   {"frames": ["🔄", "🔄", "🔄"], "interval": 0.4},
    "json_to_csv":   {"frames": ["🔄", "🔄", "🔄"], "interval": 0.4},
    "md_to_html":    {"frames": ["📝", "📝", "📝"], "interval": 0.5},
    "text_stats":    {"frames": ["📊", "📊", "📊"], "interval": 0.5},
    # 图像 / 二维码
    "image_info":    {"frames": ["🖼️ ", "🖼️ ", "🖼️ "], "interval": 0.5},
    "image_process": {"frames": ["🖼️ ", "🎨", "🖼️ ", "🎨"], "interval": 0.22},
    "qrcode_generate":{"frames": ["▛▜ ", "▙▟ ", "▛▜ "], "interval": 0.2},
    "qrcode_decode":{"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "qrcode_styled":{"frames": ["▛▜ ", "▙▟ ", "▛▜ "], "interval": 0.2},
    "qrcode_batch":  {"frames": ["▛▜ ", "▙▟ ", "▛▜ "], "interval": 0.15},
    "qrcode_wifi":   {"frames": ["📶", "📶", "📶"], "interval": 0.4},
    "qrcode_vcard":  {"frames": ["📇", "📇", "📇"], "interval": 0.4},
    "qrcode_email":  {"frames": ["✉️ ", "✉️ ", "✉️ "], "interval": 0.4},
    "qrcode_sms":    {"frames": ["💬", "💬", "💬"], "interval": 0.4},
    "qrcode_geo":    {"frames": ["📍", "📍", "📍"], "interval": 0.4},
    # AST / 网络诊断
    "py_outline":    {"frames": ["🐍", "🐍", "🐍"], "interval": 0.5},
    "py_imports":    {"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "py_find_def":   {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "py_unused_imports":{"frames": ["🧹", "🧹", "🧹"], "interval": 0.5},
    "dns_lookup":    {"frames": ["🌐", "🌐", "🌐"], "interval": 0.4},
    "ssl_check":     {"frames": ["🔒", "🔒", "🔒"], "interval": 0.5},
    "http_head":     {"frames": ["📡", "📡", "📡"], "interval": 0.4},
    "pip_list":      {"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "pip_show":      {"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "disk_tree":     {"frames": ["🌳", "🌳", "🌳"], "interval": 0.5},
    # ANSI
    "ansi_strip":    {"frames": ["🧹", "🧹", "🧹"], "interval": 0.5},
    "ansi_scan":     {"frames": ["🔬", "🔬", "🔬"], "interval": 0.5},
    "ansi_to_html":  {"frames": ["🎨", "🎨", "🎨"], "interval": 0.5},
    "ansi_palette":  {"frames": ["🎨", "🎨", "🎨"], "interval": 0.5},
    # 高级文本
    "word_frequency":{"frames": ["📊", "📊", "📊"], "interval": 0.5},
    "tokenize":      {"frames": ["✂️ ", "✂️ ", "✂️ "], "interval": 0.4},
    "simplify_chinese":{"frames": ["字", "文", "字"], "interval": 0.3},
    "dedupe_lines":  {"frames": ["🧹", "🧹", "🧹"], "interval": 0.5},
    "text_similarity":{"frames": ["≋ ", "≋ ", "≋ "], "interval": 0.5},
    "strip_invisible":{"frames": ["👁️ ", "👁️ ", "👁️ "], "interval": 0.5},
    # 网络探测
    "ping_host":     {"frames": ["📡", "📡", "📡"], "interval": 0.3},
    "port_scan":     {"frames": ["🔌", "🔌", "🔌"], "interval": 0.3},
    "traceroute":    {"frames": ["🛣️ ", "🛣️ ", "🛣️ "], "interval": 0.4},
    "get_public_ip": {"frames": ["🌍", "🌍", "🌍"], "interval": 0.5},
    # 代码质量
    "ruff_check":    {"frames": ["⚡", "⚡", "⚡"], "interval": 0.4},
    "mypy_check":    {"frames": ["🔎", "🔎", "🔎"], "interval": 0.4},
    "black_check":   {"frames": ["⚫", "⚫", "⚫"], "interval": 0.5},
    "black_format":  {"frames": ["⚫", "⚫", "⚫"], "interval": 0.5},
    "eslint_check":  {"frames": ["🟨", "🟨", "🟨"], "interval": 0.4},
    # 加密
    "symmetric_encrypt":{"frames": ["🔒", "🔒", "🔒"], "interval": 0.5},
    "symmetric_decrypt":{"frames": ["🔓", "🔓", "🔓"], "interval": 0.5},
    "rsa_generate_keypair":{"frames": ["🔑", "🔑", "🔑"], "interval": 0.5},
    "rsa_encrypt":   {"frames": ["🔐", "🔐", "🔐"], "interval": 0.5},
    "rsa_decrypt":   {"frames": ["🔏", "🔏", "🔏"], "interval": 0.5},
    "hash_data":     {"frames": ["#️⃣ ", "#️⃣ ", "#️⃣ "], "interval": 0.5},
    "random_bytes":  {"frames": ["🎲", "🎲", "🎲"], "interval": 0.4},
    # 媒体
    "video_probe":   {"frames": ["🎬", "🎬", "🎬"], "interval": 0.4},
    "video_convert": {"frames": ["🎞️ ", "🎞️ ", "🎞️ "], "interval": 0.4},
    "video_clip":    {"frames": ["✂️ ", "✂️ ", "✂️ "], "interval": 0.4},
    "video_extract_audio":{"frames": ["🎵", "🎵", "🎵"], "interval": 0.4},
    "video_thumbnail":{"frames": ["🖼️ ", "🖼️ ", "🖼️ "], "interval": 0.4},
    "video_to_gif":  {"frames": ["🎞️ ", "🎞️ ", "🎞️ "], "interval": 0.4},
    "video_compress":{"frames": ["📦", "📦", "📦"], "interval": 0.4},
    "video_merge":   {"frames": ["➕", "➕", "➕"], "interval": 0.4},
    "audio_probe":   {"frames": ["🎵", "🎵", "🎵"], "interval": 0.4},
    "audio_convert": {"frames": ["🎵", "🎵", "🎵"], "interval": 0.4},
    "audio_clip":    {"frames": ["✂️ ", "✂️ ", "✂️ "], "interval": 0.4},
    "audio_volume":  {"frames": ["🔊", "🔊", "🔊"], "interval": 0.4},
    "audio_concat":  {"frames": ["➕", "➕", "➕"], "interval": 0.4},
    # PDF 高级
    "pdf_watermark": {"frames": ["💧", "💧", "💧"], "interval": 0.5},
    "pdf_compress":  {"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "pdf_extract_images":{"frames": ["🖼️ ", "🖼️ ", "🖼️ "], "interval": 0.4},
    "pdf_rotate":    {"frames": ["🔄", "🔄", "🔄"], "interval": 0.3},
    "pdf_add_page_numbers":{"frames": ["#️⃣ ", "#️⃣ ", "#️⃣ "], "interval": 0.5},
    "pdf_metadata":  {"frames": ["ℹ️ ", "ℹ️ ", "ℹ️ "], "interval": 0.5},
    # 数据库
    "postgres_query":{"frames": ["🐘", "🐘", "🐘"], "interval": 0.5},
    "postgres_list_tables":{"frames": ["🐘", "🐘", "🐘"], "interval": 0.5},
    "postgres_describe":{"frames": ["🐘", "🐘", "🐘"], "interval": 0.5},
    "mysql_query":   {"frames": ["🐬", "🐬", "🐬"], "interval": 0.5},
    "mysql_list_tables":{"frames": ["🐬", "🐬", "🐬"], "interval": 0.5},
    "mysql_describe":{"frames": ["🐬", "🐬", "🐬"], "interval": 0.5},
    "sqlite_tables": {"frames": ["🗃️ ", "🗃️ ", "🗃️ "], "interval": 0.5},
    "sqlite_schema": {"frames": ["🗃️ ", "🗃️ ", "🗃️ "], "interval": 0.5},
    "mongo_list_databases":{"frames": ["🍃", "🍃", "🍃"], "interval": 0.4},
    "mongo_list_collections":{"frames": ["🍃", "🍃", "🍃"], "interval": 0.4},
    "mongo_find":    {"frames": ["🍃", "🍃", "🍃"], "interval": 0.4},
    "mongo_aggregate":{"frames": ["🍃", "🍃", "🍃"], "interval": 0.4},
    "mongo_stats":   {"frames": ["🍃", "🍃", "🍃"], "interval": 0.4},
    # Compose / K8s
    "compose_status":{"frames": ["🐳", "🐳", "🐳"], "interval": 0.4},
    "compose_logs":  {"frames": ["📜", "📜", "📜"], "interval": 0.4},
    "compose_config":{"frames": ["⚙️ ", "⚙️ ", "⚙️ "], "interval": 0.5},
    "compose_up":    {"frames": ["⬆️ ", "⬆️ ", "⬆️ "], "interval": 0.4},
    "compose_down":  {"frames": ["⬇️ ", "⬇️ ", "⬇️ "], "interval": 0.4},
    "compose_restart":{"frames": ["🔄", "🔄", "🔄"], "interval": 0.3},
    "compose_exec":  {"frames": ["🐳", "🐳", "🐳"], "interval": 0.4},
    "k8s_get":       {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_describe":  {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_logs":      {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_contexts":  {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_apply":     {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_delete":    {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_scale":     {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_exec":      {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    "k8s_top":       {"frames": ["☸️ ", "☸️ ", "☸️ "], "interval": 0.4},
    # 高德
    "amap_geocode":  {"frames": ["📍", "📍", "📍"], "interval": 0.5},
    "amap_regeocode":{"frames": ["📍", "📍", "📍"], "interval": 0.5},
    "amap_search_poi":{"frames": ["🔍", "🔎", "🔍"], "interval": 0.2},
    "amap_poi_detail":{"frames": ["📋", "📋", "📋"], "interval": 0.5},
    "amap_around":   {"frames": ["🔍", "🔎", "🔍"], "interval": 0.2},
    "amap_input_tips":{"frames": ["✍️ ", "✍️ ", "✍️ "], "interval": 0.5},
    "amap_weather":  {"frames": ["☀️ ", "⛅ ", "☁️ ", "🌧️ "], "interval": 0.2},
    "amap_driving":  {"frames": ["🚗", "🚗", "🚗"], "interval": 0.5},
    "amap_walking":  {"frames": ["🚶", "🚶", "🚶"], "interval": 0.5},
    "amap_bicycling":{"frames": ["🚲", "🚲", "🚲"], "interval": 0.5},
    "amap_transit":  {"frames": ["🚌", "🚌", "🚌"], "interval": 0.5},
    "amap_distance": {"frames": ["📏", "📏", "📏"], "interval": 0.5},
    "amap_ip_location":{"frames": ["🌐", "🌐", "🌐"], "interval": 0.5},
    "amap_district": {"frames": ["🗺️ ", "🗺️ ", "🗺️ "], "interval": 0.5},
    # 天气
    "weather":       {"frames": ["☀️ ", "⛅ ", "☁️ ", "🌧️ ", "⛈️ ", "🌤️ "],
                      "interval": 0.18},
    # 邮件
    "email_accounts":{"frames": ["📬", "📬", "📬"], "interval": 0.5},
    "email_list_folders":{"frames": ["📁", "📁", "📁"], "interval": 0.5},
    "email_list_messages":{"frames": ["📧", "✉️ ", "📧"], "interval": 0.25},
    "email_search":  {"frames": ["🔍", "🔎", "🔍"], "interval": 0.2},
    "email_read":    {"frames": ["📖", "📖", "📖"], "interval": 0.5},
    "email_list_attachments":{"frames": ["📎", "📎", "📎"], "interval": 0.5},
    "email_download_attachment":{"frames": ["⬇️ ", "⬇️ ", "⬇️ "], "interval": 0.4},
    "email_pop_list":{"frames": ["📥", "📥", "📥"], "interval": 0.5},
    "email_pop_read":{"frames": ["📖", "📖", "📖"], "interval": 0.5},
    "email_send":    {"frames": ["✉️ ", "✉️ ", "✉️ "], "interval": 0.5},
    "email_reply":   {"frames": ["↩️ ", "↩️ ", "↩️ "], "interval": 0.5},
    "email_mark":    {"frames": ["🏷️ ", "🏷️ ", "🏷️ "], "interval": 0.5},
    "email_move":    {"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "email_delete":  {"frames": ["🗑️ ", "🗑️ ", "🗑️ "], "interval": 0.5},
    # 文件属性
    "file_attrs":    {"frames": ["🏷️ ", "🏷️ ", "🏷️ "], "interval": 0.5},
    # Agent
    "spawn_agent":   {"frames": ["🤖", "🤖", "🤖", "🤖", "🤖", "🤖", "🤖", "🤖"],
                      "interval": 0.15},
    "multi_review":  {"frames": ["🔍", "🔎", "🔍"], "interval": 0.2},
    # 记忆 / 定时 / 梦境
    "memory_remember":{"frames": ["💾", "💾", "💾"], "interval": 0.5},
    "memory_recall": {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "memory_forget": {"frames": ["🗑️ ", "🗑️ ", "🗑️ "], "interval": 0.5},
    "memory_list":   {"frames": ["📋", "📋", "📋"], "interval": 0.5},
    "cron_add":      {"frames": ["⏰", "⏰", "⏰"], "interval": 0.5},
    "cron_list":     {"frames": ["⏰", "⏰", "⏰"], "interval": 0.5},
    "cron_remove":   {"frames": ["🗑️ ", "🗑️ ", "🗑️ "], "interval": 0.5},
    "cron_enable":   {"frames": ["⏰", "⏰", "⏰"], "interval": 0.5},
    "cron_logs":     {"frames": ["📜", "📜", "📜"], "interval": 0.4},
    "dream_run":     {"frames": ["🌙", "🌙", "🌙"], "interval": 0.5},
    "dream_list":    {"frames": ["🌙", "🌙", "🌙"], "interval": 0.5},
    "dream_read":    {"frames": ["📖", "📖", "📖"], "interval": 0.5},
    "dream_stats":   {"frames": ["📊", "📊", "📊"], "interval": 0.5},
    # 成本
    "cost_anomaly":  {"frames": ["📊", "📈", "📉", "📊"], "interval": 0.3},
    "cost_export":   {"frames": ["💾", "💾", "💾"], "interval": 0.5},
    # 通知
    "notify":        {"frames": ["🔔", "🔕", "🔔"], "interval": 0.3},
    "notify_check":  {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    # 应用
    "open_app":      {"frames": ["🚀", "🚀", "🚀"], "interval": 0.4},
    "list_apps":     {"frames": ["📋", "📋", "📋"], "interval": 0.5},
    "find_app":      {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "pkg_manager_info":{"frames": ["📦", "📦", "📦"], "interval": 0.5},
    "pkg_search":    {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "pkg_list_installed":{"frames": ["📋", "📋", "📋"], "interval": 0.5},
    "pkg_install":   {"frames": ["⬇️ ", "⬇️ ", "⬇️ "], "interval": 0.4},
    "pkg_uninstall": {"frames": ["🗑️ ", "🗑️ ", "🗑️ "], "interval": 0.4},
    # OCR
    "ocr_image":     {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    "ocr_status":    {"frames": ["🔍", "🔎", "🔍"], "interval": 0.25},
    # 微信
    "wechat_status": {"frames": ["💬", "💬", "💬"], "interval": 0.4},
    "wechat_send":   {"frames": ["💬", "💬", "💬"], "interval": 0.4},
    "wechat_read_recent":{"frames": ["📖", "📖", "📖"], "interval": 0.5},
    "wechat_moments_read":{"frames": ["📷", "📷", "📷"], "interval": 0.4},
    "wechat_moments_post":{"frames": ["📷", "📷", "📷"], "interval": 0.4},
    # 定位
    "locate_rough":  {"frames": ["📍", "📍", "📍"], "interval": 0.5},
    "locate_set_exact":{"frames": ["📍", "📍", "📍"], "interval": 0.5},
    "locate_current":{"frames": ["📍", "📍", "📍"], "interval": 0.5},
    # 默认
    "_default":      {"frames": ["⚙️ ", "⚙️ ", "⚙️ "], "interval": 0.4},
}

TOOL_VERBS = {
    "read_file": "读取",
    "list_files": "列目录",
    "glob": "查找",
    "grep_regex": "正则搜索",
    "search_in_files": "搜索",
    "file_info": "文件信息",
    "web_fetch": "抓取",
    "http_request": "请求",
    "web_search": "搜索",
    "web_research": "研究",
    "download": "下载",
    "bash": "执行",
    "bash_bg": "后台执行",
    "python_exec": "Python",
    "git": "Git",
    "docker": "Docker",
    "sqlite": "SQLite",
    "json_query": "JSON",
    "csv_query": "CSV",
    "env_info": "环境",
    "process_info": "进程",
    "calculate": "计算",
    "clipboard": "剪贴板",
    "diff_files": "对比",
    "archive": "压缩",
    "todo": "待办",
    "edit_file": "编辑",
    "write_file": "写入",
    "apply_patch": "打补丁",
    "file_ops": "文件操作",
    "find_replace": "批量替换",
    "docx": "Word",
    "pdf": "PDF",
    "pptx": "PPT",
    "excel": "Excel",
    "sysop": "系统操作",
    "weather": "天气",
    "spawn_agent": "子 agent",
    "multi_review": "多 agent 审查",
    "memory_remember": "记忆",
    "memory_recall": "回忆",
    "memory_forget": "遗忘",
    "memory_list": "记忆列表",
    "dream_run": "做梦",
    "notify": "系统通知",
    "ocr_image": "OCR",
    "wechat_send": "发微信",
    "locate_rough": "定位",
    "locate_set_exact": "记录位置",
    "locate_current": "当前位置",
    "pkg_install": "安装包",
    "pkg_uninstall": "卸载包",
    "open_app": "打开",
}

TOOL_GLYPHS = {
    "read_file": "R", "list_files": "L", "glob": "⌕",
    "grep_regex": "⌕", "search_in_files": "⌕",
    "web_fetch": "↗", "http_request": "⇄", "web_search": "⌕",
    "web_research": "⌖", "download": "↓", "bash": "$",
    "bash_bg": "$", "python_exec": "Py", "git": "±",
    "docker": "▣", "sqlite": "▤", "write_file": "✎",
    "edit_file": "✎", "apply_patch": "Δ", "file_ops": "▱",
    "find_replace": "↻", "todo": "☷", "spawn_agent": "◇",
}


def _icon_for(name: str) -> dict:
    if name in TOOL_SPINNERS:
        return TOOL_SPINNERS[name]
    for k in TOOL_SPINNERS:
        if k != "_default" and name.startswith(k.rsplit("_", 1)[0] + "_"):
            return TOOL_SPINNERS[k]
    return TOOL_SPINNERS["_default"]


def get_spinner(name: str) -> Spinner:
    """返回一个 Spinner 实例。"""
    spec = _icon_for(name)
    frames = spec.get("frames", ["⚙️ "])
    icon = "▐●ᴥ●▌" if name == "_thinking" else (
        frames[0].strip() if frames else "⚙"
    )
    label = "正在等待模型响应" if name == "_thinking" else "正在处理"
    return Spinner(
        "dots",
        text=Text(
            f"  {icon}  {label}  ·  Ctrl+C 可中断",
            style=ERR_C if name == "_thinking" else TOOL_C,
        ),
        style=ERR_C if name == "_thinking" else ACCENT,
    )


# ═══════════════════════════════════════════════════════════════════════ #
# ToolStatus — 工具执行时的动态状态行
# ═══════════════════════════════════════════════════════════════════════ #

class ToolStatus:
    """上下文管理器：工具执行时的动态状态卡片。

    动画元素：
      · 星轨光环 —— 围绕工具图标的 braille 轨道旋转
      · 流光扫描条 —— 不确定进度的渐变扫描光带
      · 实时计时 —— 毫秒级耗时更新
      · 完成收尾 —— 结束瞬间闪出 ✓/✗ 状态

    用法：
        with ToolStatus(console, "read_file", "src/core.py"):
            result = do_work()
    """
    FRAME_INTERVAL = 0.1
    TRACK_LEN = 24
    BAR_LEN = 6

    def __init__(self, console, name: str, target: str = ""):
        self.console = console
        self.name = name
        self.target = target
        self._live: Live | None = None
        self._ticker: threading.Thread | None = None
        self._stop = threading.Event()
        self._frame = 0
        self._start = time.time()
        self._animate = False

    def __enter__(self):
        self._animate = motion_enabled(self.console)
        self.icon = TOOL_GLYPHS.get(self.name, "◇")
        self.label = TOOL_VERBS.get(self.name, self.name.replace("_", " "))
        self._start = time.time()

        if not self._animate:
            line = Text()
            line.append(f"  {self.icon}  ", style=f"bold {TOOL_C}")
            line.append("▐●ᴥ●▌  ", style="bold red")
            line.append(self.label, style=f"bold {TOOL_C}")
            if self.name != self.label:
                line.append(f" · {self.name}", style="dim")
            line.append(f"  {self.target or '正在处理'}",
                        style="dim")
            self.console.print(line)
            return self

        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=True,
            auto_refresh=False,
            vertical_overflow="visible",
        )
        self._live.__enter__()
        self._stop.clear()
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._ticker:
            try:
                self._ticker.join(timeout=1)
            except Exception:
                pass
        if self._live:
            try:
                # 结束前闪一次完成帧（✓ 绿色 或 ✗ 红色）
                ok = not exc[0]
                self._live.update(self._render(final=ok), refresh=True)
                time.sleep(0.09)
                self._live.__exit__(*exc)
            except Exception:
                pass
            self._live = None
        else:
            self.console.print(self._render(final=not exc[0]))

    def _tick(self):
        while not self._stop.is_set():
            self._frame += 1
            try:
                if self._live:
                    self._live.update(self._render(), refresh=True)
            except Exception:
                pass
            if self._stop.wait(self.FRAME_INTERVAL):
                return

    def _render(self, final: bool | None = None) -> Text:
        frame = self._frame

        if final is not None:
            color = OK_C if final else ERR_C
            mark = "✓" if final else "✗"
            line = Text()
            line.append("  ")
            line.append("▐●ᴥ●▌ ", style=f"bold {color}")
            line.append(self.icon + " ", style=f"bold {color}")
            line.append(self.label, style=f"bold {TOOL_C}")
            if self.name != self.label:
                line.append(f" · {self.name}", style="dim")
            if self.target:
                line.append(f"  {escape(self.target)}", style="dim")
            line.append(f"  {mark} ", style=f"bold {color}")
            elapsed = time.time() - self._start
            line.append(f"{elapsed:.1f}s", style="dim")
            return line

        elapsed = time.time() - self._start
        t = Text()
        t.append("  ")
        t.append("▐●ᴥ●▌ ", style="bold red")
        t.append(self.icon, style=f"bold {ACCENT}")
        t.append(f" {self.label}", style=f"bold {TOOL_C}")
        if self.name != self.label:
            t.append(f" · {self.name}", style="dim")
        if self.target:
            t.append(f"  {escape(self.target)}", style="dim")
        t.append(f"  {elapsed:.1f}s", style="dim")
        t.append("\n  ")
        span = self.TRACK_LEN - self.BAR_LEN
        cycle = max(1, span * 2)
        offset = frame % cycle
        pos = offset if offset <= span else cycle - offset
        brightness = 0.15 + 0.85 * (
            0.5 + 0.5 * math.sin(2 * math.pi * frame / 20)
        )
        orange = f"#{int(255 * brightness):02x}{int(140 * brightness):02x}00"
        for i in range(self.TRACK_LEN):
            if pos <= i < pos + self.BAR_LEN:
                t.append("━", style=f"bold {orange}")
            else:
                t.append("─", style=DIM_C)
        return t


# ═══════════════════════════════════════════════════════════════════════ #
# Banner
# ═══════════════════════════════════════════════════════════════════════ #

def render_banner(console, *, model: str, host: str, root: Path, session_id: str,
                  config_path: Path, project_config_path: Path,
                  plan_mode: bool, plan_active: bool,
                  preset_tag: str, active_profile: str,
                  session_title: str, title_source: str,
                  show_reasoning: bool = True,
                  think_level: str = "medium",
                  access_mode: str = "workspace") -> None:
    """显示 Banner（卡片式）。"""
    console.print()

    # ── 标题行 ──
    title = Text()
    title.append(" ✦ ", style=f"bold {BRAND}")
    title.append("One Cedric", style=f"bold {BRAND}")
    title.append(" ✦", style=f"bold {BRAND}")
    title.append(f"   {BETA_VERSION}", style="dim")
    title = Align.center(title)

    # ── 元信息（两列）──
    tbl = Table(box=None, show_header=False, padding=(0, 2))
    tbl.add_column(style="dim", justify="right")
    tbl.add_column()
    tbl.add_row("模型", f"[accent]{escape(model)}[/]")
    tbl.add_row("API", f"[accent]{escape(host)}[/]")
    tbl.add_row("目录", f"[accent]{escape(str(root))}[/]")
    tbl.add_row("会话", f"[accent]{escape(session_id)}[/]")
    tbl.add_row("全局", f"[dim]{escape(str(config_path))}[/]")
    tbl.add_row("项目", f"[dim]{escape(str(project_config_path))}[/]")
    tbl = Align.center(tbl)

    # ── 徽章 ──
    badges: list[Text] = []
    badges.append(Text("推理 " + ("开" if show_reasoning else "关"),
                       style=f"bold {OK_C if show_reasoning else DIM_C}"))
    if think_level and think_level != "medium":
        badges.append(Text(f"思考:{think_level}", style=f"bold {PLAN_C}"))
    if plan_active:
        badges.append(Text("计划执行", style=f"bold {PLAN_C}"))
    elif plan_mode:
        badges.append(Text("计划模式", style=f"bold {PLAN_C}"))
    if preset_tag == "SAFE":
        badges.append(Text("SAFE", style=f"bold {OK_C}"))
    elif preset_tag == "YOLO":
        badges.append(Text("YOLO", style=f"bold {WARN_C}"))
    if active_profile:
        badges.append(Text(f"画像:{active_profile}",
                           style=f"bold {ACCENT}"))

    from ..config import ACCESS_MODE_COLOR
    mode_label_map = {
        "workspace":     "workspace",
        "workspacesafe": "workspace · safe",
        "workspaceyolo": "workspace · yolo",
        "fullaccess":    "FULL ACCESS",
    }
    if access_mode in mode_label_map and access_mode != "workspace":
        color = {"ok": OK_C, "warn": WARN_C, "err": ERR_C, "dim": DIM_C}.get(
            ACCESS_MODE_COLOR.get(access_mode, "dim"), DIM_C)
        badges.append(Text(mode_label_map[access_mode], style=f"bold {color}"))

    badge_line = Text()
    for i, b in enumerate(badges):
        if i > 0:
            badge_line.append("   ")
        badge_line.append("［")
        badge_line.append_text(b)
        badge_line.append("］")
    badge_line = Align.center(badge_line) if badges else Text("")

    hint = Text(f"  {t('banner.hint')}", style="dim")
    hint = Align.center(hint)

    panel = Panel(
        Group(title, Rule(style=DIM_C), tbl, Text(""), badge_line, Text(""), hint),
        box=box.ROUNDED,
        border_style=BRAND,
        padding=(1, 2),
        expand=False,
    )
    console.print(panel)
    console.print()


# ═══════════════════════════════════════════════════════════════════════ #
# Diff 渲染
# ═══════════════════════════════════════════════════════════════════════ #

def render_diff(console, rel_path: str, old: str, new: str,
                is_new: bool = False, tool: str | None = None) -> None:
    """显示 diff。"""
    header = Text()
    header.append("  ◆ ", style=f"bold {WARN_C}")
    header.append(escape(rel_path), style=f"bold {WARN_C}")
    if is_new:
        header.append("  (新文件)", style="dim")
    elif tool:
        header.append(f"  · {escape(tool)}", style="dim")
    console.print()
    console.print(header)
    console.print()

    if is_new:
        lines = new.splitlines()
        shown = lines[:40]
        for i, line in enumerate(shown, 1):
            console.print(f"    [dim]{i:>4}[/] [ok]+[/] {escape(line)}")
        if len(lines) > 40:
            console.print(f"    [dim]… 还有 {len(lines) - 40} 行[/]")
        console.print()
        return

    la = old.splitlines()
    lb = new.splitlines()
    diff = list(difflib.unified_diff(la, lb, fromfile=rel_path,
                                     tofile=rel_path,
                                     lineterm="", n=DIFF_CONTEXT))

    if not diff:
        console.print("    [dim]（无变化）[/]")
        return

    line_num = 0
    for line in diff[2:]:
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+),\d+ \+(\d+),\d+ @@", line)
            if m:
                line_num = int(m.group(1))
            console.print(f"    [diff.hunk]{escape(line)}[/]")
            continue
        if line.startswith("+"):
            console.print(
                f"    [dim]{'':>4}[/] [diff.add]+[/] {escape(line[1:])}")
        elif line.startswith("-"):
            console.print(
                f"    [dim]{line_num:>4}[/] [diff.del]-[/] {escape(line[1:])}")
            line_num += 1
        else:
            content = line[1:] if line else ""
            console.print(
                f"    [dim]{line_num:>4}   {escape(content)}[/]")
            line_num += 1

    console.print()


# ═══════════════════════════════════════════════════════════════════════ #
# 工具调用摘要
# ═══════════════════════════════════════════════════════════════════════ #

def format_tool_call(name: str, args: dict, shorten_fn) -> str:
    """把工具参数格式化成一行摘要（作为 target 显示）。"""
    if not args:
        return ""

    # 特殊工具
    if name in ("read_file", "file_info", "edit_file", "write_file"):
        p = args.get("path", "")
        extra = ""
        if name == "read_file":
            sl = args.get("start_line")
            el = args.get("end_line")
            if sl or el:
                extra = f"  L{sl or '?'}-{el or '?'}"
        return f"{p}{extra}"

    if name == "bash":
        cmd = args.get("command", "")
        return shorten_fn(str(cmd)[:60])

    if name == "bash_bg":
        cmd = args.get("command", "")
        return shorten_fn(str(cmd)[:60])

    if name in ("grep_regex", "search_in_files"):
        pat = args.get("pattern", "")
        p = args.get("path", "")
        return f"{pat}  in  {p}".strip()

    if name == "glob":
        return f"{args.get('pattern', '')}  in  {args.get('path', '.')}"

    if name in ("web_fetch", "http_request"):
        return shorten_fn(args.get("url", ""))

    if name == "web_search":
        return shorten_fn(args.get("query", ""))

    if name == "web_research":
        return shorten_fn(args.get("query", ""))

    if name == "download":
        return shorten_fn(args.get("url", ""))

    if name == "download_info":
        return shorten_fn(args.get("url", ""))

    if name == "calculate":
        return shorten_fn(args.get("expression", ""))

    if name == "python_exec":
        return f"{len(str(args.get('code', '')).splitlines())} 行"

    if name in ("git", "docker"):
        sub = args.get("subcommand", "")
        extra = args.get("args") or []
        return f"{sub} {' '.join(str(x) for x in extra[:3])}".strip()

    if name == "sqlite":
        return f"{args.get('path', '')}  {shorten_fn(args.get('query', '')[:40])}"

    if name == "archive":
        return f"{args.get('op', '')}  {args.get('archive', '')}"

    if name == "file_ops":
        return f"{args.get('op', '')}  {args.get('src', '')}  {args.get('dst', '')}"

    if name == "find_replace":
        return f"{shorten_fn(args.get('pattern', '')[:30])} → {shorten_fn(args.get('replacement', '')[:30])}"

    if name == "sysop":
        return str(args.get("op", ""))

    if name.startswith("amap_"):
        for k in ("keywords", "address", "location", "origin", "city", "poi_id"):
            if k in args and args[k]:
                return str(args[k])[:40]
        return ""

    if name.startswith("email_"):
        for k in ("to", "uid", "index", "action", "dest", "account", "from_"):
            if k in args and args[k] not in ("", None):
                return str(args[k])[:40]
        return ""

    if name == "file_attrs":
        return f"{args.get('op', '')} {args.get('path', '')}".strip()

    if name == "spawn_agent":
        mode = args.get("mode", "explore")
        task = str(args.get("task", ""))[:40]
        return f"{mode} · {task}"

    if name == "multi_review":
        return str(args.get("path", ""))

    if name == "ask_user":
        return shorten_fn(str(args.get("question", ""))[:40])

    if name.startswith("qrcode_"):
        return shorten_fn(str(args.get("content", ""))[:40])

    if name.startswith("python_"):
        return ""

    if name.startswith("ansi_"):
        if args.get("file"):
            return args["file"]
        return shorten_fn(str(args.get("text", ""))[:30])

    if name in ("cost_anomaly", "cost_forecast", "cost_export"):
        return str(args.get("detail", "") or args.get("days_ahead", ""))

    if name == "ocr_image":
        return str(args.get("path", ""))

    if name.startswith("wechat_"):
        for k in ("contact", "text"):
            if k in args and args[k]:
                return str(args[k])[:30]
        return ""

    if name.startswith("locate_"):
        return str(args.get("location", ""))[:40]

    if name.startswith("pkg_"):
        return str(args.get("package", ""))

    if name == "open_app":
        return str(args.get("target", ""))

    if name == "notify" or name == "notify_actions":
        return str(args.get("title", ""))

    if name.startswith("memory_"):
        return str(args.get("key", "") or args.get("token", "") or
                   args.get("query", ""))

    if name.startswith("cron_"):
        return str(args.get("token", "") or args.get("name", ""))

    if name.startswith("dream_"):
        return str(args.get("dream_id", "") or "")

    # 通用兜底：第一个字符串字段
    for k, v in args.items():
        if isinstance(v, str) and v:
            return shorten_fn(v[:40])
    return ""


def summarize_result(name: str, result: str) -> tuple:
    """从工具结果里提取一行摘要。返回 (summary, status)。"""
    if not result:
        return "完成", "ok"

    first_line = result.splitlines()[0] if result else ""

    if result.startswith("ERROR"):
        return first_line[:80] if first_line else "失败", "error"

    if name == "read_file":
        m = re.search(r"共 (\d+) 行", result)
        if m:
            return f"{m.group(1)} 行", "ok"
        return "读取完成", "ok"

    if name == "list_files":
        m = re.search(r"共 (\d+) 项", result)
        if m:
            return f"{m.group(1)} 项", "ok"
        return "列出完成", "ok"

    if name in ("grep_regex", "search_in_files"):
        m = re.search(r"共找到 (\d+) 条", result)
        if m:
            return f"{m.group(1)} 条匹配", "ok"
        return "搜索完成", "ok"

    if name == "glob":
        m = re.search(r"（(\d+) 项", result)
        if m:
            return f"{m.group(1)} 项", "ok"
        return "查找完成", "ok"

    if name == "bash":
        m = re.search(r"退出码: (\d+)", result)
        if m:
            rc = m.group(1)
            return (f"rc={rc}", "ok" if rc == "0" else "error")
        return "执行完成", "ok"

    if name == "python_exec":
        m = re.search(r"退出码: (\d+)", result)
        if m:
            rc = m.group(1)
            return (f"rc={rc}", "ok" if rc == "0" else "error")
        return "执行完成", "ok"

    if name in ("write_file", "edit_file"):
        return first_line[:60], "ok"

    if name in ("apply_patch", "find_replace"):
        return first_line[:60], "ok"

    if name.startswith("amap_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("email_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name == "file_attrs":
        return first_line[:60] if first_line else "完成", "ok"

    if name == "spawn_agent":
        return first_line[:80] if first_line else "完成", "ok"

    if name == "multi_review":
        return first_line[:80] if first_line else "完成", "ok"

    if name.startswith("qrcode_"):
        return first_line[:60] if first_line else "生成完成", "ok"

    if name.startswith("video_") or name.startswith("audio_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("pdf_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("sysop"):
        return first_line[:60] if first_line else "完成", "ok"

    if name == "weather":
        if "---" in result:
            body = result.split("---", 1)[1].strip()
            first = body.splitlines()[0] if body else ""
            return first[:60] if first else "完成", "ok"
        return first_line[:60] if first_line else "完成", "ok"

    if name == "ocr_image":
        m = re.search(r"识别结果", result)
        if m:
            lines = result.split("--- 识别结果 ---")
            if len(lines) > 1:
                n = len(lines[1].strip().splitlines())
                return f"{n} 行文字", "ok"
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("locate_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("pkg_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name == "open_app":
        return first_line[:60] if first_line else "已启动", "ok"

    if name in ("notify", "notify_actions"):
        return first_line[:60] if first_line else "已发送", "ok"

    if name.startswith("memory_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("cron_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("dream_"):
        return first_line[:60] if first_line else "完成", "ok"

    if name.startswith("cost_"):
        return first_line[:60] if first_line else "完成", "ok"

    # 兜底
    return first_line[:80] if first_line else "完成", "ok"


def render_tool_line(console, *, name: str, target: str,
                     summary: str, status: str = "ok",
                     result: str = "") -> None:
    """Render a compact tool result card with a readable output preview."""
    color = ERR_C if status in ("error", "blocked", "rejected") else OK_C
    glyph = TOOL_GLYPHS.get(name, "◇")
    title = Text()
    title.append(f"{glyph}  {name}", style=f"bold {TOOL_C}")
    if target:
        title.append(f"  {target}", style="dim")
    title.append("  ")
    title.append("FAILED" if color == ERR_C else "COMPLETE",
                 style=f"bold {color}")

    parts = []
    if summary:
        parts.append(Text(summary, style=f"bold {color}"))
    if result:
        visible = result if len(result) <= 6000 else (
            result[:6000] + f"\n\n… output truncated ({len(result)} chars total)"
        )
        parts.append(Text(visible))
    if not parts:
        parts.append(Text("No output"))
    console.print(Panel(
        Group(*parts),
        title=title,
        title_align="left",
        border_style=color,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    ))


# ═══════════════════════════════════════════════════════════════════════ #
# 写操作确认
# ═══════════════════════════════════════════════════════════════════════ #

def render_write_prompt(console, name: str) -> None:
    """提示用户确认写操作。"""
    line = Text()
    line.append("  ")
    line.append("允许执行 ", style="dim")
    line.append(name, style=f"bold {WARN_C}")
    line.append("？", style="dim")
    console.print(line)


def render_write_prompt_help(console) -> None:
    console.print("  [dim]y=执行  n=拒绝  e=编辑  a=会话内允许[/]")


# ═══════════════════════════════════════════════════════════════════════ #
# Prompt 相关
# ═══════════════════════════════════════════════════════════════════════ #

def render_user_prompt() -> str:
    """返回 REPL 提示符。"""
    return f"[bold {USER_C}]you[/] [dim]›[/] "


def render_answer_header(console) -> None:
    """回答开始前的一行。"""
    pass


# ═══════════════════════════════════════════════════════════════════════ #
# 计划面板
# ═══════════════════════════════════════════════════════════════════════ #

def render_plan_panel(console, items: list) -> None:
    if not items:
        return
    body = Text()
    for i, item in enumerate(items, 1):
        body.append(f"  {i}. ", style=f"bold {PLAN_C}")
        body.append(f"{item}\n")
    panel = Panel(
        body,
        title=f"[bold {PLAN_C}]◆ 计划[/]",
        title_align="left",
        border_style=PLAN_C,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    )
    console.print()
    console.print(Align(panel, pad=(0, 0, 0, 2)))
    console.print()


def render_plan_prompt(console) -> None:
    console.print("  [dim]批准执行？[/]  [accent]y[/] 批准  "
                  "[err]n[/] 放弃  [accent]e[/] 编辑")


# ═══════════════════════════════════════════════════════════════════════ #
# 摘要面板
# ═══════════════════════════════════════════════════════════════════════ #

def render_summary_panel(console, summary: str) -> None:
    """显示压缩摘要。"""
    panel = Panel(
        Text(summary, style="dim"),
        title="[bold]历史摘要[/]",
        title_align="left",
        border_style=DIM_C,
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    )
    console.print()
    console.print(panel)
    console.print()


# ═══════════════════════════════════════════════════════════════════════ #
# 工具表 / 白名单表
# ═══════════════════════════════════════════════════════════════════════ #

def tools_table() -> Table:
    """所有工具的分类表格。"""
    t = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
    t.add_column("工具", style="bold")
    t.add_column("分类", style="dim")
    t.add_column("说明", style="dim")

    def _cat(name):
        if name.startswith(("read_", "write_", "edit_", "list_",
                             "glob", "grep", "search_in", "file_",
                             "apply_", "hash_", "find_dup")):
            return "文件", OK_C
        if name.startswith("web_") or name in ("http_request",
                                                 "download",
                                                 "download_info",
                                                 "get_public_ip",
                                                 "ping_host",
                                                 "port_scan",
                                                 "traceroute",
                                                 "http_head"):
            return "网络", ACCENT
        if name.startswith("lsp_"):
            return "LSP", ACCENT
        if name.startswith("docx") or name.startswith("pdf") \
                or name.startswith("pptx") or name.startswith("excel"):
            return "办公", ERR_C
        if name.startswith("sysop"):
            return "系统", ERR_C
        if name.startswith("amap_"):
            return "地图", ERR_C
        if name.startswith("email_"):
            return "邮件", ACCENT
        if name.startswith("qrcode_"):
            return "二维码", ACCENT
        if name.startswith("python_"):
            return "代码", OK_C
        if name in ("bash", "bash_bg", "git", "docker"):
            return "执行", WARN_C
        if name in ("screen_capture", "screen_info",
                    "mouse_action", "keyboard_action", "window_action"):
            return "Computer", PLAN_C
        if name in ("spawn_agent", "multi_review", "ask_user"):
            return "Agent", PLAN_C
        if name.startswith(("memory_", "cron_", "dream_")):
            return "记忆", PLAN_C
        if name.startswith(("video_", "audio_")):
            return "媒体", ACCENT
        if name in ("json_query", "csv_query", "sqlite",
                    "json_schema_validate", "sqlite_tables",
                    "sqlite_schema", "postgres_query", "mysql_query",
                    "mongo_find"):
            return "数据", WARN_C
        if name in ("image_info", "image_process"):
            return "图像", ACCENT
        if name.startswith("ansi_"):
            return "文本", WARN_C
        if name.startswith("notify"):
            return "通知", ACCENT
        if name.startswith("pkg_") or name in ("open_app",
                                                 "list_apps",
                                                 "find_app"):
            return "应用", WARN_C
        if name.startswith("cost_"):
            return "成本", WARN_C
        if name == "weather":
            return "天气", ACCENT
        if name.startswith(("k8s_", "compose_")):
            return "容器", ACCENT
        if name.startswith("ocr_"):
            return "OCR", ACCENT
        if name.startswith("wechat_"):
            return "微信", OK_C
        if name.startswith("locate_"):
            return "定位", ACCENT
        if name.startswith("file_attrs"):
            return "文件", WARN_C
        return "其他", DIM_C

    for tdef in TOOLS:
        fn = tdef["function"]
        name = fn["name"]
        desc = fn.get("description", "").split("\n")[0][:60]
        cat, color = _cat(name)
        t.add_row(name, f"[{color}]{cat}[/]", desc)
    return t


def allow_table(console) -> None:
    """显示 bash 白名单。"""
    lines = _shell_allow_display()
    t = Table(box=box.SIMPLE, header_style=f"bold {BRAND}")
    t.add_column("白名单", style="bold")
    for l in lines:
        t.add_row(l)
    console.print(t)


# ═══════════════════════════════════════════════════════════════════════ #
# 简单打印
# ═══════════════════════════════════════════════════════════════════════ #

def print_error(console, msg: str) -> None:
    console.print(f"[err]✗ {escape(msg)}[/]")


def print_warn(console, msg: str) -> None:
    console.print(f"[warn]⚠ {escape(msg)}[/]")


def print_ok(console, msg: str) -> None:
    console.print(f"[ok]✓ {escape(msg)}[/]")


def print_info(console, msg: str) -> None:
    console.print(f"[dim]{escape(msg)}[/]")


# ═══════════════════════════════════════════════════════════════════════ #
# 扩展名 → 语言
# ═══════════════════════════════════════════════════════════════════════ #

EXT_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".ps1": "powershell",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".sql": "sql",
    ".md": "markdown", ".markdown": "markdown",
    ".yml": "yaml", ".yaml": "yaml",
    ".json": "json", ".jsonl": "json",
    ".toml": "toml", ".ini": "ini",
    ".xml": "xml", ".svg": "xml",
    ".vue": "vue", ".svelte": "svelte",
    ".lua": "lua", ".r": "r",
}