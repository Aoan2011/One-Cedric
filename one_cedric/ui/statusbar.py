"""底栏状态：上下文 · 轮次步数 · 费用（含峰谷）· Git · 仓库环境。

由 ``ReplInputSession`` 每个提示周期刷新一次（Git 有 TTL，环境只探测
一次），渲染在输入框内部最底下一行。

开启 Nerd Font 时用 Powerline 风格渲染：每个信息段一个底色块，之间用
``\ue0b0`` 三角箭头衔接；关闭 Nerd Font（或显式 ``powerline=False``）
自动退回 `` · `` 分隔的纯文本。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text

from ..config import ACCENT, BRAND, ERR_C, OK_C, PLAN_C, USER_C, WARN_C
from . import icons
from .input_box import human_tok

#: 纯文本模式下的段分隔符
SEP = " · "

#: 状态行两侧留白（面板边框 + 行首缩进 + 余量）
_OVERHEAD = 6

#: Powerline 分段底色：按信息段种类取色（状态联动在 _*_group 里选）
PL_BG = {
    "ctx": USER_C,
    "ctx_warn": WARN_C,
    "ctx_err": ERR_C,
    "count": PLAN_C,
    "cost": OK_C,
    "git": BRAND,
    "git_dirty": WARN_C,
    "env": ACCENT,
}

#: Powerline 段内文字颜色：底色都很亮，统一近黑保证对比度
PL_FG = "#101010"

#: Powerline 分隔箭头（Nerd Font 私有区，单列宽）
PL_ARROW = "\ue0b0"

_VER_RE = re.compile(r"(\d+(?:\.\d+)+)")

#: 仓库语言标记文件 → 只用于判断「这个仓库需要什么环境」
PY_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py",
              "setup.cfg", "Pipfile", "poetry.lock", "uv.lock", ".venv")
NODE_MARKERS = ("package.json",)
RUST_MARKERS = ("Cargo.toml",)
GO_MARKERS = ("go.mod",)

#: Node 包管理器锁文件（按优先级）
PM_LOCKS = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
    ("package-lock.json", "npm"),
)


def _probe_version(args: list[str], timeout: float = 4.0) -> str:
    """跑 ``cmd --version`` 并返回首行输出；命令不存在/超时返回空串。"""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    out = (result.stdout or result.stderr or "").strip()
    return out.splitlines()[0] if out else ""


def _short_version(raw: str) -> str:
    """从版本输出里抠出主.次版本号（"v22.14.0" → "22.14"）。"""
    match = _VER_RE.search(raw or "")
    if not match:
        return ""
    return ".".join(match.group(1).split(".")[:2])


def _in_venv() -> bool:
    try:
        return sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    except Exception:
        return False


def _has(root: Path | None, name: str) -> bool:
    try:
        return bool(root and (root / name).exists())
    except OSError:
        return False


def gather_env(root, *, probe=None) -> str:
    """返回仓库环境摘要，如 ``py3.13 venv node22.14 pnpm``。

    ``probe`` 可注入（``lambda argv: "v22.14.0"``），便于测试不跑进程。
    """
    root = Path(root) if root else None
    probe = probe or _probe_version

    is_py = any(_has(root, name) for name in PY_MARKERS)
    has_node = any(_has(root, name) for name in NODE_MARKERS)
    has_rust = any(_has(root, name) for name in RUST_MARKERS)
    has_go = any(_has(root, name) for name in GO_MARKERS)

    parts: list[str] = []
    # 没有任何标记时也显示当前解释器（它就是 CLI 的运行环境）
    if is_py or not (has_node or has_rust or has_go):
        parts.append(
            "py" + ".".join(str(n) for n in sys.version_info[:2]))
        if _in_venv():
            parts.append("venv")
        elif _has(root, ".venv"):
            parts.append(".venv")
    if has_node:
        version = _short_version(probe(["node", "--version"]))
        parts.append(f"node{version}" if version else "node")
        pm = next((pm for name, pm in PM_LOCKS if _has(root, name)), "")
        if pm:
            parts.append(pm)
    if has_rust:
        version = _short_version(probe(["cargo", "--version"]))
        parts.append(f"rust{version}" if version else "rust")
    if has_go:
        version = _short_version(probe(["go", "version"]))
        parts.append(f"go{version}" if version else "go")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# 信息段构造：统一返回 {"kind", "bg", "cells": [(text, style), ...]}
# cells 的 style 供纯文本模式使用；Powerline 模式只看是否带 bold。
# --------------------------------------------------------------------------- #

def _ctx_group(ctx_used, ctx_max) -> dict:
    """上下文占用：数值高亮，占用率越高颜色越警示。"""
    used = int(ctx_used or 0)
    mx = int(ctx_max or 0)
    if mx <= 0:
        return {"kind": "ctx", "bg": PL_BG["ctx"],
                "cells": [("ctx ", "dim"),
                          (human_tok(used), f"bold {ACCENT}")]}
    ratio = used / mx
    pct_style = f"bold {ACCENT}"
    bg = PL_BG["ctx"]
    if ratio >= 0.9:
        pct_style = f"bold {ERR_C}"
        bg = PL_BG["ctx_err"]
    elif ratio >= 0.7:
        pct_style = f"bold {WARN_C}"
        bg = PL_BG["ctx_warn"]
    return {"kind": "ctx", "bg": bg,
            "cells": [
                ("ctx ", "dim"),
                (f"{human_tok(used)}/{human_tok(mx)}", ACCENT),
                (f" {ratio * 100:.0f}%", pct_style),
            ]}


def _count_group(turns, steps) -> dict:
    """轮次 / 步数（工具调用数）。"""
    return {"kind": "count", "bg": PL_BG["count"],
            "cells": [
                ("轮", "dim"),
                (str(int(turns or 0)), f"bold {ACCENT}"),
                (" ", "dim"),
                ("步", "dim"),
                (str(int(steps or 0)), f"bold {ACCENT}"),
            ]}


def _fmt_cost(cost) -> str:
    value = float(cost or 0)
    if value <= 0:
        return "$0"
    if value < 0.01:
        return f"${value:.5f}"
    if value < 1:
        return f"${value:.4f}"
    return f"${value:.2f}"


def _cost_group(cost, peak) -> dict:
    """累计费用；模型有峰谷差价时附上「谷 ×0.25 / 峰」状态。"""
    cells = [(_fmt_cost(cost), f"bold {ACCENT}")]
    if peak and peak.get("supported"):
        try:
            rate = float(peak.get("rate") or 1.0)
        except (TypeError, ValueError):
            rate = 1.0
        if peak.get("offpeak"):
            cells.append((" 谷", f"bold {OK_C}"))
            cells.append((f"×{rate:g}", f"bold {OK_C}"))
        else:
            cells.append((" 峰", "dim"))
    return {"kind": "cost", "bg": PL_BG["cost"], "cells": cells}


def _git_group(git: dict) -> dict | None:
    """Git 段：分支高亮，upstream 落后/领先暗淡，改动数警示色。"""
    branch = str((git or {}).get("branch") or "")
    if not branch:
        return None
    if git.get("detached"):
        branch = f"({branch})"
    # 关闭 Nerd Font 时 "±" 会和后面的改动数撞脸，直接写 "git"
    mark = icons.glyph("git") if icons.enabled() else "git"
    changed = int(git.get("changed") or 0)
    cells: list[tuple[str, str]] = [(f"{mark} {branch}", f"bold {ACCENT}")]
    if git.get("ahead"):
        cells.append((f" ↑{int(git['ahead'])}", "dim"))
    if git.get("behind"):
        cells.append((f" ↓{int(git['behind'])}", "dim"))
    if changed:
        cells.append((f" ±{changed}", f"bold {WARN_C}"))
    return {"kind": "git",
            "bg": PL_BG["git_dirty"] if changed else PL_BG["git"],
            "cells": cells}


def _env_group(env) -> dict | None:
    """仓库环境段：工具链版本高亮，venv 绿色，包管理器暗淡。"""
    text = str(env or "")
    if not text:
        return None
    cells: list[tuple[str, str]] = []
    for index, part in enumerate(text.split()):
        if index:
            cells.append((" ", "dim"))
        if part in ("venv", ".venv"):
            cells.append((part, f"bold {OK_C}"))
        elif part in ("pnpm", "yarn", "npm", "bun"):
            cells.append((part, "dim"))
        elif any(ch.isdigit() for ch in part):
            cells.append((part, ACCENT))
        else:
            cells.append((part, "dim"))
    return {"kind": "env", "bg": PL_BG["env"], "cells": cells}


def _group_width(cells: list) -> int:
    return sum(cell_len(text) for text, _ in cells)


def _total_width(groups: list, powerline: bool) -> int:
    content = sum(_group_width(g["cells"]) for g in groups)
    if powerline:
        # 每段首尾各 1 空格 + 段间/段尾箭头各 1 列
        return content + 3 * len(groups)
    return content + cell_len(SEP) * (len(groups) - 1)


def format_status(ctx_used, ctx_max, git, env, width, *, turns=None,
                  steps=None, cost=None, peak=None,
                  powerline: bool | None = None) -> Text | None:
    """拼出底栏状态行；放不下时从右侧整段丢弃。无内容时返回 None。"""
    if powerline is None:
        powerline = icons.enabled()
    groups: list[dict] = []
    if ctx_used is not None or ctx_max is not None:
        groups.append(_ctx_group(ctx_used, ctx_max))
    if turns is not None or steps is not None:
        groups.append(_count_group(turns, steps))
    if cost is not None:
        groups.append(_cost_group(cost, peak))
    group = _git_group(git)
    if group is not None:
        groups.append(group)
    group = _env_group(env)
    if group is not None:
        groups.append(group)
    if not groups:
        return None

    budget = max(int(width) - _OVERHEAD, 8)
    while len(groups) > 1 and _total_width(groups, powerline) > budget:
        groups.pop()

    if _total_width(groups, powerline) > budget:
        groups[0] = _crop_group(groups[0], budget, powerline)
    if not groups[0]["cells"]:
        return None

    if powerline:
        return _render_powerline(groups)
    return _render_plain(groups)


def _crop_group(group: dict, budget: int, powerline: bool) -> dict:
    """只剩一段还超宽：逐片保留，放不下的截断并补省略号。"""
    room = max(budget - 3, 1) if powerline else budget
    kept: list[tuple[str, str]] = []
    used = 0
    for text, style in group["cells"]:
        need = cell_len(text)
        if used + need <= room:
            kept.append((text, style))
            used += need
            continue
        space = room - used
        if space >= 2:
            kept.append((_crop(text, space - 1) + "…", style))
        break
    cropped = dict(group)
    cropped["cells"] = kept
    return cropped


def _render_plain(groups: list) -> Text:
    line = Text()
    for index, group in enumerate(groups):
        if index:
            line.append(SEP, style="dim")
        for text, style in group["cells"]:
            line.append(text, style=style)
    return line


def _render_powerline(groups: list) -> Text:
    line = Text()
    prev_bg = None
    for group in groups:
        bg = group["bg"]
        if prev_bg is not None:
            line.append(PL_ARROW, style=f"{prev_bg} on {bg}")
        pad_style = f"{PL_FG} on {bg}"
        line.append(" ", style=pad_style)
        for text, style in group["cells"]:
            seg = pad_style
            if style and "bold" in style:
                seg = "bold " + seg
            line.append(text, style=seg)
        line.append(" ", style=pad_style)
        prev_bg = bg
    if prev_bg is None:
        return line
    line.append(PL_ARROW, style=prev_bg)
    return line


def _crop(text: str, room: int) -> str:
    """按终端列宽截断（近似：附宽字符按 1 列处理）。"""
    out = ""
    used = 0
    for ch in text:
        width = cell_len(ch)
        if used + width > room:
            break
        out += ch
        used += width
    return out
