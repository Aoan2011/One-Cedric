"""底栏状态：环境探测、git 摘要与状态行裁剪。"""
from __future__ import annotations

import io

from rich.cells import cell_len
from rich.console import Console

from one_cedric import git_snap
from one_cedric.ui import statusbar


def _plain(text) -> str:
    console = Console(file=io.StringIO(), width=200, record=True)
    console.print(text)
    return console.export_text()


# --------------------------------------------------------------------------- #
# git_brief_status
# --------------------------------------------------------------------------- #

def _runner(out: str, code: int = 0):
    def run(root, args, timeout=15):
        return code, out, ""
    return run


def test_git_brief_status_parses_branch_ahead_behind_and_changes():
    info = git_snap.git_brief_status(".", run=_runner(
        "## main...origin/main [ahead 1, behind 2]\n"
        " M a.py\n"
        "?? b.py\n"
        " M c.py\n"))
    assert info == {"branch": "main", "ahead": 1, "behind": 2,
                    "changed": 3, "detached": False}


def test_git_brief_status_clean_branch():
    info = git_snap.git_brief_status(".", run=_runner("## main\n"))
    assert info == {"branch": "main", "ahead": 0, "behind": 0,
                    "changed": 0, "detached": False}


def test_git_brief_status_detached_head():
    info = git_snap.git_brief_status(".", run=_runner("## HEAD (no branch)\n"))
    assert info["detached"] is True
    assert info["branch"] == "detached"


def test_git_brief_status_no_commits_yet():
    info = git_snap.git_brief_status(
        ".", run=_runner("## No commits yet on dev\n"))
    assert info["branch"] == "dev"


def test_git_brief_status_returns_none_outside_a_repo():
    assert git_snap.git_brief_status(
        ".", run=_runner("", code=128)) is None


# --------------------------------------------------------------------------- #
# gather_env
# --------------------------------------------------------------------------- #

def test_gather_env_detects_python_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    env = statusbar.gather_env(tmp_path, probe=lambda argv: "")
    assert env.startswith("py")


def test_gather_env_marks_inactive_dot_venv(tmp_path):
    (tmp_path / ".venv").mkdir()
    env = statusbar.gather_env(tmp_path, probe=lambda argv: "")
    assert ".venv" in env or "venv" in env


