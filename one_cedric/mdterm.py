"""终端侧 Markdown 降级渲染（!!!关键!!! / ==高亮== / LaTeX 公式）。

WebUI 有 KaTeX，终端没有。这里做「尽力而为」的降级，让终端里不再看到
裸的 ``!!!`` 标记与裸的 TeX：

* ``!!!内容!!!`` → Rich Markdown 的 ``<kbd>``（主题键 ``markdown.kbd``，
  绿底黑字）；TUI 由 :func:`iter_segments` 直接给出绿底样式段。
* ``==内容==`` → ``**加粗**``；TUI 给 ``bold``。
* 公式（``$…$``、``\\(…\\)``、``$$…$$``、``\\[…\\]``、```math 围栏）→
  TeX 转 Unicode 文本（:func:`tex_to_unicode`）。行内公式渲染成行内代码
  ——终端无法排版公式，等宽反而和正文区分得最清楚；块级公式渲染成围栏块。
* 围栏代码与行内代码一律原样透传，不做任何替换。

词法规则与 ``gateway/webui/cedric-md.js`` 对齐：价格启发式（``$5`` 不当
公式）、``$`` 内首尾不留空白、``==`` 首尾空白/``=`` 拒绝、代码保护。
"""

from __future__ import annotations

import re

from rich.markdown import Markdown

__all__ = [
    "CedricMarkdown",
    "degrade_markdown",
    "iter_segments",
    "tex_to_unicode",
]

# ═══════════════════════════════════════════════════════════════════════ #
# TeX → Unicode 符号表
# ═══════════════════════════════════════════════════════════════════════ #

_SYMBOLS = {
    # 希腊字母
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "varepsilon": "ε", "vartheta": "ϑ", "varphi": "φ", "varrho": "ϱ",
    "varsigma": "ς", "varpi": "ϖ",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
    # 关系 / 运算
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "equiv": "≡", "approx": "≈", "sim": "∼", "simeq": "≃", "cong": "≅",
    "propto": "∝", "ll": "≪", "gg": "≫", "subset": "⊂", "supset": "⊃",
    "subseteq": "⊆", "supseteq": "⊇", "nsubseteq": "⊈", "in": "∈",
    "notin": "∉", "ni": "∋", "forall": "∀", "exists": "∃", "nexists": "∄",
    "emptyset": "∅", "varnothing": "∅", "cup": "∪", "cap": "∩",
    "setminus": "∖", "sqcup": "⊔", "sqcap": "⊓", "wedge": "∧",
    "vee": "∨", "land": "∧", "lor": "∨", "neg": "¬", "lnot": "¬",
    "top": "⊤", "bot": "⊥", "perp": "⊥", "angle": "∠", "parallel": "∥",
    "circ": "∘", "bullet": "•", "star": "⋆", "dagger": "†", "ddagger": "‡",
    "oplus": "⊕", "otimes": "⊗", "ominus": "⊖", "odot": "⊙",
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "⋅",
    "ast": "∗", "hbar": "ℏ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ",
    "aleph": "ℵ", "infty": "∞", "partial": "∂", "nabla": "∇",
    "degree": "°", "prime": "′",
    # 省略号
    "ldots": "…", "dots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    # 箭头
    "to": "→", "rightarrow": "→", "Rightarrow": "⇒", "leftarrow": "←",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "Leftrightarrow": "⇔",
    "mapsto": "↦", "uparrow": "↑", "downarrow": "↓", "updownarrow": "↕",
    "hookrightarrow": "↪", "hookleftarrow": "↩", "longrightarrow": "⟶",
    "longleftarrow": "⟵", "implies": "⟹", "iff": "⟺", "gets": "←",
    # 大运算符
    "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "iiint": "∭", "oint": "∮", "bigcup": "⋃", "bigcap": "⋂",
    "bigoplus": "⨁", "bigotimes": "⨂", "bigodot": "⨀", "bigvee": "⋁",
    "bigwedge": "⋀",
    # 函数名（按文字排出）
    "log": "log", "ln": "ln", "lg": "lg", "sin": "sin", "cos": "cos",
    "tan": "tan", "cot": "cot", "sec": "sec", "csc": "csc",
    "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh", "exp": "exp",
    "lim": "lim", "limsup": "lim sup", "liminf": "lim inf", "max": "max",
    "min": "min", "sup": "sup", "inf": "inf", "gcd": "gcd", "det": "det",
    "dim": "dim", "ker": "ker", "arg": "arg", "deg": "deg", "bmod": "mod",
    # 括号类（供 \left/\right 与独立命令使用）
    "langle": "⟨", "rangle": "⟩", "lVert": "‖", "rVert": "‖", "Vert": "‖",
    "lvert": "|", "rvert": "|", "lbrace": "{", "rbrace": "}",
    "lbrack": "[", "rbrack": "]", "lceil": "⌈", "rceil": "⌉",
    "lfloor": "⌊", "rfloor": "⌋",
}

