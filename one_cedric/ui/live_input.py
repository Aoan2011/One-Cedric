"""常驻底部的 REPL 输入框：鼠标定位、行编辑、回合中途排队 / 插队。

设计要点
========

* **纯逻辑可测**：``LineEditor``（光标与缓冲区）、``parse_sgr_mouse``（鼠标
  转义序列）与 ``KeyPoller``（非阻塞按键读取，读取函数可注入）都不依赖
  终端，测试里可以逐字节喂输入。
* **底部常驻**：``ReplInputSession`` 用一个长时间存活的 ``rich.Live`` 渲染
  输入框；Rich 会把同时打印到该 console 的输出显示在 Live 区域**上方**，
  所以输入框始终贴在底部，不会随输出滚走。
* **低延迟**：Live 用 ``auto_refresh=False``（没有 10Hz 后台整屏重绘），
  按键累积到一批再处理（``handle_keys``），渲染按内容签名去重 + 约
  1/60s 节流，提交/状态切换时强制 flush；等待输入是事件驱动的
  （Windows 走 ``WaitForSingleObject``，其它平台走 ``select``），
  没有按键时不会空转。
* **中途可插话**：回合进行中按 Enter 会先让你选「排队」还是「插队」：
    - 排队（queue）：当前回合跑完后立刻作为下一条消息处理；
    - 插队（interject）：中断当前流式输出，把这条消息立刻追加进对话，
      模型下一轮就能看到。
  决择绝不吞键、也不跨回合悬挂：回合结束时还没作答就自动把消息放回输入
  框；待决择时继续打字会取消决择、原文留在框里，用户永远不会遇到
  「输入完按 Enter 没反应」的静默状态。
* **提示符处 Ctrl+C 只清行**：常驻输入框里按 Ctrl+C 清空当前输入继续
  对话（退出请用 ``/exit``）；回合进行中 Ctrl+C 才是中断本轮。
* **安全降级**：stdin 不是 TTY（管道、CI、重定向）时全部退回原来的
  ``console.input`` 行为，不启用鼠标、不起线程。
"""
from __future__ import annotations

import os
import select
import sys
import time
from collections import deque
from dataclasses import dataclass, field

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.segment import Segment
from rich.text import Text

from . import icons, statusbar

# ── 转义序列 ──────────────────────────────────────────────────────────── #
ENABLE_MOUSE = "\x1b[?1000h\x1b[?1006h"    # 普通点击 + SGR 扩展坐标
DISABLE_MOUSE = "\x1b[?1000l\x1b[?1006l"

#: 输入框提示符样式（提交回显复用同一套）
PROMPT_STYLE = "bold #d97757"

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
KEY_PAGE_UP = "PAGE_UP"
KEY_PAGE_DOWN = "PAGE_DOWN"
KEY_WORD_LEFT = "WORD_LEFT"
KEY_WORD_RIGHT = "WORD_RIGHT"
KEY_KILL_END = "KILL_END"
KEY_KILL_START = "KILL_START"
KEY_KILL_WORD = "KILL_WORD"

#: 决策：中途消息如何处理
DECISION_NONE = "none"
DECISION_QUEUE = "queue"
DECISION_INTERJECT = "interject"
DECISION_CANCEL = "cancel"

#: ``set_status`` 的哨兵：区分「没传」与「显式清空（None）」
_UNSET = object()


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


