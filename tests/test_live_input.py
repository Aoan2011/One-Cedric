"""Tests for the bottom-pinned REPL input box (mouse / editing / queue / interject).

Only the terminal-independent logic is exercised here: the line editor, the
SGR mouse parser, the key-sequence splitter and the mid-turn queue. The Rich
``Live`` rendering and raw terminal I/O are intentionally not tested.
"""
from __future__ import annotations

import pytest

from one_cedric.ui.live_input import (
    DECISION_CANCEL,
    DECISION_INTERJECT,
    DECISION_QUEUE,
    DISABLE_MOUSE,
    ENABLE_MOUSE,
    KEY_BACKSPACE,
    KEY_DELETE,
    KEY_END,
    KEY_ENTER,
    KEY_ESC,
    KEY_HOME,
    KEY_INTERRUPT,
    KEY_KILL_END,
    KEY_KILL_START,
    KEY_KILL_WORD,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_TAB,
    KEY_UP,
    KEY_DOWN,
    KEY_WORD_LEFT,
    KEY_WORD_RIGHT,
    KeyPoller,
    LineEditor,
    MidTurnQueue,
    ReplInputSession,
    apply_key,
    parse_sgr_mouse,
    mouse_tracking_enabled,
    render_prompt,
)

# --------------------------------------------------------------------------- #
# LineEditor
# --------------------------------------------------------------------------- #

def test_insert_and_cursor():
    ed = LineEditor()
    ed.insert("hello")
    assert ed.buffer == "hello"
    assert ed.cursor == 5
    ed.left()
    ed.insert("X")
    assert ed.buffer == "hellXo"
    assert ed.cursor == 5


def test_backspace_and_delete():
    ed = LineEditor(buffer="abc", cursor=3)
    ed.backspace()
    assert ed.buffer == "ab"
    ed.home()
    ed.delete()
    assert ed.buffer == "b"


def test_backspace_at_start_is_a_noop():
    ed = LineEditor(buffer="abc", cursor=0)
    ed.backspace()
    assert ed.buffer == "abc"


def test_delete_at_end_is_a_noop():
    ed = LineEditor(buffer="abc", cursor=3)
    ed.delete()
    assert ed.buffer == "abc"


def test_home_end_and_movement_clamp():
    ed = LineEditor(buffer="abcd", cursor=2)
    ed.home()
    assert ed.cursor == 0
    ed.left()
    assert ed.cursor == 0
    ed.end()
    assert ed.cursor == 4
    ed.right()
    assert ed.cursor == 4


def test_word_movement():
    ed = LineEditor(buffer="read the file now", cursor=17)
    ed.word_left()
    assert ed.cursor == 14          # at "now"
    ed.word_left()
    assert ed.cursor == 9           # at "file"
    ed.word_right()
    assert ed.cursor == 14


def test_kill_to_end_and_start():
    ed = LineEditor(buffer="abcdef", cursor=3)
    ed.kill_to_end()
    assert ed.buffer == "abc"
    ed = LineEditor(buffer="abcdef", cursor=3)
    ed.kill_to_start()
    assert ed.buffer == "def"
    assert ed.cursor == 0


def test_newlines_are_stripped_from_inserted_text():
    ed = LineEditor()
    ed.insert("a\nb\rc")
    assert ed.buffer == "abc"


def test_split_returns_cursor_character():
    ed = LineEditor(buffer="abc", cursor=1)
    assert ed.split() == ("a", "b", "c")
    ed = LineEditor(buffer="abc", cursor=3)
    assert ed.split() == ("abc", "", "")


# --------------------------------------------------------------------------- #
# Mouse
# --------------------------------------------------------------------------- #

def test_parse_sgr_mouse_left_press():
    event = parse_sgr_mouse("\x1b[<0;12;5M")
    assert event == {"button": 0, "x": 12, "y": 5, "press": True}


def test_parse_sgr_mouse_release():
    event = parse_sgr_mouse("\x1b[<0;12;5m")
    assert event is not None and event["press"] is False