#: 带一个参数、内容原样保留的排版命令
_WRAP_CMDS = {
    "text", "textrm", "textnormal", "textsf", "texttt", "textbf",
    "textit", "textup", "textsl", "mathrm", "mathbf", "mathit",
    "mathsf", "mathtt", "mathcal", "mathbb", "mathfrak", "boldsymbol",
    "bm", "operatorname", "operatornamewithlimits",
}

#: \mathbb 单字符 → 黑板体
_BLACKBOARD = {
    "R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ",
    "H": "ℍ", "F": "𝔽", "P": "ℙ",
}

_FRAC_CMDS = {"frac", "dfrac", "tfrac", "cfrac"}
_SQRT_CMDS = {"sqrt"}
_ACCENT_CMDS = {
    "vec": "\u20d7", "bar": "\u0304", "hat": "\u0302", "tilde": "\u0303",
    "dot": "\u0307", "ddot": "\u0308", "acute": "\u0301", "grave": "\u0300",
}
_DELIM_CMDS = {
    "left", "right", "middle",
    "big", "Big", "bigg", "Bigg",
    "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr",
}
_DELIMS = {
    "(": "(", ")": ")", "[": "[", "]": "]", "|": "|", ".": "",
    "/": "/", "<": "⟨", ">": "⟩",
}
_SPACES = {
    "quad": "  ", "qquad": "    ", "enspace": " ", "thinspace": "",
    "space": " ", "nobreakspace": " ",
}

#: 矩阵类环境：& 分列、\\ 分行
_MATRIX_ENVS = {
    "matrix", "smallmatrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix",
    "Vmatrix", "array", "aligned", "align", "align*", "gathered", "gather",
    "gather*", "cases", "split",
}
_MATRIX_WRAP = {
    "pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"),
    "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"), "cases": ("{", ""),
}

_SUP_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
    "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼",
    "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ",
    "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ",
    "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "A": "ᴬ", "B": "ᴮ", "D": "ᴰ", "E": "ᴱ", "G": "ᴳ", "H": "ᴴ", "I": "ᴵ",
    "J": "ᴶ", "K": "ᴷ", "L": "ᴸ", "M": "ᴹ", "N": "ᴺ", "O": "ᴼ", "P": "ᴾ",
    "R": "ᴿ", "T": "ᵀ", "U": "ᵁ", "V": "ⱽ", "W": "ᵂ",
}
_SUB_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
    "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "−": "₋", "=": "₌",
    "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ",
    "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ",
    "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}


# ═══════════════════════════════════════════════════════════════════════ #
# TeX → Unicode
# ═══════════════════════════════════════════════════════════════════════ #

def _read_cmd(s: str, i: int) -> tuple[str, int]:
    """``i`` 指向 ``\\``；返回 (命令名, 下一个下标)。"""
    j = i + 1
    n = len(s)
    while j < n and s[j].isascii() and s[j].isalpha():
        j += 1
    return s[i + 1:j], j


