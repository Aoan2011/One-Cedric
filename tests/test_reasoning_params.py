"""推理模型开关：``reasoning_effort`` / ``thinking`` 是否真的进入请求参数。"""
from __future__ import annotations

import pytest

from one_cedric.config import (
    is_reasoning_model_name,
    normalize_reasoning_mode,
)


def test_normalize_reasoning_mode_accepts_bool_and_strings():
    assert normalize_reasoning_mode(True) == "on"
    assert normalize_reasoning_mode(False) == "off"
    assert normalize_reasoning_mode("ON") == "on"
    assert normalize_reasoning_mode("true") == "on"
    assert normalize_reasoning_mode("off") == "off"
    assert normalize_reasoning_mode("0") == "off"
    assert normalize_reasoning_mode("auto") == "auto"
    assert normalize_reasoning_mode("") == "auto"
    assert normalize_reasoning_mode("garbage") == "auto"


def test_is_reasoning_model_name():
    assert is_reasoning_model_name("deepseek-v4.1-flash")
    assert is_reasoning_model_name("o3-mini")
    assert is_reasoning_model_name("gpt-5.1")
    assert is_reasoning_model_name("claude-sonnet-4")
    assert is_reasoning_model_name("qwq-32b")
    assert not is_reasoning_model_name("llama3.1:8b")
    assert not is_reasoning_model_name("qwen2.5:7b")


# --------------------------------------------------------------------------- #
# OneCedric._think_params（不初始化完整实例，只挂必要属性）
# --------------------------------------------------------------------------- #

@pytest.fixture
def think_params(monkeypatch):
    from one_cedric.core import OneCedric
    from one_cedric.ui.screens import models as models_screen

    overrides: dict = {}

    def fake_override(model):
        return dict(overrides.get(model, {}))

    monkeypatch.setattr(models_screen, "get_model_override", fake_override)
    monkeypatch.delenv("ONE_CEDRIC_REASONING_MODEL", raising=False)

    def _make(model, think_level="high", config=None, override=None):
        client = OneCedric.__new__(OneCedric)
        client.model = model
        client.think_level = think_level
        client.config = config or {}
        if override is not None:
            overrides[model] = override
        return client

    return _make


def test_auto_sends_reasoning_effort_for_known_reasoning_models(think_params):
    client = think_params("o3-mini")
    assert client._think_params()["reasoning_effort"] == "high"
    client = think_params("deepseek-v4.1-flash")
    assert client._think_params()["reasoning_effort"] == "high"


def test_auto_leaves_plain_models_alone(think_params):
    client = think_params("llama3.1:8b")
    params = client._think_params()
    assert "reasoning_effort" not in params
    assert "thinking" not in params


def test_explicit_on_sends_reasoning_effort_for_any_model(think_params):
    client = think_params("llama3.1:8b", override={"reasoning_model": "on"})
    assert client._think_params()["reasoning_effort"] == "high"


def test_explicit_off_silences_known_reasoning_models(think_params):
    client = think_params("o3-mini", override={"reasoning_model": "off"})
    params = client._think_params()
    assert "reasoning_effort" not in params
    assert "thinking" not in params


def test_claude_gets_thinking_budget_instead(think_params):
    client = think_params("claude-sonnet-4", think_level="medium")
    assert client._think_params()["thinking"] == {
        "type": "enabled", "budget_tokens": 8192}


def test_claude_minimal_disables_thinking(think_params):
    client = think_params("claude-sonnet-4", think_level="minimal")
    assert "thinking" not in client._think_params()


def test_config_default_applies_without_override(think_params):
    client = think_params(
        "llama3.1:8b", config={"default": {"reasoning_model": "on"}})
    assert client._think_params()["reasoning_effort"] == "high"


def test_override_beats_config_default(think_params):
    client = think_params(
        "llama3.1:8b", config={"default": {"reasoning_model": "on"}},
        override={"reasoning_model": "off"})
    assert "reasoning_effort" not in client._think_params()


def test_env_var_beats_everything(think_params, monkeypatch):
    client = think_params("o3-mini")
    monkeypatch.setenv("ONE_CEDRIC_REASONING_MODEL", "off")
    assert "reasoning_effort" not in client._think_params()
    monkeypatch.setenv("ONE_CEDRIC_REASONING_MODEL", "on")
    assert client._think_params()["reasoning_effort"] == "high"


def test_per_model_think_level_override_wins(think_params):
    client = think_params(
        "o3-mini", think_level="minimal",
        override={"think_level": "ultra"})
    assert client._think_params()["reasoning_effort"] == "ultra"