@pytest.mark.parametrize("seq", [
    "", "\x1b[A", "\x1b[<0;12M", "\x1b[<a;b;cM", "\x1b[<0;12;5X", "hello",
])
def test_parse_sgr_mouse_rejects_non_mouse(seq):
    assert parse_sgr_mouse(seq) is None


def test_mouse_click_places_cursor():
    ed = LineEditor(buffer="hello world", prompt_width=4)
    # 终端第 3 列 → 去掉提示符宽度 4 后 clamp 到 0
    ed.locate(3)
    assert ed.cursor == 0
    ed.locate(10)          # 10 - 1 - 4 = 5
    assert ed.cursor == 5
    ed.locate(999)         # 超出末尾 → 贴到末尾
    assert ed.cursor == len(ed.buffer)


def test_mouse_escape_constants():
    assert ENABLE_MOUSE.startswith("\x1b[?1000h")
    assert DISABLE_MOUSE.startswith("\x1b[?1000l")


# --------------------------------------------------------------------------- #
# Key sequence splitting
# --------------------------------------------------------------------------- #

def _poller_with(seq: str) -> KeyPoller:
    p = KeyPoller(read_char=lambda: "", has_input=lambda: False)
    p.feed(seq)
    return p


def test_pop_key_reads_printable_characters():
    p = _poller_with("ab")
    assert p.pop_key() == "a"
    assert p.pop_key() == "b"
    assert p.pop_key() is None


def test_pop_key_handles_enter_and_backspace():
    p = _poller_with("\r\x7f")
    assert p.pop_key() == KEY_ENTER
    assert p.pop_key() == KEY_BACKSPACE


def test_pop_key_handles_arrow_sequences():
    p = _poller_with("\x1b[A\x1b[B\x1b[C\x1b[D")
    assert [p.pop_key() for _ in range(4)] == [
        "UP", "DOWN", "RIGHT", "LEFT"]


def test_pop_key_handles_home_end_delete():
    p = _poller_with("\x1b[H\x1b[F\x1b[3~")
    assert p.pop_key() == KEY_HOME
    assert p.pop_key() == KEY_END
    assert p.pop_key() == KEY_DELETE


def test_pop_key_handles_ss3_sequences():
    p = _poller_with("\x1bOA")
    assert p.pop_key() == "UP"


def test_partial_escape_sequence_waits_for_more_input():
    p = _poller_with("\x1b[")
    assert p.pop_key() is None
    p.feed("A")
    assert p.pop_key() == "UP"


def test_partial_mouse_sequence_waits_for_more_input():
    p = _poller_with("\x1b[<0;5;5")
    assert p.pop_key() is None
    p.feed("M")
    assert p.pop_key() == "MOUSE_LEFT:5"


def test_bare_escape_is_escape():
    p = _poller_with("\x1b")
    assert p.pop_key() == KEY_ESC


def test_windows_extended_keys():
    p = _poller_with("\xe0H\xe0P")
    assert p.pop_key() == "UP"
    assert p.pop_key() == "DOWN"


def test_pop_key_waits_for_extended_key_second_byte():
    p = _poller_with("\xe0")
    assert p.pop_key() is None
    p.feed("K")
    assert p.pop_key() == "LEFT"


def test_ctrl_c_is_interrupt():
    p = _poller_with("\x03")
    assert p.pop_key() == "INTERRUPT"


def test_apply_key_maps_editing_keys():
    ed = LineEditor(buffer="ab", cursor=2)
    assert apply_key(ed, KEY_LEFT) == "edit"
    assert ed.cursor == 1
    assert apply_key(ed, KEY_ENTER) == "submit"
    assert apply_key(ed, KEY_ESC) == "escape"


def test_apply_key_never_inserts_named_keys_as_text():
    """旧版把 "UP" / "TAB" 字面写进输入框，这里钉死不再发生。"""
    ed = LineEditor()
    for key in (KEY_TAB, "F5", "UNKNOWN", "PAGE_UP"):
        assert apply_key(ed, key) == "noop"
    assert ed.buffer == ""
    assert ed.cursor == 0