def _read_group(s: str, i: int) -> tuple[str, int]:
    """``i`` 指向 ``{``；返回 (括号内容, 下一个下标)。不闭合时吃到结尾。"""
    start = i + 1
    depth = 0
    j = i
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:j], j + 1
        j += 1
    return s[start:], n


def _read_script_arg(s: str, i: int) -> tuple[str, int]:
    if i < len(s) and s[i] == "{":
        return _read_group(s, i)
    if i < len(s):
        return s[i], i + 1
    return "", i


def _skip_space(s: str, i: int) -> int:
    n = len(s)
    while i < n and s[i] in " \t":
        i += 1
    return i


def _map_script(content: str, table: dict) -> str | None:
    if not content:
        return None
    out = []
    for ch in content:
        u = table.get(ch)
        if u is None:
            return None
        out.append(u)
    return "".join(out)


def _tex_escape(s: str, i: int) -> tuple[str, int]:
    """``\\`` 后不是字母的转义（``\\{`` ``\\,`` ``\\\\`` …）。"""
    nxt = s[i + 1] if i + 1 < len(s) else ""
    if nxt in "{}%&$#_":
        return nxt, i + 2
    if nxt in ",;:!":
        return "", i + 2                      # 细空格 / 负空格
    if nxt == " ":
        return " ", i + 2
    if nxt == "\\":
        return "\n", i + 2                    # TeX 换行
    if not nxt:
        return "\\", i + 1
    return nxt, i + 2


def _frac(s: str, j: int) -> tuple[str | None, int]:
    k = _skip_space(s, j)
    if k >= len(s) or s[k] != "{":
        return None, j
    num, k2 = _read_group(s, k)
    k3 = _skip_space(s, k2)
    if k3 >= len(s) or s[k3] != "{":
        return None, j
    den, k4 = _read_group(s, k3)
    num_u, den_u = _convert(num), _convert(den)
    if len(num_u) == 1 and len(den_u) == 1:
        return f"{num_u}/{den_u}", k4
    return f"({num_u})/({den_u})", k4


def _sqrt(s: str, j: int) -> tuple[str | None, int]:
    k = _skip_space(s, j)
    root = ""
    if k < len(s) and s[k] == "[":
        e = s.find("]", k + 1)
        if e != -1:
            root = _convert(s[k + 1:e])
            k = e + 1
    if k < len(s) and s[k] == "{":
        inner, k2 = _read_group(s, k)
        body = _convert(inner)
        return (f"{root}√({body})" if root else f"√({body})"), k2
    return None, j


def _delim(s: str, k: int) -> tuple[str, int]:
    if k >= len(s):
        return "", k
    if s[k] == "\\":
        if k + 1 < len(s) and s[k + 1] in "{}|":
            return s[k + 1], k + 2
        name, j = _read_cmd(s, k)
        if name in _SYMBOLS:
            return _SYMBOLS[name], j
        return "\\" + name, j
    if s[k] in _DELIMS:
        return _DELIMS[s[k]], k + 1
    return s[k], k + 1


def _matrix(env: str, body: str) -> str:
    body = body.strip()
    if env == "array":
        b = body.lstrip()
        if b.startswith("{"):               # 列格式参数 {cc}
            _, k = _read_group(b, 0)
            body = b[k:].strip()
    rows = re.split(r"\\\\", body)
    lines = []
    for row in rows:
        cells = [_convert(c.strip()) for c in row.split("&")]
        lines.append("  ".join(cells).strip())
    text = "\n".join([ln for ln in lines if ln != ""])
    wrap = _MATRIX_WRAP.get(env)
    if wrap:
        op, cl = wrap
        if op:
            text = f"{op} {text}"
        if cl:
            text = f"{text} {cl}"
    return text


