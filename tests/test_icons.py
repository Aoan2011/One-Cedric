"""Nerd Font 图标注册表测试。

三件事必须钉死：

1. ``_CODEPOINTS`` 里每个码点都和 ``assets/nf-icons.json`` 一致
   （资产是唯一事实来源，硬编码只是缓存）；
2. 关闭开关时字形回退到原来的 Unicode / ASCII，行为与旧版完全一致；
3. 环境变量 ``ONE_CEDRIC_NERD_FONT`` > 配置 ``[ui].nerd_font`` > 默认开启。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from one_cedric.ui import icons

ASSET = (pathlib.Path(__file__).resolve().parents[1]
         / "assets" / "nf-icons.json")


def _asset_codepoints() -> dict[str, int]:
    table: dict[str, int] = {}
    for entry in json.loads(ASSET.read_text(encoding="utf-8")):
        code = str(entry.get("codepoint") or "")
        if "code=" not in code:
            continue
        hexstr = code.split("code=")[-1].rstrip("}").split(";")[0].strip()
        table[str(entry.get("name"))] = int(hexstr, 16)
    return table


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """每个用例都从「未解析 + 无环境变量」开始，结束后也恢复。"""
    monkeypatch.delenv("ONE_CEDRIC_NERD_FONT", raising=False)
    icons.reset()
    yield
    icons.reset()


# --------------------------------------------------------------------------- #
# 与资产核对
# --------------------------------------------------------------------------- #

def test_codepoints_match_the_asset():
    asset = _asset_codepoints()
    for name, cp in icons._CODEPOINTS.items():
        assert name in asset, f"{name} 不在 assets/nf-icons.json"
        assert cp == asset[name], f"{name} 码点漂移"


def test_every_catalog_entry_has_a_codepoint():
    missing = sorted({name for name, _ in icons.CATALOG.values()
                      if name not in icons._CODEPOINTS})
    assert missing == []


def test_catalog_fallbacks_are_plain_text():
    for key, (_name, fallback) in icons.CATALOG.items():
        assert fallback, f"{key} 的回退字形不能为空"
        # 允许 "#️⃣"（# + VS16 + 键帽符）这种三字符序列
        assert len(fallback) <= 3, f"{key} 的回退字形异常: {fallback!r}"


# --------------------------------------------------------------------------- #
# 开关与解析
# --------------------------------------------------------------------------- #

def test_default_is_enabled(monkeypatch):
    # 没有环境变量、没有配置文件时默认开启（配置读取走 tmp HOME 之外，
    # _config_flag 失败时返回 None → DEFAULT_ENABLED）
    assert icons.enabled() is True


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "enable"])
def test_env_truthy_values_enable(monkeypatch, value):
    monkeypatch.setenv("ONE_CEDRIC_NERD_FONT", value)
    assert icons.enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "NO", "off", "disable"])
def test_env_falsy_values_disable(monkeypatch, value):
    monkeypatch.setenv("ONE_CEDRIC_NERD_FONT", value)
    assert icons.enabled() is False


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("ONE_CEDRIC_NERD_FONT", "0")
    assert icons.configure_from_config({"ui": {"nerd_font": True}}) is False
    icons.reset()
    monkeypatch.setenv("ONE_CEDRIC_NERD_FONT", "1")
    assert icons.configure_from_config({"ui": {"nerd_font": False}}) is True


def test_config_flag_used_when_env_missing():
    assert icons.configure_from_config({"ui": {"nerd_font": False}}) is False
    assert icons.enabled() is False
    icons.reset()
    assert icons.configure_from_config({"ui": {"nerd_font": True}}) is True


def test_configure_and_reset():
    icons.configure(False)
    assert icons.enabled() is False
    icons.configure(True)
    assert icons.enabled() is True
    icons.reset()
    assert icons.enabled() is True


# --------------------------------------------------------------------------- #
# glyph()
# --------------------------------------------------------------------------- #

def test_glyph_uses_fallback_when_disabled():
    icons.configure(False)
    assert icons.glyph("ok") == "✓"
    assert icons.glyph("prompt") == "❯"
    assert icons.glyph("search") == "⌕"


def test_glyph_uses_nerd_codepoint_when_enabled():
    icons.configure(True)
    assert icons.glyph("ok") == chr(icons._CODEPOINTS["nf-md-check_circle"])
    assert icons.glyph("prompt") == chr(
        icons._CODEPOINTS["nf-md-chevron_right"])
    assert icons.glyph("search") == chr(icons._CODEPOINTS["nf-md-magnify"])


def test_glyph_unknown_key_returns_default():
    icons.configure(True)
    assert icons.glyph("no-such-icon", "x") == "x"
    assert icons.glyph("no-such-icon") == ""


# --------------------------------------------------------------------------- #
# replace_emoji()
# --------------------------------------------------------------------------- #

def test_replace_emoji_is_identity_when_disabled():
    icons.configure(False)
    text = "📖 🔍 ✏️ ⚡"
    assert icons.replace_emoji(text) == text


def test_replace_emoji_maps_and_drops_variation_selector():
    icons.configure(True)
    out = icons.replace_emoji("📖 ✏️")
    assert out == (chr(icons._CODEPOINTS["nf-md-book_open_page_variant"]) +
                   " " + chr(icons._CODEPOINTS["nf-md-pencil_outline"]))
    assert "\ufe0f" not in out


def test_replace_emoji_keeps_unknown_text():
    icons.configure(True)
    assert icons.replace_emoji("plain ASCII") == "plain ASCII"
    assert icons.replace_emoji("中文不动") == "中文不动"


def test_replace_emoji_handles_keycap():
    icons.configure(True)
    out = icons.replace_emoji("#️⃣ ")
    assert out == chr(icons._CODEPOINTS["nf-md-pound"]) + " "


def test_all_spinner_frame_emoji_are_mapped():
    """legacy.py 的 spinner 帧里每个 emoji 都必须能被替换。"""
    from one_cedric.ui.legacy import TOOL_SPINNERS
    icons.configure(True)
    for name, spec in TOOL_SPINNERS.items():
        for frame in spec.get("frames", []):
            replaced = icons.replace_emoji(frame)
            assert replaced == frame or replaced != "", name
            for ch in replaced:
                # 替换后不允许再出现 emoji 区字符（CJK 等除外）
                assert not (0x1F000 <= ord(ch) <= 0x1FAFF), \
                    f"{name}: {frame!r} 残留 {ch!r}"


# --------------------------------------------------------------------------- #
# process_markup() / CedricConsole
# --------------------------------------------------------------------------- #

def test_tag_glyph_keys_all_exist_in_catalog():
    missing = sorted({k for k in icons._TAG_GLYPH_KEYS.values()
                      if k not in icons.CATALOG})
    assert missing == []


def test_process_markup_only_touches_glyphs_after_tags():
    icons.configure(True)
    out = icons.process_markup("[ok]✓ done[/]  [err]✗ nope[/]")
    assert out == (f"[ok]{icons.glyph('ok')} done[/]  "
                   f"[err]{icons.glyph('error')} nope[/]")
    # 正文里的同样字形（没有标记前缀）不动
    plain = "冒烟：3 ✓ / 2 ✗ 是正文"
    assert icons.process_markup(plain) == plain


def test_process_markup_is_identity_when_disabled():
    icons.configure(False)
    text = "[ok]✓ done[/] [warn]⚠ careful[/]"
    assert icons.process_markup(text) == text


def test_process_markup_maps_diamond_and_triangle():
    icons.configure(True)
    out = icons.process_markup("[bold]◆ 工具管理[/] [accent]▸[/]")
    assert out == (f"[bold]{icons.glyph('diamond_filled')} 工具管理[/] "
                   f"[accent]{icons.glyph('collapse')}[/]")


def test_cedric_console_transforms_status_glyphs():
    import io as _io

    from one_cedric.ui.console import CedricConsole

    def render() -> str:
        buf = _io.StringIO()
        console = CedricConsole(file=buf, width=80, no_color=True,
                                force_terminal=False, soft_wrap=True)
        console.print("[ok]✓ 全部完成[/]")
        return buf.getvalue()

    icons.configure(True)
    assert icons.glyph("ok") in render()
    icons.configure(False)
    assert "✓ 全部完成" in render()