def test_apply_key_handles_readline_shortcuts():
    ed = LineEditor(buffer="echo hello world", cursor=16)
    assert apply_key(ed, KEY_KILL_WORD) == "edit"
    assert ed.buffer == "echo hello "
    assert ed.cursor == 11
    assert apply_key(ed, KEY_KILL_START) == "edit"
    assert ed.buffer == ""
    ed = LineEditor(buffer="abcdef", cursor=3)
    assert apply_key(ed, KEY_KILL_END) == "edit"
    assert ed.buffer == "abc"


def test_apply_key_word_movement():
    ed = LineEditor(buffer="read the file now", cursor=17)
    assert apply_key(ed, KEY_WORD_LEFT) == "edit"
    assert ed.cursor == 14
    assert apply_key(ed, KEY_WORD_RIGHT) == "edit"
    assert ed.cursor == 17


def test_ctrl_chars_map_to_editing_keys():
    p = _poller_with("\x01\x05\x0b\x15\x17")
    assert [p.pop_key() for _ in range(5)] == [
        KEY_HOME, KEY_END, KEY_KILL_END, KEY_KILL_START, KEY_KILL_WORD]


def test_word_move_and_page_csi_sequences():
    p = _poller_with("\x1b[1;5D\x1b[1;5C\x1b[5~\x1b[6~")
    assert [p.pop_key() for _ in range(4)] == [
        KEY_WORD_LEFT, KEY_WORD_RIGHT, KEY_PAGE_UP, KEY_PAGE_DOWN]


def test_crlf_collapses_into_one_enter():
    p = _poller_with("a\r\nb")
    assert [p.pop_key() for _ in range(3)] == ["a", KEY_ENTER, "b"]


def test_unknown_csi_sequence_is_consumed_as_noop():
    p = _poller_with("\x1b[99~x")
    assert p.pop_key() == "noop"
    assert p.pop_key() == "x"


def test_poller_wait_uses_injected_fn_and_skips_when_input_ready():
    calls = []
    quiet = KeyPoller(read_char=lambda: "", has_input=lambda: False,
                      wait=calls.append)
    quiet.wait(0.25)
    assert calls == [0.25]
    ready = KeyPoller(read_char=lambda: "", has_input=lambda: True,
                      wait=calls.append)
    ready.wait(0.25)
    assert calls == [0.25]          # 有输入时不进入等待


def test_poll_is_mutually_exclusive_across_threads():
    """两个线程同时 poll 时必须串行：检查与读取之间不能被插队。

    旧缺陷：A 线程在 ``has_input()`` 为真、``read_char()`` 执行前让出，
    B 线程若挤进同一窗口，双方都会去读输入；默认的 ``msvcrt.getwch``
    在抢不到字符时**阻塞**，于是整个回合卡死到用户下一次按键（WebUI
    流式一起停摆的根因）。
    """
    import threading
    import time

    reading = {"on": False}
    violations: list[str] = []
    first_read = threading.Event()
    release_read = threading.Event()
    calls = {"n": 0}

    def read_char():
        if reading["on"]:
            violations.append("read_char 重入")
        reading["on"] = True
        calls["n"] += 1
        if calls["n"] == 1:
            first_read.set()
            release_read.wait(timeout=5)
        reading["on"] = False
        return "a"

    def has_input():
        if reading["on"]:
            violations.append("has_input 与 read_char 并发")
        return calls["n"] < 6

    p = KeyPoller(read_char=read_char, has_input=has_input)
    got: dict[str, list[str]] = {}

    t1 = threading.Thread(target=lambda: got.__setitem__("a", p.poll()))
    t2 = threading.Thread(target=lambda: got.__setitem__("b", p.poll()))
    t1.start()
    assert first_read.wait(timeout=5)   # t1 正卡在 read_char「阻塞」中
    t2.start()
    time.sleep(0.05)
    # 持锁时 t2 进不来：一个字符都读不走（旧代码这里会到 2）
    assert calls["n"] == 1

    release_read.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not t1.is_alive() and not t2.is_alive()
    assert violations == []
    assert calls["n"] == 6
    assert got["a"] == ["a"] * 6        # 六个字符全归先到的线程
    assert got["b"] == []               # 后到的线程只拿到空 poll