def _env(s: str, i: int, j: int) -> tuple[str, int]:
    """``\\begin{...}``：已知环境转成行块，未知环境原样保留。"""
    k = _skip_space(s, j)
    if k >= len(s) or s[k] != "{":
        return "\\begin", j
    env, k2 = _read_group(s, k)
    end_marker = "\\end{" + env + "}"
    e = s.find(end_marker, k2)
    if e == -1:
        return s[i:], len(s)                     # 不闭合：原样
    body = s[k2:e]
    after = e + len(end_marker)
    if env in _MATRIX_ENVS:
        return _matrix(env, body), after
    return s[i:after], after                     # 未知环境：整体原样


def _convert(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            name, j = _read_cmd(s, i)
            if not name:
                piece, i = _tex_escape(s, i)
                out.append(piece)
                continue
            if name == "begin":
                piece, i = _env(s, i, j)
                out.append(piece)
                continue
            if name == "end":
                k = _skip_space(s, j)
                if k < n and s[k] == "{":
                    _, k2 = _read_group(s, k)
                    out.append(s[i:k2])
                    i = k2
                else:
                    out.append("\\end")
                    i = j
                continue
            if name in _WRAP_CMDS:
                k = _skip_space(s, j)
                if k < n and s[k] == "{":
                    inner, k2 = _read_group(s, k)
                    inner_u = _convert(inner)
                    if name in ("mathbb", "mathbf") and inner_u in _BLACKBOARD:
                        inner_u = _BLACKBOARD[inner_u]
                    out.append(inner_u)
                    i = k2
                else:
                    out.append("\\" + name)
                    i = j
                continue
            if name in _FRAC_CMDS:
                piece, k2 = _frac(s, j)
                if piece is None:
                    out.append("\\" + name)
                    i = j
                else:
                    out.append(piece)
                    i = k2
                continue
            if name in _SQRT_CMDS:
                piece, k2 = _sqrt(s, j)
                if piece is None:
                    out.append("\\" + name)
                    i = j
                else:
                    out.append(piece)
                    i = k2
                continue
            if name in _ACCENT_CMDS:
                k = _skip_space(s, j)
                if k < n and s[k] == "{":
                    inner, k2 = _read_group(s, k)
                    out.append(_convert(inner) + _ACCENT_CMDS[name])
                    i = k2
                else:
                    out.append("\\" + name)
                    i = j
                continue
            if name in _DELIM_CMDS:
                k = _skip_space(s, j)
                piece, k2 = _delim(s, k)
                if k2 > k:
                    out.append(piece)
                    i = k2
                else:
                    i = j
                continue
            if name == "pmod":
                k = _skip_space(s, j)
                if k < n and s[k] == "{":
                    inner, k2 = _read_group(s, k)
                    out.append("(mod " + _convert(inner) + ")")
                    i = k2
                else:
                    out.append("(mod")
                    i = j
                continue
            if name in _SPACES:
                out.append(_SPACES[name])
                i = j
                continue
            if name in _SYMBOLS:
                out.append(_SYMBOLS[name])
                i = j
                continue
            out.append("\\" + name)              # 未知命令：原样保留
            i = j
            continue
        if c in "^_":
            arg, j = _read_script_arg(s, i + 1)
            arg_u = _convert(arg)
            table = _SUP_MAP if c == "^" else _SUB_MAP
            mapped = _map_script(arg_u, table)
            if mapped is None:
                out.append(c + "(" + arg_u + ")")
            else:
                out.append(mapped)
            i = j
            continue
        if c == "{":
            inner, j = _read_group(s, i)
            out.append(_convert(inner))
            i = j
            continue
        if c == "~":
            out.append(" ")                      # TeX 不换行空格
            i += 1
            continue
        if c == "}":
            out.append(c)                        # 不配对的 }：保留
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def tex_to_unicode(tex: str) -> str:
    """尽力把一段 TeX 转成 Unicode 文本；任何异常都原样返回。"""
    if not isinstance(tex, str) or not tex:
        return tex if isinstance(tex, str) else ""
    try:
        return _convert(tex)
    except Exception:
        return tex


# ═══════════════════════════════════════════════════════════════════════ #
# 词法（与 gateway/webui/cedric-md.js 对齐）
# ═══════════════════════════════════════════════════════════════════════ #

_RE_DOLLAR2 = re.compile(r"\$\$([^\n$]+)\$\$")
_RE_DOLLAR = re.compile(r"\$((?:\\\$|[^$\n])+)\$")
_RE_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\n]*?)[ \t]*$")
_MATH_LANGS = {"math", "katex", "latex", "tex"}