def test_gather_env_node_with_package_manager(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    env = statusbar.gather_env(
        tmp_path,
        probe=lambda argv: "v22.14.0" if argv[0] == "node" else "")
    assert "node22.14" in env
    assert "pnpm" in env


def test_gather_env_rust_and_go(tmp_path):
    (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")
    (tmp_path / "go.mod").write_text("", encoding="utf-8")

    def probe(argv):
        if argv[0] == "cargo":
            return "cargo 1.83.0 (5ffbef321 2024-10-29)"
        return "go version go1.22.1 windows/amd64"

    env = statusbar.gather_env(tmp_path, probe=probe)
    assert "rust1.83" in env
    assert "go1.22" in env


def test_gather_env_falls_back_to_python_without_markers(tmp_path):
    env = statusbar.gather_env(tmp_path, probe=lambda argv: "")
    assert env.startswith("py")


# --------------------------------------------------------------------------- #
# format_status
# --------------------------------------------------------------------------- #

def _git(branch="main", ahead=1, behind=0, changed=3, detached=False):
    return {"branch": branch, "ahead": ahead, "behind": behind,
            "changed": changed, "detached": detached}


def test_format_status_none_without_any_data():
    assert statusbar.format_status(None, None, None, "", 80) is None


def test_format_status_shows_ctx_git_and_env():
    text = statusbar.format_status(
        12345, 128000, _git(), "py3.13 venv", 160, powerline=False)
    out = _plain(text)
    assert "ctx 12K/128K 10%" in out
    assert "main" in out and "↑1" in out and "±3" in out
    assert "py3.13 venv" in out


def test_format_status_shows_turns_steps_and_cost():
    text = statusbar.format_status(
        None, None, None, "", 160, turns=3, steps=12, cost=0.01234,
        powerline=False)
    out = _plain(text)
    assert "轮3" in out and "步12" in out
    assert "$0.0123" in out


def test_format_status_cost_zero_is_not_free():
    text = statusbar.format_status(None, None, None, "", 80, cost=0.0,
                                   powerline=False)
    assert "$0" in _plain(text)


def test_cost_group_marks_offpeak_and_peak():
    off = statusbar.format_status(
        None, None, None, "", 160, cost=0.5,
        peak={"supported": True, "offpeak": True, "rate": 0.25},
        powerline=False)
    assert "谷" in off.plain and "×0.25" in off.plain
    peak = statusbar.format_status(
        None, None, None, "", 160, cost=0.5,
        peak={"supported": True, "offpeak": False, "rate": 0.25},
        powerline=False)
    assert "峰" in peak.plain and "谷" not in peak.plain
    plain = statusbar.format_status(
        None, None, None, "", 160, cost=0.5,
        peak={"supported": False, "offpeak": True, "rate": 1.0},
        powerline=False)
    assert "谷" not in plain.plain and "峰" not in plain.plain


def test_format_status_highlights_values_and_state_colors():
    from one_cedric.config import ACCENT, OK_C, WARN_C

    text = statusbar.format_status(
        45678, 128000, _git(), "py3.14 venv pnpm", 160, powerline=False)
    styles = {str(span.style) for span in text.spans}
    assert any(ACCENT in style for style in styles)   # 数值 / 分支高亮
    assert any(WARN_C in style for style in styles)   # 脏工作区警示
    assert any(OK_C in style for style in styles)     # venv 绿色
    assert any("dim" == style for style in styles)    # 标签保持低调


def test_powerline_renders_arrow_segments_with_backgrounds():
    text = statusbar.format_status(
        1000, 10000, _git(), "py3.13 venv", 200,
        turns=1, steps=2, cost=0.5, powerline=True)
    assert statusbar.PL_ARROW in text.plain
    styles = {str(span.style) for span in text.spans}
    assert any(statusbar.PL_BG["ctx"] in style for style in styles)
    assert any(statusbar.PL_BG["count"] in style for style in styles)
    assert any(statusbar.PL_BG["cost"] in style for style in styles)
    assert text.plain.endswith(statusbar.PL_ARROW)


def test_powerline_ctx_warning_switches_segment_color():
    text = statusbar.format_status(950, 1000, None, "", 120,
                                   powerline=True)
    styles = {str(span.style) for span in text.spans}
    assert any(statusbar.PL_BG["ctx_err"] in style for style in styles)


def test_format_status_drops_right_groups_when_too_narrow():
    text = statusbar.format_status(
        10, 1000,
        _git(branch="feature/" + "x" * 60, ahead=0, changed=12),
        "py3.13 node22 pnpm", 40, powerline=False)
    assert text is not None
    assert "feature/" not in text.plain           # git 段被丢弃
    assert "py3.13" not in text.plain             # 环境段被丢弃
    assert "ctx 10/1.0K 1%" in text.plain


def test_powerline_drops_groups_that_do_not_fit():
    text = statusbar.format_status(
        10, 1000,
        _git(branch="feature/" + "x" * 60, ahead=0, changed=12),
        "py3.13 node22 pnpm", 34, turns=3, steps=12, cost=0.001,
        powerline=True)
    assert text is not None
    assert "ctx" in text.plain and "轮3" in text.plain
    assert "feature/" not in text.plain
    assert "py3.13" not in text.plain
    assert statusbar.PL_ARROW in text.plain


def test_powerline_crops_single_group_without_ellipsis_overflow():
    text = statusbar.format_status(
        123456, 200000, None, "", 24, powerline=True)
    assert text is not None
    assert cell_len(text.plain) <= 24 - 6 + 1


def test_format_status_skips_empty_git_dict():
    assert statusbar.format_status(None, None, {}, "", 80) is None


def test_git_marker_falls_back_to_text_without_nerd_font():
    from one_cedric.ui import icons

    icons.configure(False)
    try:
        text = statusbar.format_status(
            None, None, _git(branch="dev", ahead=0, changed=0), "", 80)
        assert text is not None
        assert text.plain.startswith("git dev")
    finally:
        icons.configure(True)


def test_format_status_marks_high_context_usage():
    warn = statusbar.format_status(750, 1000, None, "", 80)
    err = statusbar.format_status(950, 1000, None, "", 80)
    assert warn.spans and err.spans
    warn_styles = {str(s.style) for s in warn.spans}
    err_styles = {str(s.style) for s in err.spans}
    assert any("bold" in style for style in warn_styles)
    assert any("bold" in style for style in err_styles)