# --------------------------------------------------------------------------- #
# MidTurnQueue
# --------------------------------------------------------------------------- #

def test_queue_ignores_blank_messages():
    q = MidTurnQueue()
    q.enqueue("   ")
    q.enqueue("")
    assert q.take_queued() == []


def test_queue_and_interject_are_independent():
    q = MidTurnQueue()
    q.enqueue("first")
    q.enqueue("second")
    q.set_interject("urgent")
    assert q.has_interject is True
    assert q.take_interject() == "urgent"
    assert q.has_interject is False
    assert q.take_queued() == ["first", "second"]
    assert q.take_queued() == []


# --------------------------------------------------------------------------- #
# Session decision flow (no terminal involved)
# --------------------------------------------------------------------------- #

class _HeadlessSession(ReplInputSession):
    """ReplInputSession without a terminal: no Live, no mouse."""

    def __init__(self):
        super().__init__(console=None)
        self.enabled = True

    def refresh(self):
        pass


def test_idle_submit_returns_the_line():
    s = _HeadlessSession()
    for ch in "hi":
        s.handle_key(ch)
    assert s.handle_key(KEY_ENTER) == "hi"
    assert s.editor.buffer == ""


def test_idle_empty_submit_returns_empty_string():
    s = _HeadlessSession()
    assert s.handle_key(KEY_ENTER) == ""


def test_mouse_click_moves_cursor_in_session():
    s = _HeadlessSession()
    for ch in "hello":
        s.handle_key(ch)
    s.handle_key("MOUSE_LEFT:4")   # prompt_width=2 → cursor 1
    s.handle_key("X")
    assert s.editor.buffer == "hXello"


def test_during_turn_enter_asks_for_a_decision():
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "stop":
        s.handle_key(ch)
    assert s.handle_key(KEY_ENTER) is None
    assert s.pending_decision is True
    assert s.editor.buffer == ""


def test_decision_queue_adds_to_the_queue():
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "later":
        s.handle_key(ch)
    s.handle_key(KEY_ENTER)
    s.handle_key(KEY_ENTER)          # 默认 = 排队
    assert s.pending_decision is False
    assert s.take_queued() == ["later"]
    assert s.interject == ""


def test_decision_interject_sets_the_interject():
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "urgent":
        s.handle_key(ch)
    s.handle_key(KEY_ENTER)
    s.handle_key("i")
    assert s.pending_decision is False
    assert s.interject == "urgent"
    assert s.take_interject() == "urgent"
    assert s.interject == ""


def test_decision_cancel_keeps_nothing():
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "oops":
        s.handle_key(ch)
    s.handle_key(KEY_ENTER)
    s.handle_key(KEY_ESC)
    assert s.pending_decision is False
    assert s.take_queued() == []
    assert s.interject == ""


def test_decision_typing_restores_draft_instead_of_eating_keys():
    """待决策时继续打字：取消决策、原稿放回输入框，绝不吞键。"""
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "hello":
        s.handle_key(ch)
    s.handle_key(KEY_ENTER)
    assert s.pending_decision is True
    assert s.handle_key("w") is None
    assert s.pending_decision is False
    assert s.editor.buffer == "hellow"


def test_end_turn_restores_unanswered_decision_message():
    """回合结束还没作答：消息回到输入框，而不是静默留在决策模式。"""
    s = _HeadlessSession()
    s.begin_turn()
    for ch in "draft":
        s.handle_key(ch)
    s.handle_key(KEY_ENTER)
    assert s.pending_decision is True
    s.end_turn()
    assert s.pending_decision is False
    assert s.state == "idle"
    assert s.editor.buffer == "draft"
    assert s.take_queued() == []


def test_decision_constants_are_distinct():
    assert len({DECISION_QUEUE, DECISION_INTERJECT, DECISION_CANCEL}) == 3


# --------------------------------------------------------------------------- #
# Batch key handling / history（还是无终端）
# --------------------------------------------------------------------------- #