def _match_dollar(s: str, i: int):
    """``$…$`` / ``$$…$$``（同一行）。返回 (tex, end) 或 None。"""
    m = _RE_DOLLAR2.match(s, i)
    if m is None:
        m = _RE_DOLLAR.match(s, i)
        if m is None:
            return None
        after = s[m.end():m.end() + 1]
        if after.isdigit():                  # $x$2 多半是价格写法
            return None
    tex = m.group(1)
    if not tex or tex[0].isspace() or tex[-1].isspace():
        return None
    tex = tex.strip()
    return (tex, m.end()) if tex else None


def _match_math_cmd(s: str, i: int):
    """``\\(…\\)`` / ``\\[…\\]``（同一行）。"""
    for opener, closer in (("\\(", "\\)"), ("\\[", "\\]")):
        if s.startswith(opener, i):
            j = s.find(closer, i + 2)
            if j != -1:
                tex = s[i + 2:j].strip()
                if tex:
                    return tex, j + 2
            return None
    return None


def _match_key(s: str, i: int):
    """``!!!内容!!!``。"""
    j = s.find("!!!", i + 3)
    if j == -1:
        return None
    inner = s[i + 3:j].strip()
    return (inner, j + 3) if inner else None


def _match_mark(s: str, i: int):
    """``==内容==``（首尾不留空白、结尾不能是 ``=``）。"""
    j = s.find("==", i + 2)
    if j == -1:
        return None
    inner = s[i + 2:j]
    if not inner or inner[0].isspace() or inner[-1].isspace():
        return None
    if inner[-1] == "=":
        return None
    return inner, j + 2


def _fence_close(line: str, fence: str) -> bool:
    s = line.strip()
    ch = fence[0]
    return len(s) >= len(fence) and set(s) == {ch}


def _block_math(lines: list[str], i: int) -> tuple[str | None, int]:
    """独占行的 ``$$…$$`` / ``\\[…\\]``（允许跨行）。"""
    stripped = lines[i].strip()
    for opener, closer in (("$$", "$$"), ("\\[", "\\]")):
        if not stripped.startswith(opener):
            continue
        rest = stripped[len(opener):]
        close = rest.rfind(closer)
        if close != -1:
            if rest[close + len(closer):].strip():
                return None, i                # 收尾后还有正文：按行内处理
            body = rest[:close].strip()
            return (body or None), i + 1
        parts = [rest]
        j = i + 1
        while j < len(lines):
            k = lines[j].find(closer)
            if k != -1:
                if lines[j][k + len(closer):].strip():
                    return None, i
                parts.append(lines[j][:k])
                body = "\n".join(parts).strip()
                return (body or None), j + 1
            parts.append(lines[j])
            j += 1
        return None, i
    return None, i


def _scan_inline(s: str) -> list[tuple[str, str]]:
    """单行内的段落级扫描（行内代码 / !!! / == / 公式）。"""
    segs: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            segs.append(("text", "".join(buf)))
            buf.clear()

    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        hit = None
        if c == "`":
            ticks = "`"
            while i + len(ticks) < n and s[i + len(ticks)] == "`":
                ticks += "`"
            close = s.find(ticks, i + len(ticks))
            if close != -1:
                flush()
                segs.append(("code", s[i:close + len(ticks)]))
                i = close + len(ticks)
                continue
        elif c == "$":
            hit = _match_dollar(s, i)
        elif c == "\\":
            hit = _match_math_cmd(s, i)
        elif c == "!" and s.startswith("!!!", i):
            hit = _match_key(s, i)
        elif c == "=" and s.startswith("==", i):
            hit = _match_mark(s, i)
        if hit is not None:
            payload, j = hit
            flush()
            if c == "$" or c == "\\":
                segs.append(("math", payload))
            elif c == "!":
                segs.append(("key", payload))
            else:
                segs.append(("mark", payload))
            i = j
            continue
        buf.append(c)
        i += 1
    flush()
    return segs


