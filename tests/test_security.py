"""Regression tests for the security audit findings (SECURITY_AUDIT.md).

Each test pins one hardening decision so it cannot silently regress.
"""
from __future__ import annotations

import types

import pytest

from one_cedric.tools.shell import classify_command

pytest.importorskip("fastapi")
try:
    from starlette.testclient import TestClient
except Exception:  # pragma: no cover
    TestClient = None

TOKEN = "audit-token"


# --------------------------------------------------------------------------- #
# SEC-04 — interpreter inline execution must never be auto-trusted
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("command", [
    'python -c "import os; os.system(\'calc\')"',
    'python3 -c "print(1)"',
    'py -c "x"',
    'node -e "require(\'child_process\').execSync(\'calc\')"',
    'perl -e "system(\'calc\')"',
    'ruby -e "system(\'calc\')"',
    'php -r "system(\'calc\');"',
    'powershell -Command "Start-Process calc"',
    'pwsh -c "Start-Process calc"',
    'cmd /c "calc"',
    'bash -c "calc"',
    'sh -c "calc"',
])
def test_interpreter_inline_execution_is_never_whitelisted(command):
    level, reason = classify_command(command)
    assert level == "unknown", (
        f"{command!r} was classified {level!r} ({reason}); inline interpreter "
        f"execution must require a forced confirmation")
    assert reason


def test_ordinary_module_invocation_stays_whitelisted():
    """The fix must not break the legitimate `python -m pytest` shortcut."""
    assert classify_command("python -m pytest")[0] == "whitelist"
    assert classify_command("python -m ruff check .")[0] == "whitelist"


def test_plain_script_run_is_still_known_not_blocked():
    level, _ = classify_command("python script.py")
    assert level == "known"


# --------------------------------------------------------------------------- #
# SEC-06 — the sandbox env scrubber must catch more credential shapes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "DB_PASS", "MYSQL_PASS", "PASSPHRASE",
    "SLACK_WEBHOOK", "DISCORD_WEBHOOK_URL",
    "BEARER_CRED", "DATABASE_DSN", "SENTRY_DSN",
    "PG_CONNECTION", "REDIS_CONN_STR",
    "SMTP_HOST", "IMAP_SERVER",
    "ALIYUN_ACCESS_ID", "TENCENT_SECRET_ID",
])
def test_sandbox_env_strips_audit_keywords(monkeypatch, name):
    from one_cedric.core import _sandbox_env

    monkeypatch.setenv(name, "leak")
    assert name not in _sandbox_env()


# --------------------------------------------------------------------------- #
# SEC-02 / SEC-16 — the gateway must ship hardening response headers
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client():
    if TestClient is None:  # pragma: no cover
        pytest.skip("starlette TestClient unavailable")
    from one_cedric.gateway.server import Gateway

    gw = Gateway(types.SimpleNamespace(root=".", api_key=""))
    gw.token = TOKEN
    return TestClient(gw.app, raise_server_exceptions=False)


def test_security_headers_are_present(client):
    resp = client.get("/")
    csp = resp.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp, f"weak or missing CSP: {csp!r}"
    assert "'unsafe-inline'" not in csp.split("style-src")[0], (
        "script-src must not allow inline scripts")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


def test_index_html_has_no_inline_script():
    """A CSP without 'unsafe-inline' only works if the page has no inline JS."""
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "one_cedric" / "gateway"
            / "webui" / "index.html").read_text(encoding="utf-8")
    import re

    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE)
    assert not inline, f"index.html still has inline <script> blocks: {inline}"


def test_webui_sanitizes_markdown_before_v_html():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "one_cedric" / "gateway"
          / "webui" / "app.js").read_text(encoding="utf-8")
    assert "function sanitizeHtml" in js
    assert "sanitizeHtml(marked.parse" in js, (
        "marked output must pass through sanitizeHtml before rendering")
    assert "_BLOCKED_TAGS" in js


def test_auto_approve_defaults_to_off():
    """SEC-01: the WebUI must not auto-confirm tool calls by default."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "one_cedric" / "gateway"
          / "webui" / "app.js").read_text(encoding="utf-8")
    assert "const autoApprove = ref(false)" in js
    assert "const autoApprove = ref(true)" not in js


# --------------------------------------------------------------------------- #
# SEC-12 — /api/tools/{name}/call must not bypass the permission layer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["bash", "write_file", "python_exec",
                                  "edit_file", "apply_patch"])
def test_tool_call_endpoint_refuses_write_tools(client, name):
    resp = client.post(f"/api/tools/{name}/call",
                       json={"arguments": {}},
                       headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 403, (
        f"/api/tools/{name}/call allowed a write tool through ({resp.status_code})")


def test_cli_prompt_mode_does_not_force_auto_yes():
    """SEC-04 amplifier: `--prompt` must not silently disable confirmations."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "one_cedric"
           / "cli.py").read_text(encoding="utf-8")
    assert "if args.prompt:\n        auto_yes = True" not in src
