"""像素小狗：带眨眼、摇尾巴、状态帧 + 用户自定义。

自定义配置文件: ~/.one-cedric/dog.toml
"""
from __future__ import annotations

import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None


DOG_PATH = Path.home() / ".one-cedric" / "dog.toml"

COLOR_MAP = {
    "green":   "\x1b[1;32m",
    "red":     "\x1b[1;31m",
    "yellow":  "\x1b[1;33m",
    "blue":    "\x1b[1;34m",
    "magenta": "\x1b[1;35m",
    "cyan":    "\x1b[1;36m",
    "white":   "\x1b[1;37m",
    "dim":     "\x1b[2m",
}

DEFAULT_FRAMES = {
    "idle": {
        "color": "green",
        "frames": [
            "▐•ᴥ•▌ ",
            "▐•ᴥ•▌~",
            "▐-ᴥ-▌~",
            "▐•ᴥ•▌~",
            "▐•ᴥ•▌ ",
            "~▐•ᴥ•▌",
            "▐-ᴥ-▌~",
            "▐•ᴥ•▌ ",
        ],
        "interval": 0.35,
    },
    "busy": {
        "color": "red",
        "frames": [
            "▐●ᴥ●▌ ",
            "▐●ᴥ●▌~",
            "▐●ᴥ●▌/",
            "▐●ᴥ●▌~",
            "▐●ᴥ●▌\\",
            "▐●ᴥ●▌~",
        ],
        "interval": 0.12,
    },
    "confirm": {
        "color": "yellow",
        "frames": [
            "▐◉ᴥ◉▌ ?",
            "▐◉ᴥ◉▌ ~",
            "▐◉ᴥ◉▌ ?",
            "▐◉ᴥ◉▌ ~",
        ],
        "interval": 0.3,
    },
    "error": {
        "color": "red",
        "frames": [
            "▐✕ᴥ✕▌ ",
            "▐✕ᴥ✕▌ ",
        ],
        "interval": 0.6,
    },
}

RESET = "\x1b[0m"
DIM = "\x1b[2m"
WHITE = "\x1b[37m"

_FRAMES_CACHE: dict | None = None


def _load_custom() -> dict:
    if not DOG_PATH.exists() or tomllib is None:
        return {}
    try:
        raw = tomllib.loads(DOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    out = {}
    for state in ("idle", "busy", "confirm", "error"):
        block = raw.get(state)
        if not isinstance(block, dict):
            continue
        frames = block.get("frames")
        if not isinstance(frames, list) or not frames:
            continue
        color = block.get("color", "green")
        if color not in COLOR_MAP:
            color = "green"
        try:
            interval = float(block.get("interval", 0.35))
        except (TypeError, ValueError):
            interval = 0.35
        out[state] = {
            "color": color,
            "frames": [str(f) for f in frames],
            "interval": interval,
        }
    return out


def _get_frames() -> dict:
    global _FRAMES_CACHE
    if _FRAMES_CACHE is None:
        merged = {k: dict(v) for k, v in DEFAULT_FRAMES.items()}
        custom = _load_custom()
        for k, v in custom.items():
            merged[k] = v
        _FRAMES_CACHE = merged
    return _FRAMES_CACHE


def reload_frames() -> None:
    global _FRAMES_CACHE
    _FRAMES_CACHE = None


def render_frame(state: str, index: int) -> str:
    frames = _get_frames()
    s = frames.get(state, frames["idle"])
    fs = s["frames"]
    if not fs:
        return ""
    frame = fs[index % len(fs)]
    color = COLOR_MAP.get(s["color"], COLOR_MAP["green"])
    return f"{color}{frame}{RESET}"


def frame_interval(state: str) -> float:
    frames = _get_frames()
    return frames.get(state, frames["idle"]).get("interval", 0.35)


def play_animation(state: str = "idle", cycles: int = 1,
                   prefix: str = "  ", suffix: str = " "):
    frames = _get_frames()
    s = frames.get(state, frames["idle"])
    fs = s["frames"]
    interval = s["interval"]

    total = len(fs) * cycles
    for i in range(total):
        frame = render_frame(state, i)
        print(f"\r{prefix}{WHITE}│{RESET} {frame}{suffix}",
              end="", flush=True)
        time.sleep(interval)
    print(f"\r{' ' * 80}\r", end="", flush=True)


def dog_inline(state: str = "idle", index: int = 0) -> str:
    return render_frame(state, index)


def export_default_toml(path: str = "") -> tuple:
    if not path:
        path = str(Path.cwd() / "dog.toml")
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out

    lines = [
        "# One Cedric 小狗帧配置",
        "# color: green/red/yellow/blue/magenta/cyan/white/dim",
        "# interval: 每帧间隔秒数",
        "# frames: 帧数组，每个字符串是一帧",
        "",
    ]
    for state in ("idle", "busy", "confirm", "error"):
        s = DEFAULT_FRAMES[state]
        lines.append(f"[{state}]")
        lines.append(f'color = "{s["color"]}"')
        lines.append(f'interval = {s["interval"]}')
        lines.append("frames = [")
        for f in s["frames"]:
            escaped = f.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    "{escaped}",')
        lines.append("]")
        lines.append("")

    try:
        out.write_text("\n".join(lines), encoding="utf-8")
        return True, str(out)
    except OSError as exc:
        return False, str(exc)


def stats() -> str:
    frames = _get_frames()
    custom = _load_custom()
    lines = [f"配置路径: {DOG_PATH}", ""]
    for state in ("idle", "busy", "confirm", "error"):
        s = frames[state]
        src = "用户" if state in custom else "默认"
        lines.append(
            f"  [{state}]  {len(s['frames'])} 帧 · "
            f"{s['color']} · {s['interval']}s · {src}"
        )
    return "\n".join(lines)