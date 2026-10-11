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
    KEY_LEFT,
    KeyPoller,
    LineEditor,
    MidTurnQueue,
    ReplInputSession,
    apply_key,
    parse_sgr_mouse,
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


def test_decision_constants_are_distinct():
    assert len({DECISION_QUEUE, DECISION_INTERJECT, DECISION_CANCEL}) == 3


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
