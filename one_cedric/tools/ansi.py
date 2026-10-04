"""ANSI 转义序列扫描与处理。"""
from __future__ import annotations

import re
from pathlib import Path

from .sandbox import _resolve_path

CSI = re.compile(r"\x1b\[([0-9;?]*)([a-zA-Z])")
OSC = re.compile(r"\x1b\]([^\x07\x1b]*)(?:\x07|\x1b\\)")
ESC_SINGLE = re.compile(r"\x1b([@-Z\\-_])")
ALL_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[a-zA-Z]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)

SGR_NAMES = {
    "0": "reset", "1": "bold", "2": "dim", "3": "italic",
    "4": "underline", "5": "blink", "7": "reverse",
    "8": "hidden", "9": "strikethrough",
    "30": "fg-black", "31": "fg-red", "32": "fg-green",
    "33": "fg-yellow", "34": "fg-blue", "35": "fg-magenta",
    "36": "fg-cyan", "37": "fg-white",
    "90": "fg-bright-black", "91": "fg-bright-red",
    "92": "fg-bright-green", "93": "fg-bright-yellow",
    "94": "fg-bright-blue", "95": "fg-bright-magenta",
    "96": "fg-bright-cyan", "97": "fg-bright-white",
    "40": "bg-black", "41": "bg-red", "42": "bg-green",
    "43": "bg-yellow", "44": "bg-blue", "45": "bg-magenta",
    "46": "bg-cyan", "47": "bg-white",
    "100": "bg-bright-black", "101": "bg-bright-red",
    "102": "bg-bright-green", "103": "bg-bright-yellow",
    "104": "bg-bright-blue", "105": "bg-bright-magenta",
    "106": "bg-bright-cyan", "107": "bg-bright-white",
}


def _read_input(text: str, file: str, root: Path | None):
    if file:
        if root is None:
            return None, "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return None, err
        if not p.exists():
            return None, f"ERROR: 文件不存在: {file}"
        try:
            return p.read_bytes().decode("utf-8", errors="replace"), ""
        except OSError as exc:
            return None, f"ERROR: {exc}"
    if text is not None and text != "":
        return text, ""
    return None, "ERROR: 需要 text 或 file"


def ansi_strip(text: str = "", file: str = "",
               root: Path | None = None,
               keep_osc: bool = False) -> str:
    raw, err = _read_input(text, file, root)
    if err:
        return err
    if keep_osc:
        cleaned = CSI.sub("", ESC_SINGLE.sub("", raw))
    else:
        cleaned = ALL_ANSI.sub("", raw)
    before = len(raw)
    after = len(cleaned)
    return (f"清理 {before - after} 字节的 ANSI 序列"
            f"（{before} → {after}）\n--- 结果 ---\n{cleaned}")


def ansi_scan(text: str = "", file: str = "",
              root: Path | None = None,
              show_examples: bool = True) -> str:
    raw, err = _read_input(text, file, root)
    if err:
        return err
    csi_matches = list(CSI.finditer(raw))
    osc_matches = list(OSC.finditer(raw))
    esc_matches = list(ESC_SINGLE.finditer(raw))
    total = len(csi_matches) + len(osc_matches) + len(esc_matches)
    lines = [
        f"总字节: {len(raw)}",
        f"ANSI 序列: {total}",
        f"  CSI:  {len(csi_matches)}",
        f"  OSC:  {len(osc_matches)}",
        f"  单字符 ESC: {len(esc_matches)}",
        "",
    ]
    if not total:
        lines.append("✓ 无 ANSI 序列（纯文本）")
        return "\n".join(lines)
    sgr_codes: dict = {}
    finals: dict = {}
    for m in csi_matches:
        params, final = m.group(1), m.group(2)
        finals[final] = finals.get(final, 0) + 1
        if final == "m":
            for p in (params or "0").split(";"):
                if p == "":
                    p = "0"
                sgr_codes[p] = sgr_codes.get(p, 0) + 1
    if finals:
        lines.append("CSI 终止字符统计：")
        for f, n in sorted(finals.items(), key=lambda x: -x[1]):
            desc = {"m": "SGR 颜色/样式", "H": "光标定位",
                    "J": "清屏", "K": "清行", "A": "光标上",
                    "B": "光标下", "C": "光标右", "D": "光标左",
                    "h": "模式开启", "l": "模式关闭"}.get(f, "")
            lines.append(f"  ESC[{f}  × {n}   {desc}")
        lines.append("")
    if sgr_codes:
        lines.append("SGR 参数统计：")
        for code, n in sorted(sgr_codes.items(),
                              key=lambda x: -x[1])[:30]:
            name = SGR_NAMES.get(code, "")
            label = f"{code} ({name})" if name else code
            lines.append(f"  {label:<24} × {n}")
    if show_examples:
        lines.append("")
        lines.append("前 10 个序列（转义显示）：")
        examples = (csi_matches + osc_matches + esc_matches)[:10]
        for m in examples:
            snippet = (m.group(0).replace("\x1b", "\\x1b")
                       .replace("\x07", "\\x07"))
            lines.append(f"  位置 {m.start():>6}: {snippet!r}")
    return "\n".join(lines)


