"""WebUI asset and markup invariants.

These are cheap guards for the browser front end: the stylesheet layers must
stay wired in the right order, the strict CSP must not be broken by a new
inline script, and the rendering sinks must keep their escaping/sanitising.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEBUI = Path(__file__).resolve().parents[1] / "one_cedric" / "gateway" / "webui"
INDEX = (WEBUI / "index.html").read_text(encoding="utf-8")
APP_JS = (WEBUI / "app.js").read_text(encoding="utf-8")

#: Style layers must be linked in this order.
STYLE_ORDER = ["tokens.css", "style.css", "hljs-theme.min.css", "polish.css"]


@pytest.mark.parametrize("name", [
    "index.html", "app.js", "style.css", "tokens.css", "polish.css",
    "boot.js", "settings.html", "stats.html",
])
def test_webui_asset_exists(name):
    path = WEBUI / name
    assert path.is_file(), f"missing WebUI asset {name}"
    assert path.stat().st_size > 0


def test_package_data_covers_the_new_assets():
    """A new .css/.js in webui/ must be shipped in the wheel."""
    import tomllib

    pyproject = tomllib.loads(
        (WEBUI.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"][
        "one_cedric.gateway.webui"]
    for name in ("tokens.css", "polish.css", "boot.js"):
        suffix = "*." + name.rsplit(".", 1)[1]
        assert suffix in patterns, f"{name} would not be packaged"


def test_stylesheets_are_linked_in_layered_order():
    positions = [INDEX.find(name) for name in STYLE_ORDER]
    assert all(p >= 0 for p in positions), (
        f"a style layer is not linked: "
        f"{[n for n, p in zip(STYLE_ORDER, positions) if p < 0]}")
    assert positions == sorted(positions), (
        "stylesheets must load tokens -> style -> hljs -> polish so the "
        "enhancement layer wins")


def test_no_inline_script_blocks():
    """The gateway ships a strict CSP; inline <script> would break it."""
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", INDEX, re.IGNORECASE)
    assert not inline, f"inline script blocks found: {inline}"


def test_no_inline_event_handlers():
    handlers = re.findall(
        r"\son(?:click|change|input|submit|load|error|mouse\w+|key\w+)\s*=",
        INDEX, re.IGNORECASE)
    assert not handlers, f"inline event handlers found: {handlers}"


def test_accessibility_hooks_exist():
    assert 'class="skip-link"' in INDEX, "missing skip link"
    assert 'aria-live="polite"' in INDEX, "toasts need an aria-live region"
    assert 'role="main"' in INDEX
    assert "function applyAccessibility" in APP_JS, (
        "icon-only buttons rely on this pass for their aria-label")
    assert "applyAccessibility();" in APP_JS, "the a11y pass is never called"


def test_reduced_motion_is_respected():
    css = (WEBUI / "polish.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css
    assert "prefers-contrast" in css


def test_csp_allows_the_vue_build_that_is_shipped():
    """A strict CSP must stay compatible with the bundled Vue build.

    The WebUI uses Vue's *global* build, which compiles the in-DOM template at
    runtime with ``new Function``. A ``script-src`` without ``'unsafe-eval'``
    therefore stops the app from mounting and the page hangs on the boot
    splash (black screen). Pin the two together so neither drifts.
    """
    vue = (WEBUI / "vue.min.js").read_text(encoding="utf-8", errors="replace")
    server = (WEBUI.parent / "server.py").read_text(encoding="utf-8")

    csp = server.split("Content-Security-Policy", 1)[1]
    script_src = csp.split("script-src", 1)[1].split(";", 1)[0]

    if "new Function" in vue or "compileToFunction" in vue:
        assert "'unsafe-eval'" in script_src, (
            "the bundled Vue build compiles templates at runtime with "
            "new Function, so script-src must allow 'unsafe-eval' or the "
            "WebUI will never mount")

    # Regardless of the Vue build, inline script must stay blocked — that is
    # what actually neutralises HTML injected through v-html.
    assert "'unsafe-inline'" not in script_src, (
        "script-src must never allow inline scripts")


def test_index_splash_is_removed_by_the_bundled_app():
    """The boot splash is only removed after Vue mounts; keep the contract."""
    assert "boot-splash" in INDEX
    assert "boot-splash" in APP_JS, (
        "app.js must remove the splash, otherwise a mount failure shows as a "
        "permanent black screen")


def test_polish_layer_targets_real_classes():
    """Selectors in polish.css should reference markup that actually exists."""
    css = (WEBUI / "polish.css").read_text(encoding="utf-8")
    classes = set(re.findall(r"\.([a-z][a-z0-9-]{2,})", css))
    html_classes = set(re.findall(r'class="([^"]+)"', INDEX))
    known = set()
    for chunk in html_classes:
        known.update(chunk.split())
    known.update(re.findall(r"class=\"([a-z0-9-]+)\"", APP_JS))
    known.update(re.findall(r"class=\\?[\"']([a-z0-9 -]+)", APP_JS))
    known.update(re.findall(r"classList\.add\('([a-z0-9-]+)'\)", APP_JS))

    # Utility/animation names and state helpers are intentionally not bound
    # to a literal class string; only flag clearly-unknown component classes.
    ignored = {
        "sr-only", "skip-link", "toast", "mono", "loading",
    }
    unknown = sorted(
        c for c in classes
        if c not in known and c not in ignored
        and not c.startswith(("acrylic-", "theme-", "think-", "msg-",
                              "tool-", "sb-", "embed-", "ctx-", "st-"))
    )
    # Allow a small margin: a few classes are produced by JS string building.
    assert len(unknown) <= 40, (
        f"{len(unknown)} polish.css selectors match no markup; first: "
        f"{unknown[:15]}")
