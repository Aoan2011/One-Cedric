"""One Cedric UI 组件包。

原 ui.py 内容迁到 legacy.py，本文件 re-export 所有旧接口，
再导出新增的菜单、确认、小狗、输入框、进度组件。
"""
from __future__ import annotations

from .legacy import (  # noqa: F401
    render_banner, render_diff, render_tool_line,
    format_tool_call, summarize_result,
    render_write_prompt, render_write_prompt_help,
    render_user_prompt, render_answer_header,
    render_plan_panel, render_plan_prompt, render_summary_panel,
    tools_table, allow_table,
    print_error, print_warn, print_ok, print_info,
    TOOL_SPINNERS, TOOL_VERBS, get_spinner, ToolStatus,
    EXT_LANG,
)

from .keys import (
    read_key, has_readchar,
    KEY_UP, KEY_DOWN, KEY_ENTER, KEY_ESC, KEY_LEFT, KEY_RIGHT,
    KEY_BACKSPACE, KEY_TAB,
)
from .menu import Menu, MenuItem, select_menu
from .confirm import (
    confirm_yes_no, confirm_5, confirm_choice,
    confirm_input, confirm_dangerous,
    confirm_multi, multi_delete, multi_toggle,
    ask_confirm, ConfirmResult,
)
from .dog import (
    render_frame, play_animation, dog_inline,
    reload_frames as dog_reload,
    export_default_toml as dog_export,
    stats as dog_stats,
)
from .input_box import (
    ask_with_box, quick_ask, format_meta_line, human_tok,
)
from .progress import (
    ProgressMatrix, Waveform, MetricDashboard,
    celebrate, retry_with_feedback,
    BRAILLE, PULSE, WAVE_BLOCKS, SPARK_CHARS,
)

__all__ = [
    # legacy
    "render_banner", "render_diff", "render_tool_line",
    "format_tool_call", "summarize_result",
    "render_write_prompt", "render_write_prompt_help",
    "render_user_prompt", "render_answer_header",
    "render_plan_panel", "render_plan_prompt", "render_summary_panel",
    "tools_table", "allow_table",
    "print_error", "print_warn", "print_ok", "print_info",
    "TOOL_SPINNERS", "TOOL_VERBS", "get_spinner", "ToolStatus",
    "EXT_LANG",
    # keys
    "read_key", "has_readchar",
    "KEY_UP", "KEY_DOWN", "KEY_ENTER", "KEY_ESC", "KEY_LEFT", "KEY_RIGHT",
    "KEY_BACKSPACE", "KEY_TAB",
    # menu
    "Menu", "MenuItem", "select_menu",
    # confirm
    "confirm_yes_no", "confirm_5", "confirm_choice",
    "confirm_input", "confirm_dangerous",
    "confirm_multi", "multi_delete", "multi_toggle",
    "ask_confirm", "ConfirmResult",
    # dog
    "render_frame", "play_animation", "dog_inline",
    "dog_reload", "dog_export", "dog_stats",
    # input_box
    "ask_with_box", "quick_ask", "format_meta_line", "human_tok",
    # progress
    "ProgressMatrix", "Waveform", "MetricDashboard",
    "celebrate", "retry_with_feedback",
    "BRAILLE", "PULSE", "WAVE_BLOCKS", "SPARK_CHARS",
]