def test_handle_keys_processes_batch_and_keeps_after_enter():
    """同一批里 Enter 之后的按键不再被丢掉。"""
    s = _HeadlessSession()
    assert s.handle_keys(list("ab") + [KEY_ENTER] + list("cd")) == "ab"
    assert s.editor.buffer == "cd"


def test_handle_keys_returns_first_submission_of_the_batch():
    s = _HeadlessSession()
    assert s.handle_keys(["x", KEY_ENTER, "y", KEY_ENTER]) == "x"
    assert s.next_line() == "y"          # 第二行排队，不丢
    assert s.next_line() is None
    assert s.editor.buffer == ""


def test_handle_keys_interrupt_wins_over_batch():
    s = _HeadlessSession()
    assert s.handle_keys(["x", KEY_INTERRUPT]) == "\x03"


def test_history_up_down_and_draft_restore():
    s = _HeadlessSession()
    for text in ("one", "two"):
        s.handle_keys(list(text) + [KEY_ENTER])
    s.handle_key(KEY_UP)
    assert s.editor.buffer == "two"
    s.handle_key(KEY_UP)
    assert s.editor.buffer == "one"
    s.handle_key(KEY_DOWN)
    assert s.editor.buffer == "two"
    s.handle_key(KEY_DOWN)
    assert s.editor.buffer == ""
    assert s.editor.cursor == 0


def test_history_restores_unsubmitted_draft():
    s = _HeadlessSession()
    s.handle_keys(list("saved") + [KEY_ENTER])
    for ch in "dra":
        s.handle_key(ch)
    s.handle_key(KEY_UP)
    assert s.editor.buffer == "saved"
    s.handle_key(KEY_DOWN)
    assert s.editor.buffer == "dra"
    assert s.editor.cursor == 3


def test_submit_is_recorded_in_history_but_blank_is_not():
    s = _HeadlessSession()
    s.handle_keys(list("hey") + [KEY_ENTER])
    s.handle_key(KEY_ENTER)
    assert s.history == ["hey"]


def test_history_ignores_duplicate_consecutive_entries():
    s = _HeadlessSession()
    for _ in range(2):
        s.handle_keys(list("same") + [KEY_ENTER])
    assert s.history == ["same"]


def test_old_up_tab_bug_no_longer_inserts_literal_text():
    s = _HeadlessSession()
    s.handle_key(KEY_TAB)
    s.handle_key("UP")          # 旧版会插入字面 "UP"
    s.handle_key("F5")
    assert s.editor.buffer == ""


def test_page_up_page_down_browse_history():
    s = _HeadlessSession()
    s.handle_keys(list("old") + [KEY_ENTER])
    s.handle_key(KEY_PAGE_UP)
    assert s.editor.buffer == "old"
    s.handle_key(KEY_PAGE_DOWN)
    assert s.editor.buffer == ""


# --------------------------------------------------------------------------- #
# Rendering is at least constructible
# --------------------------------------------------------------------------- #

def test_render_prompt_returns_a_renderable():
    import io

    from rich.console import Console

    ed = LineEditor(buffer="hi", cursor=1)
    console = Console(file=io.StringIO(), width=80, record=True)
    console.print(render_prompt(ed, state="idle", width=80))
    text = console.export_text()
    assert "hi" in text


def test_render_prompt_shows_decision_hint():
    import io

    from rich.console import Console

    ed = LineEditor()
    console = Console(file=io.StringIO(), width=100, record=True)
    console.print(render_prompt(ed, state="busy", pending_decision=True))
    assert "排队" in console.export_text()



# --------------------------------------------------------------------------- #
# 回合流式预览（输入框上方的区域）
# --------------------------------------------------------------------------- #

def _render_session(session, height=24):
    import io

    from rich.console import Console

    console = Console(file=io.StringIO(), width=80, height=height,
                      record=True)
    console.print(session.render())
    text = console.export_text()
    lines = text.splitlines()
    return text, lines