def mouse_tracking_enabled(config: dict | None = None) -> bool:
    """是否启用终端鼠标追踪（默认 **关闭**）。

    开启后点击输入框可以定位光标，但终端会把**滚轮事件交给应用**而不是
    滚动回滚缓冲 —— 长回答就翻不动了。所以默认关掉，需要点击定位的用户
    可以设 ``ONE_CEDRIC_MOUSE=1`` 或 ``[ui].mouse = true``。
    """
    env = os.environ.get("ONE_CEDRIC_MOUSE")
    if env is not None:
        return env.strip().lower() not in ("", "0", "false", "no", "off")
    try:
        ui = (config or {}).get("ui") or {}
        return bool(ui.get("mouse", False))
    except Exception:
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

    def kill_word(self) -> None:
        """删除光标前的一个词（Ctrl+W 语义）。"""
        i = self.cursor
        while i > 0 and self.buffer[i - 1].isspace():
            i -= 1
        while i > 0 and not self.buffer[i - 1].isspace():
            i -= 1
        self.buffer = self.buffer[:i] + self.buffer[self.cursor:]
        self.cursor = i

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

    返回：``"submit"`` / ``"edit"`` / ``"escape"`` / ``"interrupt"`` /
    ``"noop"``。

    命名键（``KEY_UP`` 这类多字符键名）绝不会被当作文字写进缓冲区 ——
    这是旧版把 ``UP`` / ``TAB`` 原样插进输入框的根因。
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
    elif key == KEY_WORD_LEFT:
        editor.word_left()
    elif key == KEY_WORD_RIGHT:
        editor.word_right()
    elif key == KEY_KILL_END:
        editor.kill_to_end()
    elif key == KEY_KILL_START:
        editor.kill_to_start()
    elif key == KEY_KILL_WORD:
        editor.kill_word()
    elif key == KEY_TAB:
        # Tab 目前没有补全目标：当无操作，绝不插入 "\t"
        return "noop"
    elif len(key) > 1:
        # 未知的命名键：同样不写进缓冲区
        return "noop"
    elif key.isprintable():
        editor.insert(key)
    else:
        return "noop"
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


#: VT 转义序列 → 统一键名（去掉前导 ESC）
_CSI_KEYS = {
    "[A": KEY_UP, "[B": KEY_DOWN, "[C": KEY_RIGHT, "[D": KEY_LEFT,
    "[H": KEY_HOME, "[F": KEY_END, "[1~": KEY_HOME, "[4~": KEY_END,
    "[3~": KEY_DELETE, "[7~": KEY_HOME, "[8~": KEY_END,
    "[5~": KEY_PAGE_UP, "[6~": KEY_PAGE_DOWN,
    "[1;5D": KEY_WORD_LEFT, "[1;5C": KEY_WORD_RIGHT,
    "OA": KEY_UP, "OB": KEY_DOWN, "OC": KEY_RIGHT, "OD": KEY_LEFT,
    "OH": KEY_HOME, "OF": KEY_END,
}

#: 控制字符 → 统一键名（readline 风格）
_CTRL_KEYS = {
    "\x01": KEY_HOME,        # Ctrl+A
    "\x05": KEY_END,         # Ctrl+E
    "\x0b": KEY_KILL_END,    # Ctrl+K
    "\x15": KEY_KILL_START,  # Ctrl+U
    "\x17": KEY_KILL_WORD,   # Ctrl+W
}

#: Windows 扩展键第二字节 → 统一键名（msvcrt 路径）
_WIN_EXT_KEYS = {
    "H": KEY_UP, "P": KEY_DOWN, "K": KEY_LEFT, "M": KEY_RIGHT,
    "G": KEY_HOME, "O": KEY_END, "S": KEY_DELETE,
}


