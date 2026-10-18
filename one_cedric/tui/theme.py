"""Shell C：色板与版本号的单一来源。

对齐 OpenCode（sst/opencode v2.0.x）TUI 的暗色 token 体系：

* 背景是带一点蓝紫的近黑，面板亮一档，侧栏/状态栏暗一档；
* 主强调色是淡紫（#8b7cf6）；选中态用更深的紫底 pill；
* 模型 / 思考档位用暖橙，Thinking 琥珀，错误红、成功绿；
* 首页 logo 与 stats 大数字共用一条四色渐变（橙→粉→紫→蓝）。

``app_css.py`` 里的 Textual CSS 变量（``$accent`` 等）必须与这里同值 ——
``tests/test_tui.py::test_theme_colors_match_css_variables`` 会强制核对。
"""
from __future__ import annotations

from importlib import metadata


def _version() -> str:
    try:
        return metadata.version("one-cedric")
    except Exception:
        try:
            from .._version import __version__
            return __version__
        except Exception:
            return "0.0.0"


#: TUI 显示的版本号（右下角常驻）。
VERSION = _version()

#: 语义色（Hex）。终端没有毛玻璃/阴影，只能靠对比度分层。
COLORS = {
    "bg": "#0f0f16",            # 主背景，近黑带一点蓝紫
    "bg-elev": "#16161f",       # 面板背景（composer/右栏/浮层）
    "bg-sunken": "#0a0a10",     # 侧栏/状态栏，暗一档
    "border": "#262631",        # 常规边框
    "border-strong": "#3d3c4d", # 浮层/composer 边框
    "text": "#e6e6ee",          # 主文本
    "text-dim": "#8f8b9d",      # 次要文本
    "text-faint": "#5d5a6a",    # 元信息
    "accent": "#8b7cf6",        # 主强调（composer 左条/选中/链接）
    "accent-deep": "#5b4bdd",   # 深一档强调（用户消息竖线/pill 底）
    "thought": "#d9a05f",       # Thought / 运行中工具
    "model": "#e8a25c",         # 模型名 / 思考档位（暖橙）
    "pill": "#2b2440",          # 选中 tab / 命令面板高亮底
    "band": "#2c3a57",          # 设置浮层选中行的蓝底
    "diff-add": "#16281d",      # diff 新增行底色
    "diff-del": "#2a1618",      # diff 删除行底色
    "danger": "#ff6b6b",        # 错误
    "ok": "#4ec98a",            # 成功/就绪
}

#: 首页 logo 与统计页共用的四色渐变（橙 → 粉 → 紫 → 蓝）。
LOGO_GRADIENT = ("#e8a25c", "#e0709f", "#a878f0", "#6f8df5")


def mix(c1: str, c2: str, t: float) -> str:
    """两个 hex 颜色按 t(0..1) 线性插值（渐变的基础件）。"""
    t = min(max(t, 0.0), 1.0)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    out = [round(x + (y - x) * t) for x, y in zip(a, b)]
    return "#%02x%02x%02x" % tuple(out)


def gradient_at(t: float) -> str:
    """在 :data:`LOGO_GRADIENT` 上取色（t 0..1，超界自动夹紧）。"""
    stops = LOGO_GRADIENT
    pos = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    return mix(stops[i], stops[i + 1], pos - i)
