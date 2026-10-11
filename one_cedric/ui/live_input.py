"""常驻底部的 REPL 输入框：鼠标定位、行编辑、回合中途排队 / 插队。

设计要点
========

* **纯逻辑可测**：``LineEditor``（光标与缓冲区）、``parse_sgr_mouse``（鼠标
  转义序列）与 ``KeyPoller``（非阻塞按键读取，读取函数可注入）都不依赖
  终端，测试里可以逐字节喂输入。
* **底部常驻**：``ReplInputSession`` 用一个长时间存活的 ``rich.Live`` 渲染
  输入框；Rich 会把同时打印到该 console 的输出显示在 Live 区域**上方**，
  所以输入框始终贴在底部，不会随输出滚走。
* **中途可插话**：回合进行中按 Enter 会先让你选「排队」还是「插队」：
    - 排队（queue）：当前回合跑完后立刻作为下一条消息处理；
    - 插队（interject）：中断当前流式输出，把这条消息立刻追加进对话，
      模型下一轮就能看到。
* **安全降级**：stdin 不是 TTY（管道、CI、重定向）时全部退回原来的
  ``console.input`` 行为，不启用鼠标、不起线程。
"""
from __future__ import annotations

import os
import select
import sys
import threading
import time
from dataclasses import dataclass, field

from rich import box
from rich.panel import Panel
from rich.text import Text

# ── 转义序列 ──────────────────────────────────────────────────────────── #
ENABLE_MOUSE = "\x1b[?1000h\x1b[?1006h"    # 普通点击 + SGR 扩展坐标
DISABLE_MOUSE = "\x1b[?1000l\x1b[?1006l"

KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_LEFT = "LEFT"
KEY_RIGHT = "RIGHT"
KEY_HOME = "HOME"
KEY_END = "END"
KEY_DELETE = "DELETE"
KEY_ENTER = "ENTER"
KEY_ESC = "ESC"
KEY_BACKSPACE = "BACKSPACE"
KEY_TAB = "TAB"
KEY_INTERRUPT = "INTERRUPT"

#: 决策：中途消息如何处理
DECISION_NONE = "none"
DECISION_QUEUE = "queue"
DECISION_INTERJECT = "interject"
DECISION_CANCEL = "cancel"


# ═══════════════════════════════════════════════════════════════════════ #
# 鼠标
# ═══════════════════════════════════════════════════════════════════════ #

def parse_sgr_mouse(seq: str) -> dict | None:
    """解析 SGR 鼠标序列 ``\\x1b[<b;x;yM`` → dict，非鼠标序列返回 None。

    返回 ``{"button": int, "x": int, "y": int, "press": bool}``，
    x/y 为 1-based 终端列/行（与转义序列一致）。
    """
    if not seq.startswith("\x1b[<"):
        return None
    final = seq[-1:]
    if final not in ("M", "m"):
        return None
    body = seq[3:-1]
    parts = body.split(";")
    if len(parts) != 3:
        return None
    try:
        button, x, y = (int(p) for p in parts)
    except ValueError:
        return None
    return {"button": button, "x": x, "y": y, "press": final == "M"}


def is_left_click(event: dict | None) -> bool:
    if not event or not event.get("press"):
        return False
    # SGR: 0 = 左键按下；带修饰位（shift/alt/ctrl）时低两位仍表示按键
    return (event["button"] & 0b11) == 0 and not (event["button"] & 0b1100000)


@dataclass
class MouseMode:
    """进入/退出鼠标追踪的上下文管理器（仅 TTY 下生效）。"""

    console: object = None
    enabled: bool = False

    def __enter__(self):
        if _stdout_is_tty() and self.console is not None:
            try:
                self.console.file.write(ENABLE_MOUSE)
                self.console.file.flush()
                self.enabled = True
            except Exception:
                self.enabled = False
        return self

    def __exit__(self, *exc):
        if self.enabled and self.console is not None:
            try:
                self.console.file.write(DISABLE_MOUSE)
                self.console.file.flush()
            except Exception:
                pass
        self.enabled = False
        return False


