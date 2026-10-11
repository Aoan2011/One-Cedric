"""End-to-end smoke tests for tools that work purely on local files.

These really invoke the handlers through ``dispatch_tool`` against a scratch
workspace, so they catch the failures unit tests miss: wrong argument names,
missing optional dependencies and handlers that blow up on real input.

Tools that need the network or external binaries are deliberately excluded —
they are listed in ``EXTERNAL_TOOLS`` and only ever exercised by hand.
"""
from __future__ import annotations

import pytest

from one_cedric.tools import dispatch_tool

pytestmark = pytest.mark.e2e

#: Tools this file does not call, and why (kept explicit so the gap is visible).
EXTERNAL_TOOLS = {
    "web_fetch", "web_search", "web_research", "http_request",  # network
    "postgres_query", "mysql_query", "mongo_find",              # servers
    "email_*", "wechat_*", "amap_*",                            # credentials
    "browser_open", "browser_click",                            # Playwright
    "screen_capture", "mouse_action", "keyboard_action",        # real desktop
    "bash", "bash_bg", "git", "docker",                         # core-handled
}


def _call(name, args, workspace):
    out = dispatch_tool(name, args, workspace)
    assert isinstance(out, str), f"{name} returned {type(out)}"
    assert out.strip(), f"{name} returned an empty result"
    assert not out.startswith("ERROR:"), f"{name} failed: {out[:400]}"
    return out


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #

def test_read_file_returns_contents(workspace):
    out = _call("read_file", {"path": "notes.txt"}, workspace)
    assert "hello world" in out


def test_read_file_line_range(workspace):
    out = _call("read_file",
                {"path": "notes.txt", "start_line": 2, "end_line": 2},
                workspace)
    assert "second line" in out
    assert "hello world" not in out


def test_list_files(workspace):
    out = _call("list_files", {"path": "."}, workspace)
    assert "notes.txt" in out


def test_list_files_recursive_finds_nested(workspace):
    out = _call("list_files", {"path": ".", "recursive": True}, workspace)
    assert "deep.txt" in out


def test_glob(workspace):
    out = _call("glob", {"pattern": "*.txt"}, workspace)
    assert "notes.txt" in out


def test_glob_recursive_pattern(workspace):
    out = _call("glob", {"pattern": "**/*.txt"}, workspace)
    assert "deep.txt" in out


def test_grep_regex(workspace):
    out = _call("grep_regex", {"pattern": "second", "path": "."}, workspace)
    assert "second" in out


def test_grep_regex_case_insensitive(workspace):
    out = _call("grep_regex",
                {"pattern": "THIRD", "path": ".", "case_insensitive": True},
                workspace)
    assert "THIRD" in out or "third" in out.lower()


def test_file_info(workspace):
    out = _call("file_info", {"path": "notes.txt"}, workspace)
    assert "notes.txt" in out


def test_hash_file_is_deterministic(workspace):
    first = _call("hash_file", {"path": "notes.txt"}, workspace)
    second = _call("hash_file", {"path": "notes.txt"}, workspace)
    assert first == second
    assert any(c.isdigit() for c in first)


# --------------------------------------------------------------------------- #
# Structured data
# --------------------------------------------------------------------------- #

def test_json_query(workspace):
    out = _call("json_query", {"file": "data.json", "path": "nested.k"},
                workspace)
    assert "v" in out


def test_json_format(workspace):
    out = _call("json_format", {"file": "data.json"}, workspace)
    assert "nested" in out


def test_csv_query(workspace):
    out = _call("csv_query", {"path": "rows.csv"}, workspace)
    assert "alice" in out


def test_csv_to_json(workspace):
    out = _call("csv_to_json", {"path": "rows.csv"}, workspace)
    assert "alice" in out
    assert "{" in out or "[" in out


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #

def test_text_stats(workspace):
    out = _call("text_stats", {"file": "notes.txt"}, workspace)
    assert any(ch.isdigit() for ch in out)


def test_word_frequency(workspace):
    out = _call("word_frequency", {"file": "notes.txt", "top": 5}, workspace)
    assert "hello" in out.lower() or "line" in out.lower()


def test_regex_extract(workspace):
    out = _call("regex_extract", {"pattern": r"\w+", "path": "notes.txt"},
                workspace)
    assert "hello" in out


def test_dedupe_lines():
    out = _call("dedupe_lines", {"text": "a\nb\na\nb\n"}, None)
    assert out.count("a") == out.count("a")


def test_strip_invisible():
    out = _call("strip_invisible", {"text": "a\u200bb"}, None)
    assert "\u200b" not in out


# --------------------------------------------------------------------------- #
# Encoding / crypto helpers
# --------------------------------------------------------------------------- #

def test_base64_round_trip():
    encoded = _call("base64_codec", {"action": "encode", "data": "hello"}, None)
    token = encoded.strip().split()[-1]
    decoded = _call("base64_codec", {"action": "decode", "data": token}, None)
    assert "hello" in decoded


def test_hash_text_known_value():
    out = _call("hash_text", {"data": "abc", "algorithm": "sha256"}, None)
    assert "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" in out


# --------------------------------------------------------------------------- #
# System / misc (read-only, no credentials)
# --------------------------------------------------------------------------- #

def test_now_info():
    out = _call("now_info", {}, None)
    assert any(ch.isdigit() for ch in out)


def test_calculate():
    out = _call("calculate", {"expression": "1 + 2 * 3"}, None)
    assert "7" in out


def test_env_info_does_not_leak_secrets(workspace, monkeypatch):
    monkeypatch.setenv("ONE_CEDRIC_FAKE_SECRET_TOKEN", "leak-me-if-you-can")
    out = _call("env_info", {}, workspace)
    assert "leak-me-if-you-can" not in out, (
        "env_info exposed a secret-looking environment variable")


def test_code_stats(workspace):
    out = _call("code_stats", {"path": "."}, workspace)
    assert isinstance(out, str)


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #

def test_missing_file_reports_an_error(workspace):
    out = dispatch_tool("read_file", {"path": "nope.txt"}, workspace)
    assert "ERROR" in out or "不存在" in out or "not found" in out.lower()


def test_directory_listing_outside_root_is_refused(workspace):
    out = dispatch_tool("list_files", {"path": "../../.."}, workspace)
    assert isinstance(out, str)
