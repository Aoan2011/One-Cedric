"""峰谷价格：窗口/时区解析、折扣匹配、按时刻计价与配置读写。"""
from __future__ import annotations

from datetime import datetime

import pytest

from one_cedric import pricing

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11
    try:
        import tomli as tomllib      # pytest pulls tomli on Python 3.10
    except ImportError:
        tomllib = None


def _cfg(**kw):
    cfg = {
        "enabled": True,
        "windows": "16:30-00:30",
        "tz": "UTC",
        "default_discount": 1.0,
        "discounts": {"deepseek-chat": 0.5, "deepseek-reasoner": 0.25},
    }
    cfg.update(kw)
    return cfg


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #

def test_parse_windows_supports_wrap_and_multiple():
    assert pricing.parse_windows("16:30-00:30") == [(990, 30)]
    assert pricing.parse_windows("10:00-14:00, 22:00~23:00") == [
        (600, 840), (1320, 1380)]
    assert pricing.parse_windows("garbage") == []
    assert pricing.parse_windows("10:00-10:00") == []


def test_parse_tz_offsets():
    assert pricing.parse_tz("UTC") == 0.0
    assert pricing.parse_tz("utc+8") == 8.0
    assert pricing.parse_tz("+8") == 8.0
    assert pricing.parse_tz("-5:30") == -5.5
    assert pricing.parse_tz("local") is None
    assert pricing.parse_tz("tomorrow") is None


def test_peak_rate_prefers_longest_match():
    cfg = _cfg()
    assert pricing.peak_rate("deepseek-reasoner", cfg) == 0.25
    assert pricing.peak_rate("deepseek-chat-0324", cfg) == 0.5
    assert pricing.peak_rate("gpt-4o", cfg) == 1.0
    assert pricing.peak_rate("", _cfg(default_discount=0.8)) == 0.8


def test_windows_text_and_duration_helpers():
    assert pricing.windows_text([(990, 30)]) == "16:30-00:30"
    assert pricing.format_duration(3 * 3600 + 12 * 60) == "3h12m"
    assert pricing.format_duration(45 * 60) == "45m"
    assert pricing.format_duration(30) == "30s"


# --------------------------------------------------------------------------- #
# 状态判定
# --------------------------------------------------------------------------- #

def test_peak_state_detects_offpeak_window(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config", lambda: _cfg())
    state = pricing.peak_state("deepseek-chat",
                               at=datetime(2026, 1, 1, 17, 0))
    assert state["supported"] and state["offpeak"]
    assert state["discount"] == 0.5
    assert state["seconds_to_change"] == 7 * 3600 + 30 * 60


def test_peak_state_detects_peak_window(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config", lambda: _cfg())
    state = pricing.peak_state("deepseek-chat",
                               at=datetime(2026, 1, 1, 12, 0))
    assert state["supported"] and not state["offpeak"]
    assert state["discount"] == 1.0
    assert state["seconds_to_change"] == (4 * 60 + 30) * 60


def test_peak_state_handles_midnight_edge(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config", lambda: _cfg())
    state = pricing.peak_state("deepseek-chat",
                               at=datetime(2026, 1, 1, 0, 10))
    assert state["offpeak"]
    assert state["seconds_to_change"] == 20 * 60


def test_peak_state_respects_timezone_offset(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config",
                        lambda: _cfg(tz="+8"))
    # +8 时区的 17:00 == UTC 09:00 → 谷价
    state = pricing.peak_state("deepseek-chat",
                               at=datetime(2026, 1, 1, 9, 0))
    assert state["offpeak"]


def test_peak_state_disabled(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config",
                        lambda: _cfg(enabled=False))
    state = pricing.peak_state("deepseek-chat",
                               at=datetime(2026, 1, 1, 17, 0))
    assert not state["enabled"] and not state["supported"]
    assert state["discount"] == 1.0


def test_peak_state_unsupported_model_still_reports_window(monkeypatch):
    monkeypatch.setattr(pricing, "load_peak_config", lambda: _cfg())
    state = pricing.peak_state("gpt-4o", at=datetime(2026, 1, 1, 17, 0))
    assert state["enabled"] and not state["supported"]
    assert state["offpeak"]


# --------------------------------------------------------------------------- #
# 计价
# --------------------------------------------------------------------------- #

def test_compute_cost_applies_offpeak_discount(monkeypatch):
    monkeypatch.setattr(pricing, "pricing_for",
                        lambda model: (0.0, 1.0, 2.0))
    monkeypatch.setattr(pricing, "load_peak_config", lambda: _cfg())
    day = pricing.compute_cost("deepseek-chat", 1_000_000, 500_000,
                               at=datetime(2026, 1, 1, 12, 0))
    night = pricing.compute_cost("deepseek-chat", 1_000_000, 500_000,
                                 at=datetime(2026, 1, 1, 17, 0))
    assert day == pytest.approx(2.0)
    assert night == pytest.approx(1.0)


def test_compute_cost_ignores_peak_when_disabled(monkeypatch):
    monkeypatch.setattr(pricing, "pricing_for",
                        lambda model: (0.0, 1.0, 0.0))
    monkeypatch.setattr(pricing, "load_peak_config",
                        lambda: _cfg(enabled=False))
    cost = pricing.compute_cost("deepseek-chat", 1_000_000, 0,
                                at=datetime(2026, 1, 1, 17, 0))
    assert cost == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 配置文件
# --------------------------------------------------------------------------- #

def _read(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


@pytest.mark.skipif(tomllib is None, reason="tomllib unavailable")
def test_save_peak_config_round_trip_keeps_models(tmp_path, monkeypatch):
    target = tmp_path / "pricing.toml"
    monkeypatch.setattr(pricing, "PRICING_PATH", target)

    assert pricing.save_user_pricing({"m1": (0.1, 0.2, 0.3)})
    cfg = pricing.load_peak_config()
    assert cfg["enabled"] is True
    assert cfg["discounts"]["deepseek-reasoner"] == 0.25

    cfg["enabled"] = False
    cfg["tz"] = "+8"
    cfg["discounts"]["acme"] = 0.1
    assert pricing.save_peak_config(cfg)
    raw = _read(target)
    assert raw["models"]["m1"]["output"] == 0.3
    assert raw["peak"]["enabled"] is False
    assert raw["peak"]["tz"] == "+8"
    assert raw["peak"]["discounts"]["acme"] == 0.1

    # 之后再保存 models 不会丢掉 [peak] 段
    assert pricing.save_user_pricing({"m2": (0.0, 1.0, 2.0)})
    raw2 = _read(target)
    assert raw2["peak"]["enabled"] is False
    assert raw2["peak"]["discounts"]["acme"] == 0.1
    assert raw2["models"]["m2"]["input"] == 1.0
    assert "m1" not in raw2["models"]


def test_apply_peak_preset_deepseek_and_off(tmp_path, monkeypatch):
    target = tmp_path / "pricing.toml"
    monkeypatch.setattr(pricing, "PRICING_PATH", target)

    ok, _ = pricing.apply_peak_preset("deepseek")
    assert ok
    cfg = pricing.load_peak_config()
    assert cfg["enabled"] and cfg["windows"] == "16:30-00:30"

    ok, _ = pricing.apply_peak_preset("nope")
    assert not ok

    ok, _ = pricing.apply_peak_preset("off")
    assert ok
    assert pricing.load_peak_config()["enabled"] is False