# ═══════════════════════════════════════════════════════════════════════ #
# 行编辑
# ═══════════════════════════════════════════════════════════════════════ #

@dataclass
class LineEditor:
    """单行文本编辑器（无终端依赖，可直接单测）。"""

    buffer: str = ""
    cursor: int = 0
    #: 输入框左侧提示串的宽度，用于把鼠标列映射到字符下标
    prompt_width: int = 2

    # ── 修改 ──────────────────────────────────────────────────────────── #
    def insert(self, text: str) -> None:
        if not text:
            return
        text = text.replace("\r", "").replace("\n", "")
        self.buffer = self.buffer[:self.cursor] + text + self.buffer[self.cursor:]
        self.cursor += len(text)

    def newline(self) -> bool:
        """返回 True 表示用户按下了 Enter（提交）。"""
        return True

    def backspace(self) -> None:
        if self.cursor > 0:
            self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]
            self.cursor -= 1

    def delete(self) -> None:
        if self.cursor < len(self.buffer):
            self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]

    def clear(self) -> None:
        self.buffer = ""
        self.cursor = 0

    # ── 移动 ──────────────────────────────────────────────────────────── #
    def left(self) -> None:
        self.cursor = max(0, self.cursor - 1)

    def right(self) -> None:
        self.cursor = min(len(self.buffer), self.cursor + 1)

    def home(self) -> None:
        self.cursor = 0

    def end(self) -> None:
        self.cursor = len(self.buffer)

    def word_left(self) -> None:
        i = self.cursor
        while i > 0 and self.buffer[i - 1].isspace():
            i -= 1
        while i > 0 and not self.buffer[i - 1].isspace():
            i -= 1
        self.cursor = i

    def word_right(self) -> None:
        i = self.cursor
        n = len(self.buffer)
        while i < n and not self.buffer[i].isspace():
            i += 1
        while i < n and self.buffer[i].isspace():
            i += 1
        self.cursor = i

    def kill_to_end(self) -> None:
        self.buffer = self.buffer[:self.cursor]

    def kill_to_start(self) -> None:
        self.buffer = self.buffer[self.cursor:]
        self.cursor = 0

    # ── 鼠标 ──────────────────────────────────────────────────────────── #
    def locate(self, column: int) -> None:
        """把光标移到鼠标点击所在的字符位置（1-based 终端列）。"""
        idx = int(column) - 1 - self.prompt_width
        self.cursor = max(0, min(len(self.buffer), idx))

    # ── 渲染 ──────────────────────────────────────────────────────────── #
    def split(self) -> tuple[str, str, str]:
        return (self.buffer[:self.cursor],
                self.buffer[self.cursor:self.cursor + 1],
                self.buffer[self.cursor + 1:])

    def __len__(self) -> int:
        return len(self.buffer)


def apply_key(editor: LineEditor, key: str) -> str:
    """把一次按键作用到编辑器上。

    返回：``"submit"`` / ``"edit"`` / ``"escape"`` / ``"interrupt"`` / ``"noop"``。
    """
    if key == KEY_ENTER:
        return "submit"
    if key == KEY_ESC:
        return "escape"
    if key == KEY_INTERRUPT:
        return "interrupt"
    if key == KEY_BACKSPACE:
        editor.backspace()
    elif key == KEY_DELETE:
        editor.delete()
    elif key == KEY_LEFT:
        editor.left()
    elif key == KEY_RIGHT:
        editor.right()
    elif key == KEY_HOME:
        editor.home()
    elif key == KEY_END:
        editor.end()
    else:
        editor.insert(key)
    return "edit"


# ═══════════════════════════════════════════════════════════════════════ #
# 非阻塞按键读取
# ═══════════════════════════════════════════════════════════════════════ #

def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _stdout_is_tty() -> bool:
    try:
        return bool(sys.stdout and sys.stdout.isatty())
    except Exception:
        return False