def _scan(text: str) -> list[tuple[str, str]]:
    """整段扫描：切成 text / code / key / mark / math / mathblock 段。"""
    lines = text.split("\n")
    blocks: list[list[tuple[str, str]]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = _RE_FENCE_OPEN.match(line)
        if m:
            fence, info = m.group(1), m.group(2).strip().lower()
            j = i + 1
            while j < n and not _fence_close(lines[j], fence):
                j += 1
            body = "\n".join(lines[i + 1:j])
            if info in _MATH_LANGS and body.strip():
                blocks.append([("mathblock", body.strip())])
                i = j + 1
            else:
                blocks.append([("code", "\n".join(lines[i:min(j + 1, n)]))])
                i = j + 1
            continue
        block, i2 = _block_math(lines, i)
        if block is not None:
            blocks.append([("mathblock", block)])
            i = i2
            continue
        blocks.append(_scan_inline(line))
        i += 1
    segs: list[tuple[str, str]] = []
    for k, b in enumerate(blocks):
        if k:
            segs.append(("text", "\n"))
        segs.extend(b)
    return segs


# ═══════════════════════════════════════════════════════════════════════ #
# 对外接口
# ═══════════════════════════════════════════════════════════════════════ #

def degrade_markdown(text: str) -> str:
    """把终端无法渲染的扩展语法降级成 Rich Markdown 能显示的形式。"""
    if not isinstance(text, str) or not text:
        return text
    if "$" not in text and "!" not in text and "=" not in text \
            and "\\" not in text:
        return text
    try:
        parts: list[str] = []
        for kind, payload in _scan(text):
            if kind in ("text", "code"):
                parts.append(payload)
            elif kind == "key":
                parts.append("<kbd>" + degrade_markdown(payload) + "</kbd>")
            elif kind == "mark":
                parts.append("**" + degrade_markdown(payload) + "**")
            elif kind == "math":
                u = tex_to_unicode(payload)
                parts.append("`" + u + "`" if "`" not in u else " " + u + " ")
            elif kind == "mathblock":
                u = tex_to_unicode(payload)
                fence = "~~~" if "`" in u else "```"
                parts.append(fence + "\n" + u + "\n" + fence)
        return "".join(parts)
    except Exception:
        return text


def iter_segments(text: str) -> list[tuple[str, str]]:
    """TUI 用：切成 (文本, 样式键) 段。

    样式键：``""`` 普通 / ``"key"``（!!!关键!!!，绿底）/ ``"bold"``
    （==高亮==）/ ``"math"``（公式，已转 Unicode）/ ``"code"``（原样）。
    """
    if not isinstance(text, str) or not text:
        return []
    try:
        out: list[tuple[str, str]] = []
        for kind, payload in _scan(text):
            if kind == "key":
                out.append((payload, "key"))
            elif kind == "mark":
                out.append((payload, "bold"))
            elif kind in ("math", "mathblock"):
                out.append((tex_to_unicode(payload), "math"))
            elif kind == "code":
                out.append((payload, "code"))
            else:
                out.append((payload, ""))
        return out
    except Exception:
        return [(text, "")]


class CedricMarkdown(Markdown):
    """先做终端降级替换，再交给 Rich 的 Markdown 渲染。

    Rich 的 ``Markdown`` 在 ``__init__`` 里就把 markup 解析成 token，
    所以替换必须在 ``super().__init__`` 之前完成。
    """

    def __init__(self, markup, *args, **kwargs):
        super().__init__(degrade_markdown(markup), *args, **kwargs)
