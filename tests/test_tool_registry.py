"""Invariants for the 250-tool registry.

The registry is the contract between the model, the permission layer and the
implementation. A drift here silently breaks tools, so every relationship
between ``schema.py`` and ``_dispatch.py`` is asserted.
"""
from __future__ import annotations

import json

import pytest

from one_cedric.tools import schema as S
from one_cedric.tools._dispatch import _HANDLERS, is_core_handled


def _schema_names() -> list[str]:
    return [t["function"]["name"] for t in S.TOOLS]


@pytest.fixture(scope="module")
def names() -> list[str]:
    return _schema_names()


def test_schema_is_non_empty_and_plausible(names):
    assert len(names) > 200, "the project advertises 240+ built-in tools"


def test_tool_names_are_unique(names):
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"duplicate tool names: {duplicates}"


def test_every_schema_entry_is_well_formed():
    for entry in S.TOOLS:
        assert entry.get("type") == "function", entry.get("type")
        fn = entry.get("function")
        assert isinstance(fn, dict)
        name = fn.get("name")
        assert isinstance(name, str) and name.strip(), entry
        assert name == name.strip()
        assert isinstance(fn.get("description"), str) and fn["description"].strip(), name
        params = fn.get("parameters")
        assert isinstance(params, dict), name
        assert params.get("type") == "object", name
        props = params.get("properties", {})
        assert isinstance(props, dict), name
        # Every required key must actually be declared.
        for key in params.get("required", []):
            assert key in props, f"{name}: required '{key}' is not declared in properties"
        # The parameters must survive a JSON round trip (they are sent on the wire).
        json.dumps(params)


def test_write_and_readonly_sets_are_disjoint():
    """A tool must never be both write and read-only.

    Three tools (image_process, pdf_metadata, sysop) expose a read-only
    preview op and a writing apply op. WRITE_TOOLS must win, otherwise plan
    mode and sub-agents are allowed to modify files.
    """
    overlap = set(S.WRITE_TOOLS) & set(S.READONLY_TOOL_NAMES)
    assert not overlap, f"tools classified as both write and read-only: {sorted(overlap)}"


def test_ambiguous_tools_are_treated_as_writes():
    for name in S.AMBIGUOUS_READONLY_WRITE_TOOLS:
        assert name in S.WRITE_TOOLS
        assert name not in S.READONLY_TOOL_NAMES
        assert name not in {t["function"]["name"] for t in S.TOOLS_READONLY}


def test_policy_sets_reference_real_tools(names):
    known = set(names)
    for label, group in (
        ("WRITE_TOOLS", S.WRITE_TOOLS),
        ("READONLY_TOOL_NAMES", S.READONLY_TOOL_NAMES),
        ("CACHEABLE_TOOLS", S.CACHEABLE_TOOLS),
    ):
        unknown = sorted(set(group) - known)
        assert not unknown, f"{label} names tools that are not in the schema: {unknown}"


def test_cacheable_tools_are_read_only():
    leaked = sorted(set(S.CACHEABLE_TOOLS) - set(S.READONLY_TOOL_NAMES))
    assert not leaked, (
        f"cacheable tools must be read-only, otherwise a cached result could "
        f"hide a write: {leaked}")


def test_every_tool_is_routable(names):
    """Each schema tool must reach an implementation.

    Either a handler is registered in _dispatch, or the core layer owns it
    (write tools and tools that need agent state).
    """
    unrouted = sorted(
        n for n in names
        if n not in _HANDLERS and not is_core_handled(n)
    )
    assert not unrouted, f"tools exposed to the model but not routed anywhere: {unrouted}"


def test_no_orphan_handlers(names):
    """A registered handler that no schema advertises is dead code."""
    orphan = sorted(set(_HANDLERS) - set(names))
    assert not orphan, f"handlers registered but not exposed to the model: {orphan}"


def test_readonly_schema_subset_matches_policy():
    subset = {t["function"]["name"] for t in S.TOOLS_READONLY}
    assert subset == set(S.READONLY_TOOL_NAMES)


def test_core_handled_write_tools_never_exposed_as_readonly():
    for name in S.WRITE_TOOLS:
        if is_core_handled(name):
            assert name not in S.READONLY_TOOL_NAMES, name


def test_handler_signature_is_callable_with_root_and_args():
    """Handlers are called as ``fn(root, args)`` — check they accept two args."""
    import inspect

    bad = []
    for name, fn in _HANDLERS.items():
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):  # C builtins etc.
            continue
        params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(params) < 2 and not any(
            p.kind is p.VAR_POSITIONAL for p in sig.parameters.values()
        ):
            bad.append((name, str(sig)))
    assert not bad, f"handlers that cannot be called as fn(root, args): {bad}"