#: VT 转义序列 → 统一键名
_CSI_KEYS = {
    "[A": KEY_UP, "[B": KEY_DOWN, "[C": KEY_RIGHT, "[D": KEY_LEFT,
    "[H": KEY_HOME, "[F": KEY_END, "[1~": KEY_HOME, "[4~": KEY_END,
    "[3~": KEY_DELETE, "[7~": KEY_HOME, "[8~": KEY_END,
    "OA": KEY_UP, "OB": KEY_DOWN, "OC": KEY_RIGHT, "OD": KEY_LEFT,
    "OH": KEY_HOME, "OF": KEY_END,
}

#: Windows 扩展键第二字节 → 统一键名（msvcrt 路径）
_WIN_EXT_KEYS = {
    "H": KEY_UP, "P": KEY_DOWN, "K": KEY_LEFT, "M": KEY_RIGHT,
    "G": KEY_HOME, "O": KEY_END, "S": KEY_DELETE,
}


class KeyPoller:
    """从字符流里非阻塞地取出按键。

    ``read_char`` 可注入，便于测试与替换后端；默认在 Windows 用 msvcrt，
    其它平台用 readchar/select。
    """

    def __init__(self, read_char=None, has_input=None):
        self._read_char = read_char or self._default_read_char
        self._has_input = has_input or self._default_has_input
        self._pending = ""

    # ── 后端 ──────────────────────────────────────────────────────────── #
    @staticmethod
    def _default_has_input() -> bool:
        if os.name == "nt":
            try:
                import msvcrt
                return bool(msvcrt.kbhit())
            except Exception:
                return False
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            return bool(ready)
        except Exception:
            return False

    @staticmethod
    def _default_read_char() -> str:
        if os.name == "nt":
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                ch += msvcrt.getwch()
            return ch
        return sys.stdin.read(1)

    # ── 解析 ──────────────────────────────────────────────────────────── #
    def feed(self, chunk: str) -> None:
        """把已读到的字符追加进缓冲区（测试用）。"""
        self._pending += chunk

    def pop_key(self) -> str | None:
        """从缓冲区取出一个按键；缓冲区不足以判定时返回 None。"""
        buf = self._pending
        if not buf:
            return None

        # Windows 扩展键
        if buf[0] in ("\x00", "\xe0"):
            if len(buf) < 2:
                return None
            self._pending = buf[2:]
            return _WIN_EXT_KEYS.get(buf[1], "noop")

        if buf[0] == "\x1b":
            # SGR 鼠标：ESC [ < ... M/m
            if buf.startswith("\x1b[<"):
                end = None
                for i, ch in enumerate(buf):
                    if i >= 3 and ch in ("M", "m"):
                        end = i
                        break
                if end is None:
                    return None
                seq, self._pending = buf[:end + 1], buf[end + 1:]
                event = parse_sgr_mouse(seq)
                if event is None:
                    return "noop"
                if is_left_click(event):
                    return f"MOUSE_LEFT:{event['x']}"
                return "MOUSE_OTHER"
            # 方向键等 CSI 序列（键名不含 ESC，按 buf[1:] 查表）
            if buf.startswith("\x1b["):
                if len(buf) < 3:
                    return None
                for length in (3, 4):
                    if len(buf) >= length:
                        cand = buf[1:length]
                        if cand in _CSI_KEYS:
                            self._pending = buf[length:]
                            return _CSI_KEYS[cand]
                if len(buf) < 4:
                    return None
                self._pending = buf[3:]
                return "noop"
            if buf.startswith("\x1bO"):
                if len(buf) < 3:
                    return None
                self._pending = buf[3:]
                return _CSI_KEYS.get(buf[1:3], "noop")
            self._pending = buf[1:]
            return KEY_ESC

        if buf[0] in ("\r", "\n"):
            self._pending = buf[1:]
            return KEY_ENTER
        if buf[0] == "\t":
            self._pending = buf[1:]
            return KEY_TAB
        if buf[0] in ("\x08", "\x7f"):
            self._pending = buf[1:]
            return KEY_BACKSPACE
        if buf[0] == "\x03":
            self._pending = buf[1:]
            return KEY_INTERRUPT

        self._pending = buf[1:]
        ch = buf[0]
        return ch if ch.isprintable() else "noop"

    def poll(self) -> list[str]:
        """取走当前所有可用按键（不阻塞）。"""
        keys = []
        guard = 0
        while self._has_input() and guard < 512:
            guard += 1
            try:
                self._pending += self._read_char()
            except Exception:
                break
        while True:
            key = self.pop_key()
            if key is None:
                break
            keys.append(key)
        return keys


