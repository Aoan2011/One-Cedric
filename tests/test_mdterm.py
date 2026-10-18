"""mdterm：终端侧 !!!关键!!! / ==高亮== / LaTeX 降级渲染。"""
from one_cedric.mdterm import (
    CedricMarkdown,
    degrade_markdown,
    iter_segments,
    tex_to_unicode,
)


def _render_styled(md, width=70):
    from rich.console import Console

    from one_cedric.config import THEME

    console = Console(record=True, force_terminal=True,
                      color_system="truecolor", theme=THEME, width=width)
    console.print(md)
    styled = console.export_text(styles=True, clear=False)
    plain = console.export_text(clear=False)
    return styled, plain


# ── !!!关键!!! ────────────────────────────────────────────────────────

def test_key_becomes_kbd():
    assert degrade_markdown("结论：!!!必须一次!!! 完") == \
        "结论：<kbd>必须一次</kbd> 完"
    assert degrade_markdown("!!! x !!!") == "<kbd>x</kbd>"


def test_key_requires_content():
    assert degrade_markdown("!!!!") == "!!!!"
    assert degrade_markdown("!!!   !!!") == "!!!   !!!"
    assert degrade_markdown("!!!未闭合") == "!!!未闭合"


def test_key_inner_degrades_too():
    assert degrade_markdown(r"!!!$\alpha^2$!!!") == "<kbd>`α²`</kbd>"


def test_key_renders_green_background():
    styled, plain = _render_styled(CedricMarkdown("结论：!!!关键!!! 完"))
    assert "48;2;158;206;106" in styled        # OK_C 绿底（WebUI --ok）
    assert "1;30;48;2;158;206;106" in styled   # bold black on #9ece6a
    assert "!!!" not in plain
    assert "关键" in plain


def test_md_with_cursor_renders_key_and_math():
    from one_cedric.core import _md_with_cursor

    styled, plain = _render_styled(
        _md_with_cursor("结论：!!!就一次!!!，公式 $x^2$。"))
    assert "48;2;158;206;106" in styled
    assert "!!!" not in plain
    assert "$x^2$" not in plain
    assert "x²" in plain


# ── ==高亮== ──────────────────────────────────────────────────────────

def test_mark_becomes_bold():
    assert degrade_markdown("==重点==") == "**重点**"
    assert degrade_markdown("a ==b== c") == "a **b** c"


def test_mark_rejects_blank_and_equals():
    assert degrade_markdown("== 空 ==") == "== 空 =="
    assert degrade_markdown("==x ==") == "==x =="


# ── 公式：价格启发式与空白规则（对齐 cedric-md.js） ───────────────────

def test_prices_untouched():
    assert degrade_markdown("价格 $5 和 $10 与 $5$") == "价格 $5 和 $10 与 `5`"


def test_dollar_math_heuristics():
    assert degrade_markdown("$x$2") == "$x$2"        # 收尾后跟数字：价格
    assert degrade_markdown("$ x$") == "$ x$"        # 起止留空白：不当公式
    assert degrade_markdown("$x $") == "$x $"
    assert degrade_markdown("$x^2+y^2$") == "`x²+y²`"


def test_paren_and_bracket_math():
    assert degrade_markdown(r"\(a+b\)") == "`a+b`"
    assert degrade_markdown(r"\[E=mc^2\]") == "```\nE=mc²\n```"


def test_display_math_block_and_fence():
    out = degrade_markdown(r"$$\frac{1}{2} + \sum_{i=1}^{n} x_i$$")
    assert out == "```\n1/2 + ∑ᵢ₌₁ⁿ xᵢ\n```"
    out = degrade_markdown("```math\n\\sqrt{2} \\approx 1.414\n```")
    assert out == "```\n√(2) ≈ 1.414\n```"
    # 非独占行不按块级处理：交给行内规则
    assert degrade_markdown("$$x$$ 尾巴") == "`x` 尾巴"


# ── 代码保护 ──────────────────────────────────────────────────────────

def test_fenced_code_untouched():
    src = "```\n!!!$x$-not-math\n```"
    assert degrade_markdown(src) == src


def test_inline_code_untouched():
    assert degrade_markdown("`$x$` 与 `!!!a!!!`") == "`$x$` 与 `!!!a!!!`"


def test_text_without_markup_fast_path():
    for text in ("", "普通文本", "C:\\Users\\path"):
        assert degrade_markdown(text) == text


# ── TeX → Unicode ─────────────────────────────────────────────────────

def test_tex_symbols_and_scripts():
    assert tex_to_unicode(r"\alpha+\beta \le \infty") == "α+β ≤ ∞"
    assert tex_to_unicode("x_1^2 + x_{n+1}") == "x₁² + xₙ₊₁"
    assert tex_to_unicode(r"2^{-k}") == "2⁻ᵏ"
    assert tex_to_unicode(r"x^{\alpha}") == "x^(α)"      # 无法上标：降级


def test_tex_frac_sqrt():
    assert tex_to_unicode(r"\frac{1}{2}") == "1/2"
    assert tex_to_unicode(r"\frac{a+b}{c}") == "(a+b)/(c)"
    assert tex_to_unicode(r"\sqrt{2}") == "√(2)"
    assert tex_to_unicode(r"\sqrt[3]{x}") == "3√(x)"


def test_tex_env_matrix():
    out = tex_to_unicode(r"\begin{matrix} a & b \\ c & d \end{matrix}")
    assert out == "a  b\nc  d"
    out = tex_to_unicode(r"\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}")
    assert "1  0" in out and out.startswith("(")


def test_tex_text_cmd_and_blackboard():
    assert tex_to_unicode(r"\text{速度 } v = \frac{s}{t}") == "速度  v = s/t"
    assert tex_to_unicode(r"\mathbb{R}^n \subset \mathbb{C}") == "ℝⁿ ⊂ ℂ"
    assert tex_to_unicode(r"\mathbf{v} = \vec{a}") == "v = a⃗"


def test_tex_unknown_and_malformed_never_raises():
    assert "\\foo" in tex_to_unicode(r"\foo{bar}")
    for bad in ("", "$", r"\frac{1", r"\left(", "{{{{", "x^", "\\begin{matrix}"):
        assert isinstance(tex_to_unicode(bad), str)


# ── TUI 分段 ──────────────────────────────────────────────────────────

def test_iter_segments_kinds():
    segs = iter_segments("前 !!!重点!!! 中 ==加粗== 尾 $x_1$")
    assert segs == [
        ("前 ", ""),
        ("重点", "key"),
        (" 中 ", ""),
        ("加粗", "bold"),
        (" 尾 ", ""),
        ("x₁", "math"),
    ]


def test_iter_segments_empty_and_plain():
    assert iter_segments("") == []
    assert iter_segments("没有标记") == [("没有标记", "")]