def test_preview_renders_above_the_input_box_and_clears():
    from rich.text import Text

    s = _HeadlessSession()
    assert not s.has_preview
    s.set_preview(Text("STREAM-BODY"))
    out, lines = _render_session(s)
    assert "STREAM-BODY" in out
    assert out.index("STREAM-BODY") < out.index("One Cedric")
    # 输入框顶边框必须独立成行：Group 不会自动补换行，
    # _TailView 漏了结尾换行时边框会跟预览末行挤在一起。
    assert any(line.lstrip().startswith("┌") for line in lines)
    assert not any("STREAM-BODY" in line and "┌" in line for line in lines)
    s.clear_preview()
    assert not s.has_preview
    out2, _ = _render_session(s)
    assert "STREAM-BODY" not in out2


def test_preview_keeps_the_tail_when_taller_than_the_screen():
    from rich.text import Text

    s = _HeadlessSession()
    s.set_preview(Text("\n".join(f"line-{i:03d}" for i in range(200))))
    out, lines = _render_session(s, height=24)
    assert "line-199" in out            # 最新内容可见
    assert "line-000" not in out        # 开头被裁掉，而不是结尾
    assert len(lines) <= 24             # 整帧（预览 + 输入框）不超屏
    assert any(line.lstrip().startswith("┌") for line in lines)


def test_mouse_tracking_defaults_off_and_can_be_enabled(monkeypatch):
    monkeypatch.delenv("ONE_CEDRIC_MOUSE", raising=False)
    assert mouse_tracking_enabled(None) is False
    assert mouse_tracking_enabled({}) is False
    assert mouse_tracking_enabled({"ui": {}}) is False
    assert mouse_tracking_enabled({"ui": {"mouse": True}}) is True
    monkeypatch.setenv("ONE_CEDRIC_MOUSE", "1")
    assert mouse_tracking_enabled({"ui": {"mouse": False}}) is True
    monkeypatch.setenv("ONE_CEDRIC_MOUSE", "0")
    assert mouse_tracking_enabled({"ui": {"mouse": True}}) is False


def test_session_does_not_enable_mouse_by_default():
    s = ReplInputSession(console=None)
    assert s.mouse is False


# --------------------------------------------------------------------------- #
# 提交回显（输入框被清空后用户还能看到自己发了什么）
# --------------------------------------------------------------------------- #

class _RecordingConsole:
    def __init__(self):
        self.printed = []

    def print(self, obj):
        self.printed.append(obj)


def test_read_line_echoes_submitted_text():
    s = _HeadlessSession()
    s.console = _RecordingConsole()
    s.poller.feed("hello\r")
    assert s.read_line() == "hello"
    assert len(s.console.printed) == 1
    assert "hello" in s.console.printed[0].plain


def test_read_line_echoes_pasted_batch_lines_in_order():
    s = _HeadlessSession()
    s.console = _RecordingConsole()
    s.poller.feed("one\rtwo\r")
    assert s.read_line() == "one"
    assert s.read_line() == "two"
    echoed = [obj.plain for obj in s.console.printed]
    assert "one" in echoed[0] and "two" in echoed[1]


def test_read_line_does_not_echo_empty_submit():
    s = _HeadlessSession()
    s.console = _RecordingConsole()
    s.poller.feed("\r")
    assert s.read_line() == ""
    assert s.console.printed == []


def _scripted_session(batches):
    """把 poller 换成按批次喂键的假实现（供 read_line 用）。"""
    s = _HeadlessSession()
    pending = [list(batch) for batch in batches]

    class _Poller:
        def poll(self):
            return pending.pop(0) if pending else []

        def wait(self, timeout):
            pass

    s.poller = _Poller()
    return s


def test_read_line_ctrl_c_clears_but_does_not_exit():
    s = _scripted_session([["\x03"], ["o", "k", KEY_ENTER]])
    s.console = _RecordingConsole()
    assert s.read_line() == "ok"
    assert s.editor.buffer == ""