class KeyPoller:
    """从字符流里非阻塞地取出按键。

    ``read_char`` / ``has_input`` / ``wait`` 都可注入，便于测试与替换后端；
    默认在 Windows 用 msvcrt + ``WaitForSingleObject``（事件驱动等待），
    其它平台用 readchar/select。
    """

    def __init__(self, read_char=None, has_input=None, wait=None):
        self._read_char = read_char or self._default_read_char
        self._has_input = has_input or self._default_has_input
        self._wait = wait or self._default_wait
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

    @staticmethod
    def _default_wait(timeout: float) -> None:
        """最多等 ``timeout`` 秒：有输入立即返回，超时返回。"""
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                get_handle = kernel32.GetStdHandle
                get_handle.restype = wintypes.HANDLE
                get_handle.argtypes = [wintypes.DWORD]
                handle = get_handle(-10)        # STD_INPUT_HANDLE
                if handle and handle.value != -1:
                    wait = kernel32.WaitForSingleObject
                    wait.restype = wintypes.DWORD
                    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                    if wait(handle, int(max(timeout, 0) * 1000)) == 0:
                        return
                    return
            except Exception:
                pass
            time.sleep(timeout)
            return
        try:
            select.select([sys.stdin], [], [], timeout)
        except Exception:
            time.sleep(timeout)

    def wait(self, timeout: float) -> None:
        """等一小段时间（事件驱动；有输入或超时即返回）。"""
        if self._has_input():
            return
        try:
            self._wait(timeout)
        except Exception:
            time.sleep(timeout)

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
            # 统一 CSI 扫描：读到终止字节（@..~）为止；SGR 鼠标的
            # "\x1b[<...M/m" 走的也是这条路（'<' 不是终止字节）。
            if buf.startswith("\x1b["):
                i = 2
                while i < len(buf) and not ("@" <= buf[i] <= "~"):
                    i += 1
                if i >= len(buf):
                    return None                      # 序列不完整，等更多
                seq, self._pending = buf[:i + 1], buf[i + 1:]
                if seq.startswith("\x1b[<"):
                    event = parse_sgr_mouse(seq)
                    if event is None:
                        return "noop"
                    if is_left_click(event):
                        return f"MOUSE_LEFT:{event['x']}"
                    return "MOUSE_OTHER"
                return _CSI_KEYS.get(seq[1:], "noop")
            if buf.startswith("\x1bO"):
                if len(buf) < 3:
                    return None
                self._pending = buf[3:]
                return _CSI_KEYS.get(buf[1:3], "noop")
            self._pending = buf[1:]
            return KEY_ESC

        if buf[0] == "\r":
            # \r\n 是同一个 Enter（终端通常只给 \r，管道/粘贴可能给两个）
            self._pending = buf[2:] if buf.startswith("\r\n") else buf[1:]
            return KEY_ENTER
        if buf[0] == "\n":
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
        ctrl = _CTRL_KEYS.get(buf[0])
        if ctrl is not None:
            self._pending = buf[1:]
            return ctrl

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


# ══════════════════════════════════════════════════════════════════════ #
# 渲染
# ══════════════════════════════════════════════════════════════════════ #

class _TailView:
    """只渲染最后几行（流式预览跟随最新内容），避免超出屏幕被截头。

    Rich 的 ``Live`` 默认 ``vertical_overflow="ellipsis"``，内容高于屏幕时
    **保留开头、丢掉结尾** —— 流式长回答看起来就像「卡住不动」。这里先
    渲染完整结果，再只取最后 ``可用高度`` 行，于是预览始终跟着最新输出走。
    """

    #: 输入框 4 行 + 预览结尾可能的空行 1 行 + 余量 1 行
    RESERVED = 6

    def __init__(self, renderable, reserved: int | None = None) -> None:
        self.renderable = renderable
        self.reserved = self.RESERVED if reserved is None else reserved

    def __rich_console__(self, console, options):
        lines = console.render_lines(self.renderable, options, pad=False)
        keep = max(options.size.height - self.reserved, 3)
        for index, line in enumerate(lines[-keep:]):
            if index:
                yield Segment.line()
            yield from line
        # Group 不会自动在相邻 renderable 之间换行（换行由各 renderable 自己
        # 产出），少了这一行，输入框顶边框会跟预览最后一行挤在同一行。
        yield Segment.line()


def prompt_hints(*, state: str = "idle", queue_len: int = 0,
                 pending_decision: bool = False) -> list[str]:
    """输入框里的操作提示（按状态变化）。"""
    hints: list[str] = []
    if pending_decision:
        hints.append("Enter 排队 · i 插队 · Esc 取消")
    else:
        if state == "busy":
            hints.append("回合进行中，可直接输入")
        if queue_len:
            hints.append(f"已排队 {queue_len} 条")
        hints.append("Ctrl+C 中断" if state == "busy" else "Ctrl+C 清空")
    return hints