_PALETTE_16 = [
    "#000000", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
]


def _code_to_color(idx: int, bright: bool) -> str:
    i = idx + (8 if bright else 0)
    i = max(0, min(i, 15))
    return _PALETTE_16[i]


def _xterm_color(n: int) -> str:
    n = max(0, min(n, 255))
    if n < 16:
        return _PALETTE_16[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n // 6) % 6, n % 6

        def v(x):
            return 0 if x == 0 else 55 + 40 * x
        return f"#{v(r):02x}{v(g):02x}{v(b):02x}"
    gray = 8 + (n - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


def ansi_to_html(text: str = "", file: str = "",
                 root: Path | None = None,
                 dark_bg: bool = True) -> str:
    raw, err = _read_input(text, file, root)
    if err:
        return err
    out: list = []
    i = 0
    n = len(raw)
    fg = bg = None
    bold = italic = underline = strike = False

    def emit(s: str):
        if not s:
            return
        s = (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;"))
        styles = []
        if fg:
            styles.append(f"color: {fg}")
        if bg:
            styles.append(f"background-color: {bg}")
        if bold:
            styles.append("font-weight: bold")
        if italic:
            styles.append("font-style: italic")
        if underline:
            styles.append("text-decoration: underline")
        if strike:
            styles.append("text-decoration: line-through")
        if styles:
            out.append(f'<span style="{"; ".join(styles)}">{s}</span>')
        else:
            out.append(s)

    text_buf: list = []
    while i < n:
        if raw[i] == "\x1b":
            if text_buf:
                emit("".join(text_buf))
                text_buf = []
            m = CSI.match(raw, i)
            if m:
                params = m.group(1)
                final = m.group(2)
                if final == "m":
                    for p in (params or "0").split(";"):
                        if p == "":
                            p = "0"
                        try:
                            pv = int(p)
                        except ValueError:
                            continue
                        if p == "0":
                            fg = bg = None
                            bold = italic = underline = strike = False
                        elif p == "1": bold = True
                        elif p == "3": italic = True
                        elif p == "4": underline = True
                        elif p == "9": strike = True
                        elif p == "22": bold = False
                        elif p == "23": italic = False
                        elif p == "24": underline = False
                        elif p == "29": strike = False
                        elif p == "39": fg = None
                        elif p == "49": bg = None
                        elif 30 <= pv <= 37:
                            fg = _code_to_color(pv - 30, False)
                        elif 90 <= pv <= 97:
                            fg = _code_to_color(pv - 90, True)
                        elif 40 <= pv <= 47:
                            bg = _code_to_color(pv - 40, False)
                        elif 100 <= pv <= 107:
                            bg = _code_to_color(pv - 100, True)
                i = m.end()
                continue
            m = OSC.match(raw, i)
            if m:
                i = m.end()
                continue
            m = ESC_SINGLE.match(raw, i)
            if m:
                i = m.end()
                continue
            text_buf.append(raw[i])
            i += 1
        else:
            text_buf.append(raw[i])
            i += 1
    if text_buf:
        emit("".join(text_buf))
    body = "".join(out)
    bg_color = "#1a1a1a" if dark_bg else "#ffffff"
    fg_color = "#e8e6e3" if dark_bg else "#1a1a1a"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>ANSI</title>
<style>
body {{ background: {bg_color}; color: {fg_color};
        font-family: 'SF Mono', Menlo, monospace;
        padding: 20px; line-height: 1.5; white-space: pre-wrap; }}
</style></head><body>{body}</body></html>"""


def ansi_palette() -> str:
    lines = ["标准 16 色：", ""]
    for i, color in enumerate(_PALETTE_16):
        code = 30 + i if i < 8 else 90 + (i - 8)
        lines.append(f"  \x1b[{code}m████\x1b[0m  {code:>3}  {color}")
    lines.append("")
    lines.append("256 色缩略（前 32）：")
    row = []
    for i in range(32):
        row.append(f"\x1b[38;5;{i}m██\x1b[0m")
    lines.append("  " + "".join(row))
    return "\n".join(lines)