def test_read_line_keyboard_interrupt_clears_and_continues():
    s = _scripted_session([])
    s.console = _RecordingConsole()
    calls = {"n": 0}

    class _Poller:
        def poll(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise KeyboardInterrupt
            return ["x", KEY_ENTER]

        def wait(self, timeout):
            pass

    s.poller = _Poller()
    assert s.read_line() == "x"


def test_read_line_returns_none_on_eof():
    s = _scripted_session([])
    s.console = _RecordingConsole()

    class _Poller:
        def poll(self):
            raise EOFError

        def wait(self, timeout):
            pass

    s.poller = _Poller()
    assert s.read_line() is None


def test_submitted_line_keeps_plain_markup_characters():
    from one_cedric.ui.live_input import submitted_line

    line = submitted_line("[bold]not markup[/] @file")
    assert "[bold]not markup[/] @file" in line.plain


# --------------------------------------------------------------------------- #
# 底栏状态（上下文占用 / git / 环境）
# --------------------------------------------------------------------------- #

def test_set_status_renders_ctx_line():
    s = _HeadlessSession()
    s.set_status(ctx_used=12345, ctx_max=128000)
    out, _ = _render_session(s)
    assert "ctx" in out and "128K" in out and "10%" in out


def test_status_signature_changes_with_ctx():
    s = _HeadlessSession()
    before = s._signature()
    s.set_status(ctx_used=10, ctx_max=100)
    assert s._signature() != before


def test_render_shows_git_and_env_parts():
    s = _HeadlessSession()
    s._git = {"branch": "main", "ahead": 0, "behind": 0,
              "changed": 2, "detached": False}
    s._env = "py3.13 venv"
    s.set_status(ctx_used=5, ctx_max=100)
    out, _ = _render_session(s)
    assert "main" in out and "±2" in out and "py3.13 venv" in out


def test_set_status_renders_turns_steps_cost_and_peak():
    s = _HeadlessSession()
    s.set_status(ctx_used=10, ctx_max=100, turns=3, steps=12,
                 cost=0.01234,
                 peak={"supported": True, "offpeak": True, "rate": 0.25})
    out, _ = _render_session(s)
    assert "轮3" in out and "步12" in out
    assert "$0.0123" in out and "谷" in out and "×0.25" in out


def test_status_signature_changes_with_cost_and_peak():
    s = _HeadlessSession()
    s.set_status(cost=0.1)
    before = s._signature()
    s.set_status(cost=0.2)
    assert s._signature() != before
    s.set_status(peak={"supported": True, "offpeak": True, "rate": 0.25})
    assert s._signature() != before


def test_set_status_peak_none_clears_the_tag():
    """模型切到没有峰谷差价的模型时，显式传 None 要把「谷/峰」摘掉。"""
    s = _HeadlessSession()
    s.set_status(ctx_used=10, ctx_max=100, turns=1, steps=2, cost=0.02,
                 peak={"supported": True, "offpeak": True, "rate": 0.25})
    out, _ = _render_session(s)
    assert "谷" in out
    s.set_status(peak=None)
    out, _ = _render_session(s)
    assert "谷" not in out and "峰" not in out
    # 没传的字段保持原值
    assert "轮1" in out and "步2" in out


def test_status_row_keeps_preview_frame_within_height():
    from rich.text import Text

    s = _HeadlessSession()
    s.set_status(ctx_used=1, ctx_max=1000)
    s.set_preview(Text("\n".join(f"line-{i:03d}" for i in range(200))))
    out, lines = _render_session(s, height=24)
    assert len(lines) <= 24
    assert "line-199" in out
    assert "ctx" in out


# --------------------------------------------------------------------------- #
# _StreamView：REPL 在场时把流式预览交给输入框的 Live
# --------------------------------------------------------------------------- #

def test_stream_view_delegates_to_repl_session():
    from one_cedric.core import _StreamView

    class _Repl:
        def __init__(self):
            self.preview = None
            self.cleared = False

        def set_preview(self, renderable):
            self.preview = renderable

        def clear_preview(self):
            self.cleared = True
            self.preview = None

    repl = _Repl()
    with _StreamView(None, repl, "thinking") as view:
        assert repl.preview == "thinking"
        view.update("body")
        assert repl.preview == "body"
    assert repl.cleared is True
    assert repl.preview is None