def submitted_line(text: str) -> Text:
    """提交后回显到对话区的一行（与输入框提示符一致）。

    没有它，按 Enter 后输入框被清空，用户看不出自己刚发了什么。
    """
    line = Text()
    line.append(f"  {icons.glyph('prompt')} ", style=PROMPT_STYLE)
    line.append(text)
    return line


def render_prompt(editor: LineEditor, *, state: str = "idle",
                  queue_len: int = 0, pending_decision: bool = False,
                  model: str = "", width: int = 80,
                  status: Text | None = None):
    """渲染底部输入框（返回 rich 可渲染对象）。

    ``status`` 是底栏状态行（上下文占用 / git / 环境），常驻在框内最底行。
    """
    before, at, after = editor.split()
    line = Text()
    line.append(f"  {icons.glyph('prompt')} ", style=PROMPT_STYLE)
    line.append(before)
    if at:
        line.append(at, style="reverse")
        line.append(after)
    else:
        line.append(" ", style="reverse")

    hints = prompt_hints(state=state, queue_len=queue_len,
                         pending_decision=pending_decision)

    border = {"idle": "#d97757", "busy": "#4ec9b0",
              "decision": "#e0af68"}.get(
        "decision" if pending_decision else state, "#d97757")

    title = "One Cedric"
    if state == "busy":
        title = f"One Cedric {icons.glyph('running')} 运行中"
    if model:
        title = f"{title} · {model}"

    body = Text()
    body.append_text(line)
    if hints:
        body.append("\n")
        # 待决策时提示行跟随边框色（橙色），让「排队/插队」一眼可见
        body.append("  " + " · ".join(hints),
                    style=border if pending_decision else "dim")
    if status is not None:
        body.append("\n")
        body.append("  ")
        body.append_text(status)

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

    渲染节流：``refresh()`` 只在内容签名变化且距上次绘制超过
    ``_min_interval`` 时重绘（按键洪峰合并成少数几帧）；提交、状态切换
    这类需要立刻可见的时机调 ``flush()`` 强制重绘。
    """

    #: 渲染合并窗口（约 60fps 可感知上限）
    _MIN_INTERVAL = 1 / 60
    #: git 状态最短刷新间隔（每次提示周期最多刷一次）
    _GIT_TTL = 2.0

    def __init__(self, console, *, poll_interval: float = 0.03,
                 mouse: bool = False, root=None):
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
        #: 鼠标追踪默认关闭（开启会吃掉滚轮滚动），需要点击定位时再打开
        self.mouse = bool(mouse)
        self.enabled = _stdin_is_tty() and _stdout_is_tty()
        # 回合中的流式预览（renderable，显示在输入框上方）
        self._preview = None
        self._preview_gen = 0
        # 底栏状态：上下文 / 轮次步数 / 费用 / 峰谷 / git / 仓库环境
        self.root = root
        self._ctx_used: int | None = None
        self._ctx_max: int | None = None
        self._turns: int | None = None
        self._steps: int | None = None
        self._cost: float | None = None
        self._peak: dict | None = None
        self._git: dict | None = None
        self._git_at = 0.0
        self._git_checked = False
        self._env: str = ""
        self._env_done = False
        # 上/下键历史（含未提交草稿）
        self.history: list[str] = []
        self._hist_idx = 0
        self._hist_draft = ""
        # 一次 poll 里提交多行（粘贴）时，先返回第一行，其余排队
        self._submitted: deque[str] = deque()
        # 渲染去重 + 节流
        self._last_sig = None
        self._last_render = 0.0

    # ── 生命周期 ──────────────────────────────────────────────────────── #
    def start(self) -> None:
        if not self.enabled:
            return
        # 鼠标追踪必须保证被关掉，否则终端会一直处于鼠标上报模式。
        # atexit 兜底覆盖所有 return 路径（包括异常退出）。
        import atexit

        from rich.live import Live
        atexit.register(self.stop)
        if self.mouse:
            self._mouse = MouseMode(self.console).__enter__()
        # auto_refresh=False：不跑 10Hz 后台整屏重绘线程，只有内容变化
        # 时由 refresh()/flush() 主动画一帧——输入延迟的主要来源。
        self._live = Live(self.render(), console=self.console,
                          refresh_per_second=8, transient=False,
                          auto_refresh=False)
        self._live.__enter__()
        self._render_now()

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

    def _signature(self):
        """输入框内容签名：没变化就不用重绘。"""
        return (self.editor.buffer, self.editor.cursor, self.state,
                self.pending_decision, len(self.queue.queued),
                getattr(self, "model", ""), self._preview_gen,
                self._ctx_used, self._ctx_max, self._turns, self._steps,
                self._cost, self._peak_key(), self._git_key(), self._env)

    def _peak_key(self):
        peak = self._peak
        if not peak:
            return None
        return (peak.get("supported"), peak.get("offpeak"),
                peak.get("rate"), peak.get("seconds_to_change"))

    def _git_key(self):
        git = self._git
        if not git:
            return None
        return (git.get("branch"), git.get("ahead"), git.get("behind"),
                git.get("changed"), git.get("detached"))

    def _render_now(self) -> None:
        if self._live is None:
            return
        try:
            self._live.update(self.render(), refresh=True)
        except Exception:
            pass
        self._last_sig = self._signature()
        self._last_render = time.monotonic()

    def refresh(self) -> None:
        """按内容签名去重 + 节流地重绘（键盘洪峰会被合并）。"""
        if self._live is None:
            return
        if self._signature() == self._last_sig:
            return
        if time.monotonic() - self._last_render < self._MIN_INTERVAL:
            return
        self._render_now()

    def flush(self) -> None:
        """立刻重绘（提交 / 状态切换 / 回合结束时调用）。"""
        if self._live is None:
            return
        self._render_now()

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
            self._render_now()

    # ── 渲染 ──────────────────────────────────────────────────────────── #
    def render(self):
        width = int(getattr(self.console, "width", 80) or 80)
        hints = prompt_hints(
            state=self.state,
            queue_len=len(self.queue.queued),
            pending_decision=self.pending_decision,
        )
        status = statusbar.format_status(
            self._ctx_used, self._ctx_max, self._git, self._env, width,
            turns=self._turns, steps=self._steps, cost=self._cost,
            peak=self._peak)
        box_view = render_prompt(
            self.editor,
            state=self.state,
            queue_len=len(self.queue.queued),
            pending_decision=self.pending_decision,
            model=getattr(self, "model", ""),
            status=status,
        )
        if self._preview is None:
            return box_view
        # 预览在上、输入框永远贴底；预览超高时只显示尾部
        box_rows = 3 + (1 if hints else 0) + (1 if status is not None else 0)
        return Group(
            _TailView(self._preview, reserved=box_rows + 2), box_view)

    # ── 底栏状态 ──────────────────────────────────────────────────────── #
    def set_status(self, *, ctx_used=_UNSET, ctx_max=_UNSET, turns=_UNSET,
                   steps=_UNSET, cost=_UNSET, peak=_UNSET) -> None:
        """更新底栏数据（核心在每个提示周期前调用）。

        未传的字段保持原值；显式传 ``None`` 表示清空（例如模型切到没有
        峰谷差价的模型时，``peak=None`` 要把「谷/峰」标记摘掉）。
        """
        if ctx_used is not _UNSET:
            self._ctx_used = None if ctx_used is None else int(ctx_used)
        if ctx_max is not _UNSET:
            self._ctx_max = None if ctx_max is None else int(ctx_max)
        if turns is not _UNSET:
            self._turns = None if turns is None else int(turns)
        if steps is not _UNSET:
            self._steps = None if steps is None else int(steps)
        if cost is not _UNSET:
            self._cost = None if cost is None else float(cost)
        if peak is not _UNSET:
            self._peak = peak
        self._refresh_status_sources()
        self.refresh()

    def _refresh_status_sources(self) -> None:
        """刷新 git 摘要（带 TTL）与仓库环境（只探测一次）。"""
        if self.root is None:
            return
        now = time.monotonic()
        if (not self._git_checked
                or now - self._git_at >= self._GIT_TTL):
            self._git_checked = True
            self._git_at = now
            try:
                from ..git_snap import git_brief_status
                self._git = git_brief_status(self.root)
            except Exception:
                self._git = None
        if not self._env_done:
            self._env_done = True
            try:
                self._env = statusbar.gather_env(self.root)
            except Exception:
                self._env = ""

    # ── 回合流式预览 ──────────────────────────────────────────────────── #
    def set_preview(self, renderable) -> None:
        """设置输入框上方的流式预览（回合进行中由 agent_turn 调用）。"""
        first = self._preview is None
        self._preview = renderable
        self._preview_gen += 1
        if first:
            # 首次出现预览（如「思考中」spinner）：绕过节流立刻画一帧
            self._render_now()
        else:
            self.refresh()

    def clear_preview(self) -> None:
        """清掉流式预览。立刻重绘一次，保证随后的 console.print 使用
        新的（只有输入框的）高度来定位光标。"""
        if self._preview is None:
            return
        self._preview = None
        self._preview_gen += 1
        self._render_now()

    @property
    def has_preview(self) -> bool:
        return self._preview is not None

    # ── 历史 ──────────────────────────────────────────────────────────── #
    def _push_history(self, text: str) -> None:
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self._hist_idx = len(self.history)
        self._hist_draft = ""

    def _history_prev(self) -> None:
        if not self.history:
            return
        if self._hist_idx >= len(self.history):
            self._hist_draft = self.editor.buffer
        self._hist_idx = max(0, self._hist_idx - 1)
        self.editor.buffer = self.history[self._hist_idx]
        self.editor.end()

    def _history_next(self) -> None:
        if self._hist_idx >= len(self.history):
            return
        self._hist_idx += 1
        if self._hist_idx >= len(self.history):
            self._hist_idx = len(self.history)
            self.editor.buffer = self._hist_draft
        else:
            self.editor.buffer = self.history[self._hist_idx]
        self.editor.end()

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
            self.refresh()
            return None
        if key == "MOUSE_OTHER":
            return None

        # 决策模式：选择如何处理中途消息
        if self.pending_decision:
            low = key.lower() if isinstance(key, str) and len(key) == 1 else key
            if low in (KEY_ENTER, "q", "1"):
                self._commit_decision(DECISION_QUEUE)
                self.refresh()
                return None
            if low in ("i", "2"):
                self._commit_decision(DECISION_INTERJECT)
                self.refresh()
                return None
            if key in (KEY_ESC, KEY_INTERRUPT):
                self._commit_decision(DECISION_CANCEL)
                self.refresh()
                return None
            # 其它按键（继续打字 / 翻历史 / 改主意）：放弃这次选择，把
            # 待决策的原文放回输入框，按键照常生效 —— 绝不静默吞键，
            # 否则用户会看到「输入完按 Enter 没反应」。
            self._restore_decision_draft()

        # 上/下翻历史（其余按键走编辑器）
        if key in (KEY_UP, KEY_PAGE_UP):
            self._history_prev()
            self.refresh()
            return None
        if key in (KEY_DOWN, KEY_PAGE_DOWN):
            self._history_next()
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
            self._push_history(text)
            self.refresh()
            # 空行也返回 ""（而不是 None），这样调用方能把「空提交」与
            # 「Ctrl+C / EOF」区分开。
            return text
        if action == "interrupt":
            return "\x03"
        self.refresh()
        return None

    def handle_keys(self, keys) -> str | None:
        """处理一整批按键（一次 poll 的结果）。

        与逐个调用 ``handle_key`` 的区别：同一批里 Enter 之后的按键不会
        被丢掉；若一次提交了多行（粘贴多行文本），第一行立即返回，其余
        进入 ``next_line()`` 队列，后续 ``read_line()`` 依次取走。
        """
        for key in keys:
            text = self.handle_key(key)
            if text == "\x03":
                return "\x03"
            if text is not None:
                self._submitted.append(text)
        return self.next_line()

    def next_line(self) -> str | None:
        """取走批量提交中暂存的行；没有则返回 None。"""
        if self._submitted:
            return self._submitted.popleft()
        return None

    def _commit_decision(self, decision: str) -> None:
        text = self._decision_text
        self._decision_text = ""
        self.pending_decision = False
        if decision == DECISION_QUEUE:
            self.queue.enqueue(text)
        elif decision == DECISION_INTERJECT:
            self.queue.set_interject(text)

    def _restore_decision_draft(self) -> None:
        """放弃待决策状态但保留原文：放回输入框继续编辑。

        回合结束还没选择的决策、或用户直接继续打字时走这里 —— 消息既
        不静默排队也不丢，输入框里看得见、改得动、Enter 能再发一次。
        """
        text = self._decision_text
        self._decision_text = ""
        self.pending_decision = False
        if text and not self.editor.buffer:
            self.editor.buffer = text
            self.editor.end()

    # ── 读取 ──────────────────────────────────────────────────────────── #
    def _echo_submitted(self, text: str) -> None:
        """把刚提交的行回显到输入框上方（终端一贯行为）。

        输入框会被清空并贴在底部，没有这行回显，用户就看不到自己发了
        什么。空提交不回显；``console.print`` 会在 Live 区域上方打印，
        不会打乱固定在底部的输入框。
        """
        text = (text or "").strip()
        if not text or self.console is None:
            return
        try:
            self.console.print(submitted_line(text))
        except Exception:
            pass

    def read_line(self) -> str | None:
        """阻塞读到一行为止；返回 None 表示 EOF / 会话结束。

        提示符处 Ctrl+C 只清空当前行、会话继续（退出请用 ``/exit``）——
        在常驻输入框里按 Ctrl+C 直接退出对话是很糟糕的意外。
        """
        if not self.enabled:
            return None
        while True:
            try:
                line = self.next_line()
                if line is not None:
                    self._echo_submitted(line)
                    self.flush()
                    return line
                keys = self.poller.poll()
                if keys:
                    text = self.handle_keys(keys)
                    if text == "\x03":
                        self.editor.clear()
                        self.flush()
                        continue
                    if text is not None:
                        self._echo_submitted(text)
                        self.flush()
                        return text
                self.refresh()
                # 事件驱动等待：有输入立刻回来，没有则最多等 poll_interval，
                # 不会像 sleep 那样不管有没有按键都固定空转一轮。
                self.poller.wait(self.poll_interval)
            except KeyboardInterrupt:
                # 控制台把 Ctrl+C 作为信号抛出（msvcrt 之外的路径）：
                # 同样只清行，不退出对话。
                self.editor.clear()
                self.flush()
                continue
            except EOFError:
                return None

    def begin_turn(self) -> None:
        self.state = "busy"
        self.flush()

    def end_turn(self) -> None:
        self.state = "idle"
        # 回合结束时还挂着未作答的决策：把消息放回输入框。否则输入框会
        # 带着「待决策」状态回到提示符，后面所有按键都会被吃掉。
        if self.pending_decision:
            self._restore_decision_draft()
        # 兜底：异常路径没走到 clear_preview 时也把预览收掉
        if self._preview is not None:
            self._preview = None
            self._preview_gen += 1
        self.flush()

    # ── 供 agent 回合调用的钩子 ───────────────────────────────────────── #
    def poll_during_turn(self) -> None:
        """回合进行中调用：不阻塞地收键，并把输入框刷新到最新状态。"""
        if not self.enabled:
            return
        keys = self.poller.poll()
        if keys:
            self.handle_keys(keys)
            self.refresh()

    @property
    def interject(self) -> str:
        return self.queue.interject

    def take_interject(self) -> str:
        return self.queue.take_interject()

    def take_queued(self) -> list:
        return self.queue.take_queued()
