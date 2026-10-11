"""The three-layer shell policy and the sandbox environment scrubber.

A model-generated command is untrusted input, so the classifier is the single
most security-relevant piece of logic in the project.
"""
from __future__ import annotations

import os

import pytest

from one_cedric.tools.shell import classify_command, merge_bash_prefixes


@pytest.mark.parametrize("command,expected", [
    # Level 0 — permanently refused
    ("rm -rf /", "blocked"),
    ("rm -rf /*", "blocked"),
    ("dd if=/dev/zero of=/dev/sda", "blocked"),
    ("format c:", "blocked"),
    ("rm important.txt", "blocked"),          # `rm` is blacklisted outright
    ("del important.txt", "blocked"),
    ("sudo rm file", "blocked"),
    ("icacls C:\\ /grant everyone:F", "blocked"),
    ("mkfs.ext4 /dev/sdb", "blocked"),
    # shell metacharacters outside quotes are refused
    ("ls | grep secret", "blocked"),
    ("cat a.txt > b.txt", "blocked"),
    ("echo hi && rm -rf /", "blocked"),
    ("cmd; other", "blocked"),
    ("echo $(whoami)", "blocked"),
    # Level 1 — whitelisted, runs directly
    ("git status", "whitelist"),
    ("git diff", "whitelist"),
    ("python -m pytest", "whitelist"),
    ("python -m ruff check .", "whitelist"),
    ("ruff check", "whitelist"),
    ("pip list", "whitelist"),
    ("python --version", "whitelist"),
    # Level 2 — known command, single confirmation
    ("ls -la", "known"),
    ("cat notes.txt", "known"),
    ("grep -n x notes.txt", "known"),
    ("git push origin main", "known"),
    # Level 3 — unknown, strong warning
    ("frobnicate --all", "unknown"),
    ("my-custom-script.exe run", "unknown"),
])
def test_classify_command_levels(command, expected):
    level, reason = classify_command(command)
    assert level == expected, f"{command!r} -> {level} ({reason})"


@pytest.mark.parametrize("command", ["", "   "])
def test_empty_command_is_blocked(command):
    level, reason = classify_command(command)
    assert level == "blocked"
    assert reason


def test_unbalanced_quotes_are_blocked_not_crashing():
    level, reason = classify_command("echo 'unterminated")
    assert level == "blocked"
    assert reason


def test_executable_suffixes_are_normalised():
    """`sudo.exe` must not slip past the blacklist."""
    level, _ = classify_command("rm.exe file.txt")
    assert level == "blocked"


def test_blacklist_wins_over_whitelist():
    """A blacklisted binary can never be whitelisted by a prefix match."""
    level, _ = classify_command("git status")
    assert level == "whitelist"
    level, _ = classify_command("chmod 777 file")
    assert level == "blocked"


def test_merge_bash_prefixes_extends_the_whitelist():
    merge_bash_prefixes(["mytool --safe"])
    level, _ = classify_command("mytool --safe run")
    assert level == "whitelist"
    # The same call must be idempotent.
    merge_bash_prefixes(["mytool --safe"])
    assert classify_command("mytool --safe run")[0] == "whitelist"


def test_merge_bash_prefixes_ignores_garbage():
    merge_bash_prefixes(["", "   ", "'unterminated"])
    assert classify_command("mytool --safe run")[0] == "whitelist"


# --------------------------------------------------------------------------- #
# Sandbox environment scrubbing
# --------------------------------------------------------------------------- #

def _sandbox_env(monkeypatch, extra: dict) -> dict:
    from one_cedric.core import _sandbox_env as scrub

    for key, value in extra.items():
        monkeypatch.setenv(key, value)
    return scrub()


@pytest.mark.parametrize("secret_name", [
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "NPM_TOKEN",
    "MY_PASSWORD",
    "DB_PASSWD",
    "SOME_CREDENTIAL",
    "SESSION_ID",
    "AUTH_HEADER",
    "PRIVATE_KEY",
    "COOKIE_JAR",
    "SIGNATURE_V1",
])
def test_sandbox_env_strips_sensitive_variables(monkeypatch, secret_name):
    env = _sandbox_env(monkeypatch, {secret_name: "super-secret-value"})
    assert secret_name not in env, (
        f"{secret_name} leaked into the sandbox environment")


def test_sandbox_env_keeps_harmless_variables(monkeypatch):
    env = _sandbox_env(monkeypatch, {"ONE_CEDRIC_TEST_HARMLESS": "ok"})
    assert env.get("ONE_CEDRIC_TEST_HARMLESS") == "ok"


def test_sandbox_env_marks_itself(monkeypatch):
    env = _sandbox_env(monkeypatch, {})
    assert env.get("ONECEDRIC_SANDBOX") == "1"


def test_sandbox_env_never_returns_the_live_environ_object(monkeypatch):
    """The scrubber must copy, otherwise tools would mutate the real env."""
    import one_cedric.core as core

    env = _sandbox_env(monkeypatch, {"SECRET_X": "v"})
    assert env is not os.environ
    assert env is not core.os.environ
