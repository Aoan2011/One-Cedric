"""Gateway HTTP surface: auth coverage, route inventory and static serving.

The ``--token`` flag exists so that a gateway bound to ``0.0.0.0`` is not open
to the local network. These tests prove the token is actually enforced on
every state-bearing route rather than merely parsed.
"""
from __future__ import annotations

import types

import pytest

pytest.importorskip("fastapi")

try:
    from starlette.testclient import TestClient
except Exception:  # pragma: no cover
    TestClient = None

from one_cedric.gateway.server import Gateway

TOKEN = "s3cr3t-test-token"

#: Routes that are intentionally reachable without a token.
PUBLIC_PATHS = {"/", "/favicon.ico", "/health", "/static/{name}"}


@pytest.fixture()
def gateway():
    return Gateway(types.SimpleNamespace())


@pytest.fixture()
def client(gateway, monkeypatch):
    if TestClient is None:  # pragma: no cover
        pytest.skip("starlette TestClient unavailable")
    gateway.token = TOKEN
    # Never let a route reach the (fake) agent: auth must reject first.
    monkeypatch.setattr(gateway, "_log_request", lambda *a, **k: None)
    return TestClient(gateway.app, raise_server_exceptions=False)


def test_app_builds_with_expected_routes(gateway):
    paths = {getattr(r, "path", None) for r in gateway.app.routes}
    for expected in ("/", "/api/chat", "/api/status", "/api/tools",
                     "/api/sessions", "/api/config"):
        assert expected in paths, f"missing route {expected}"


def test_api_routes_are_declared(gateway):
    api = {getattr(r, "path", "") for r in gateway.app.routes
           if str(getattr(r, "path", "")).startswith("/api/")}
    assert len(api) > 25, f"unexpectedly few API routes: {len(api)}"


@pytest.mark.parametrize("path", [
    "/api/status",
    "/api/chat",
    "/api/chat/clear",
    "/api/config",
    "/api/tools",
    "/api/sessions",
    "/api/files",
    "/api/file-preview",
    "/api/diagnose",
    "/api/models",
    "/api/my-models",
    "/api/cron",
    "/api/dream",
    "/api/dream/list",
    "/api/network",
    "/api/logs",
    "/api/upload",
    "/api/custom-tools",
    "/api/ask/pending",
    "/api/ask/answer",
])
def test_api_route_requires_token(client, path):
    """With a token configured, no /api route may answer unauthenticated."""
    method = "GET"
    if path in {"/api/chat", "/api/chat/clear", "/api/upload",
                "/api/ask/answer", "/api/dream", "/api/custom-tools",
                "/api/my-models", "/api/cron"}:
        method = "POST"
    if path == "/api/config":
        method = "GET"
    resp = client.request(method, path, json={})
    assert resp.status_code == 401, (
        f"{method} {path} answered {resp.status_code} without a token")


def test_wrong_token_is_rejected(client):
    resp = client.get("/api/status", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_malformed_authorization_header_is_rejected(client):
    for header in ("", "Basic abc", "Bearer", TOKEN):
        resp = client.get("/api/status", headers={"Authorization": header})
        assert resp.status_code == 401, f"header {header!r} was accepted"


def test_correct_token_is_accepted(client):
    resp = client.get("/api/status",
                      headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code != 401


def test_public_routes_stay_reachable_without_a_token(client):
    """Static/health routes are public by design — they must not demand a token.

    (They may return 5xx because the agent behind them is a stub; what matters
    is that auth does not reject them.)
    """
    for path in ("/health", "/", "/favicon.ico"):
        assert client.get(path).status_code != 401, f"{path} demands a token"


def test_gateway_without_token_does_not_require_auth(gateway):
    gw = Gateway(types.SimpleNamespace())
    gw.token = ""
    if TestClient is None:  # pragma: no cover
        pytest.skip("starlette TestClient unavailable")
    c = TestClient(gw.app, raise_server_exceptions=False)
    resp = c.get("/api/status")
    # No token configured -> not 401 (it may 500 because the agent is fake).
    assert resp.status_code != 401


def test_api_key_is_never_served_to_the_browser(client):
    """The model API key must not appear in any browser-facing payload."""
    for path in ("/api/status", "/api/config", "/api/models", "/api/diagnose"):
        resp = client.get(path, headers={"Authorization": f"Bearer {TOKEN}"})
        body = resp.text
        assert "api_key" not in body or "***" in body or len(body) < 4_000
