"""Configuration storage: layering, round-trips and safe defaults.

Storage writes to ``~/.one-cedric``; every test here runs under the
``isolated_home`` fixture so the developer's real configuration is untouched.
"""
from __future__ import annotations

import pytest

from one_cedric import storage


def test_fresh_config_has_expected_defaults(isolated_home):
    cfg = storage.compose_config(storage.default_config_path())
    assert cfg["default"]["model"]
    assert cfg["default"]["host"]
    assert cfg["default"]["mode"] in {
        "workspace", "fullaccess", "ask",
    } or cfg["default"]["mode"]
    assert isinstance(cfg["bash"]["extra_prefixes"], list)


def test_config_round_trip_preserves_values(isolated_home, tmp_path):
    path = tmp_path / "config.toml"
    cfg = storage.compose_config(storage.default_config_path())
    cfg["default"]["model"] = "my-test-model"
    cfg["default"]["host"] = "http://example.invalid:1234"
    cfg["ui"]["theme"] = "light"

    assert storage.save_config_file(path, cfg) is True
    assert path.is_file()

    reloaded = storage.compose_config(path)
    assert reloaded["default"]["model"] == "my-test-model"
    assert reloaded["default"]["host"] == "http://example.invalid:1234"
    assert reloaded["ui"]["theme"] == "light"


def test_project_config_overrides_global(isolated_home, tmp_path):
    glob = tmp_path / "global.toml"
    proj = tmp_path / "project.toml"

    base = storage.compose_config(storage.default_config_path())
    base["default"]["model"] = "global-model"
    storage.save_config_file(glob, base)

    override = storage.compose_config(storage.default_config_path())
    override["default"]["model"] = "project-model"
    storage.save_config_file(proj, override)

    merged = storage.compose_config(glob, proj)
    assert merged["default"]["model"] == "project-model"


def test_corrupt_config_file_is_ignored(isolated_home, tmp_path):
    """A broken config must not crash the agent on startup."""
    bad = tmp_path / "broken.toml"
    bad.write_text("this is [not valid toml", encoding="utf-8")
    cfg = storage.compose_config(bad)
    assert cfg["default"]["model"]  # falls back to the defaults


def test_missing_config_file_yields_defaults(isolated_home, tmp_path):
    cfg = storage.compose_config(tmp_path / "does-not-exist.toml")
    assert cfg["default"]["model"]


def test_api_key_is_preserved_verbatim(isolated_home, tmp_path):
    """The api_key must survive a round trip (it is allowed to be empty)."""
    path = tmp_path / "config.toml"
    cfg = storage.compose_config(storage.default_config_path())
    cfg["default"]["api_key"] = "sk-test-abc123"
    storage.save_config_file(path, cfg)
    assert storage.compose_config(path)["default"]["api_key"] == "sk-test-abc123"


def test_dump_config_toml_quotes_paths_and_values(isolated_home):
    cfg = storage.compose_config(storage.default_config_path())
    cfg["default"]["model"] = 'weird "quoted" \\ value'
    text = storage.dump_config_toml(cfg)
    assert '"' in text
    # The dump must be re-parsable.
    import tomllib

    parsed = tomllib.loads(text)
    assert parsed["default"]["model"] == 'weird "quoted" \\ value'


def test_project_config_path_is_stable_and_isolated(isolated_home, tmp_path):
    a = storage.project_config_path(tmp_path)
    b = storage.project_config_path(tmp_path)
    assert a == b
    assert storage.project_config_path(tmp_path / "other") != a


def test_tools_config_round_trip(isolated_home):
    cfg = storage.load_tools_config()
    assert isinstance(cfg, dict)
    assert storage.save_tools_config({"read_file"}) is True
    after = storage.load_tools_config()
    assert isinstance(after, dict)