# ═══════════════════════════════════════════════════════════════════════ #
# 回合中途消息
# ═══════════════════════════════════════════════════════════════════════ #

@dataclass
class MidTurnQueue:
    """回合中途输入的消息：排队 or 插队。"""

    queued: list = field(default_factory=list)
    interject: str = ""

    def enqueue(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.queued.append(text)

    def set_interject(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.interject = text

    def take_interject(self) -> str:
        text, self.interject = self.interject, ""
        return text

    def take_queued(self) -> list:
        items, self.queued = self.queued, []
        return items

    @property
    def has_interject(self) -> bool:
        return bool(self.interject)


# ═══════════════════════════════════════════════════════════════════════ #
# 渲染
# ═══════════════════════════════════════════════════════════════════════ #

def render_prompt(editor: LineEditor, *, state: str = "idle",
                  queue_len: int = 0, pending_decision: bool = False,
                  model: str = "", width: int = 80):
    """渲染底部输入框（返回 rich 可渲染对象）。"""
    before, at, after = editor.split()
    line = Text()
    line.append("  ❯ ", style="bold #d97757")
    line.append(before)
    if at:
        line.append(at, style="reverse")
        line.append(after)
    else:
        line.append(" ", style="reverse")

    hints = []
    if pending_decision:
        hints.append("Enter 排队 · i 插队 · Esc 取消")
    else:
        if state == "busy":
            hints.append("回合进行中，可直接输入")
        if queue_len:
            hints.append(f"已排队 {queue_len} 条")
        hints.append("Ctrl+C 中断")

    border = {"idle": "#d97757", "busy": "#4ec9b0",
              "decision": "#e0af68"}.get(
        "decision" if pending_decision else state, "#d97757")

    title = "One Cedric"
    if state == "busy":
        title = "One Cedric ⟳ 运行中"
    if model:
        title = f"{title} · {model}"

    body = Text()
    body.append_text(line)
    body.append("\n")
    body.append("  " + " · ".join(hints), style="dim")

    return Panel(body, title=title, title_align="left",
                 border_style=border, box=box.ROUNDED,
                 padding=(0, 0), expand=False)


# ═══════════════════════════════════════════════════════════════════════ #
# 会话
# ═══════════════════════════════════════════════════════════════════════ #

class ReplInputSession:
    """把「底部常驻输入框 + 鼠标 + 中途插话」打包给 REPL 使用。

    只有在 stdin/stdout 都是 TTY 时才真正启用；否则 ``enabled`` 为 False，
    调用方应回退到 ``console.input``。
    """

    def __init__(self, console, *, poll_interval: float = 0.05):
        self.console = console
        self.queue = MidTurnQueue()
        self.editor = LineEditor()
        self.poller = KeyPoller()
        self.state = "idle"
        self.pending_decision = False
        self._decision_text = ""
        self.poll_interval = poll_interval
        self._mouse = None
        self._live = None
        self.enabled = _stdin_is_tty() and _stdout_is_tty()

    # ── 生命周期 ──────────────────────────────────────────────────────── #
    def start(self) -> None:
        if not self.enabled:
            return
        from rich.live import Live
        # 鼠标追踪必须保证被关掉，否则终端会一直处于鼠标上报模式。
        # atexit 兜底覆盖所有 return 路径（包括异常退出）。
        import atexit
        atexit.register(self.stop)
        self._mouse = MouseMode(self.console).__enter__()
        self._live = Live(self.render(), console=self.console,
                          refresh_per_second=10, transient=False,
                          auto_refresh=True)
        self._live.__enter__()

    def stop(self) -> None:
        if self._live is not None:
            try:
                self._live.__exit__(None, None, None)
            except Exception:
                pass
            self._live = None
        if self._mouse is not None:
            try:
                self._mouse.__exit__(None, None, None)
            except Exception:
                pass
            self._mouse = None

    def refresh(self) -> None:
        if self._live is not None:
            try:
                self._live.update(self.render())
            except Exception:
                pass

    def pause(self) -> None:
        """其它界面（设置、菜单）要接管屏幕时先把输入框收起来。"""
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass

    def resume(self) -> None:
        if self._live is not None:
            try:
                self._live.start()
            except Exception:
                pass

    # ── 渲染 ──────────────────────────────────────────────────────────── #
    def render(self):
        return render_prompt(
            self.editor,
            state=self.state,
            queue_len=len(self.queue.queued),
            pending_decision=self.pending_decision,
            model=getattr(self, "model", ""),
        )

    # ── 按键处理 ──────────────────────────────────────────────────────── #
    def handle_key(self, key: str) -> str | None:
        """处理一个按键。

        返回 ``None`` 或提交的文本（表示用户按 Enter 提交了一行）。
        """
        if key.startswith("MOUSE_LEFT:"):
            try:
                col = int(key.split(":", 1)[1])
            except ValueError:
                return None
            self.editor.locate(col)
            return None
        if key == "MOUSE_OTHER":
            return None

        # 决策模式：选择如何处理中途消息
        if self.pending_decision:
            low = key.lower() if isinstance(key, str) and len(key) == 1 else key
            if key == KEY_ENTER or low in ("q", "1"):
                self._commit_decision(DECISION_QUEUE)
            elif low in ("i", "2"):
                self._commit_decision(DECISION_INTERJECT)
            elif key in (KEY_ESC, KEY_INTERRUPT):
                self._commit_decision(DECISION_CANCEL)
            self.refresh()
            return None

        action = apply_key(self.editor, key)
        if action == "submit":
            text = self.editor.buffer.strip()
            self.editor.clear()
            if self.state == "busy":
                # 回合进行中：非空输入先问「排队 or 插队」
                if text:
                    self._decision_text = text
                    self.pending_decision = True
                self.refresh()
                return None
            self.refresh()
            # 空行也返回 ""（而不是 None），这样调用方能把「空提交」与
            # 「Ctrl+C / EOF」区分开。
            return text
        if action == "interrupt":
            return "\x03"
        self.refresh()
        return None

    def _commit_decision(self, decision: str) -> None:
        text = self._decision_text
        self._decision_text = ""
        self.pending_decision = False
        if decision == DECISION_QUEUE:
            self.queue.enqueue(text)
        elif decision == DECISION_INTERJECT:
            self.queue.set_interject(text)

    # ── 读取 ──────────────────────────────────────────────────────────── #
    def read_line(self) -> str | None:
        """阻塞读到一行为止；返回 None 表示 Ctrl+C / EOF。"""
        if not self.enabled:
            return None
        while True:
            for key in self.poller.poll():
                text = self.handle_key(key)
                if text == "\x03":
                    return None
                if text is not None:
                    return text
            time.sleep(self.poll_interval)

    def begin_turn(self) -> None:
        self.state = "busy"
        self.refresh()

    def end_turn(self) -> None:
        self.state = "idle"
        self.refresh()

    # ── 供 agent 回合调用的钩子 ───────────────────────────────────────── #
    def poll_during_turn(self) -> None:
        """回合进行中调用：不阻塞地收键，并把输入框刷新到最新状态。"""
        if not self.enabled:
            return
        for key in self.poller.poll():
            self.handle_key(key)

    @property
    def interject(self) -> str:
        return self.queue.interject

    def take_interject(self) -> str:
        return self.queue.take_interject()

    def take_queued(self) -> list:
        return self.queue.take_queued()
