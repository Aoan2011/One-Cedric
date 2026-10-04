"""格式转换与统计工具。"""
from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path

from .sandbox import _resolve_path


def _get_source(data, file, root):
    if file:
        if root is None:
            return None, "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return None, err
        if not p.exists():
            return None, f"ERROR: 文件不存在: {file}"
        try:
            return p.read_text(encoding="utf-8",
                                errors="replace"), ""
        except OSError as exc:
            return None, f"ERROR: 读取失败: {exc}"
    if data:
        return data, ""
    return None, "ERROR: 需要 data 或 file"


def json_format(data: str = "", file: str = "", indent: int = 2,
                compact: bool = False, root: Path | None = None) -> str:
    raw, err = _get_source(data, file, root)
    if err:
        return err
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"ERROR: JSON 解析失败: {exc}"
    if compact:
        return json.dumps(obj, ensure_ascii=False,
                          separators=(",", ":"))
    try:
        ind = max(0, min(int(indent), 8))
    except (TypeError, ValueError):
        ind = 2
    return json.dumps(obj, ensure_ascii=False, indent=ind)


def json_diff(a: str = "", b: str = "",
              file_a: str = "", file_b: str = "",
              root: Path | None = None) -> str:
    def _load(d, f):
        if f:
            if root is None:
                return None, "ERROR: file 需要 root"
            p, err = _resolve_path(root, f)
            if err:
                return None, err
            if not p.exists():
                return None, f"ERROR: 文件不存在: {f}"
            try:
                return json.loads(p.read_text(
                    encoding="utf-8", errors="replace")), ""
            except (OSError, json.JSONDecodeError) as exc:
                return None, f"ERROR: {exc}"
        if d:
            try:
                return json.loads(d), ""
            except json.JSONDecodeError as exc:
                return None, f"ERROR: {exc}"
        return None, "ERROR: 需要 data 或 file"

    obj_a, err = _load(a, file_a)
    if err:
        return err
    obj_b, err = _load(b, file_b)
    if err:
        return err

    lines: list = []

    def _walk(prefix, va, vb):
        if type(va) != type(vb):
            lines.append(f"~ {prefix}: 类型 "
                         f"{type(va).__name__} → "
                         f"{type(vb).__name__}")
            return
        if isinstance(va, dict):
            for k in sorted(set(va) | set(vb), key=str):
                child = f"{prefix}.{k}" if prefix else k
                if k not in va:
                    lines.append(
                        f"+ {child} = "
                        f"{json.dumps(vb[k], ensure_ascii=False)[:100]}")
                elif k not in vb:
                    lines.append(
                        f"- {child} = "
                        f"{json.dumps(va[k], ensure_ascii=False)[:100]}")
                else:
                    _walk(child, va[k], vb[k])
        elif isinstance(va, list):
            if len(va) != len(vb):
                lines.append(f"~ {prefix}: 长度 {len(va)} → {len(vb)}")
            for i in range(min(len(va), len(vb))):
                _walk(f"{prefix}[{i}]", va[i], vb[i])
        else:
            if va != vb:
                sa = json.dumps(va, ensure_ascii=False)[:80]
                sb = json.dumps(vb, ensure_ascii=False)[:80]
                lines.append(f"~ {prefix}: {sa} → {sb}")

    _walk("", obj_a, obj_b)
    if not lines:
        return "两个 JSON 完全一致。"
    return (f"JSON diff（{len(lines)} 处差异）：\n"
            + "\n".join(lines))


def csv_to_json(path: str, root: Path, delimiter: str = ",",
                encoding: str = "utf-8") -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"
    try:
        with open(p, "r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(
                f, delimiter=delimiter[0] if delimiter else ",")
            rows = [dict(r) for r in reader]
    except (OSError, csv.Error) as exc:
        return f"ERROR: 读取失败: {exc}"
    return json.dumps(rows, ensure_ascii=False, indent=2)


def json_to_csv(data: str = "", file: str = "",
                root: Path | None = None,
                delimiter: str = ",") -> str:
    raw, err = _get_source(data, file, root)
    if err:
        return err
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"ERROR: JSON 解析失败: {exc}"

    if not isinstance(obj, list):
        return "ERROR: JSON 必须是数组（数组元素为对象）"
    if not obj:
        return "(空数组)"

    keys: list = []
    for row in obj:
        if isinstance(row, dict):
            for k in row:
                if k not in keys:
                    keys.append(k)

    buf = io.StringIO()
    w = csv.DictWriter(
        buf, fieldnames=keys,
        delimiter=delimiter[0] if delimiter else ",",
        extrasaction="ignore")
    w.writeheader()
    for row in obj:
        w.writerow(row if isinstance(row, dict) else {"value": row})
    return buf.getvalue()


def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)
    return s


def _md_simple(md: str) -> str:
    lines = md.splitlines()
    out: list = []
    in_code = False
    code_lines: list = []
    code_lang = ""

    for line in lines:
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                code_lines = []
            else:
                in_code = False
                code_html = html.escape("\n".join(code_lines))
                cls = (f' class="language-{code_lang}"'
                       if code_lang else "")
                out.append(f"<pre><code{cls}>{code_html}</code></pre>")
            continue

        if in_code:
            code_lines.append(line)
            continue

        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{_inline(m.group(2))}</h{lv}>")
            continue
        if line.startswith("> "):
            out.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
            continue
        if re.match(r"^[-*+]\s+", line):
            out.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if re.match(r"^\d+\.\s+", line):
            out.append(f"<li>{_inline(re.sub(r'^\d+\.\s+', '', line))}</li>")
            continue
        if re.match(r"^[-*_]{3,}\s*$", line):
            out.append("<hr>")
            continue
        if not line.strip():
            out.append("")
            continue
        out.append(f"<p>{_inline(line)}</p>")

    if in_code and code_lines:
        code_html = html.escape("\n".join(code_lines))
        out.append(f"<pre><code>{code_html}</code></pre>")

    result: list = []
    in_ul = False
    for item in out:
        if item.startswith("<li>"):
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            result.append(item)
        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append(item)
    if in_ul:
        result.append("</ul>")

    return "\n".join(result)


def md_to_html(text: str = "", file: str = "",
               root: Path | None = None,
               full: bool = False) -> str:
    raw = text
    if file:
        if root is None:
            return "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return err
        if not p.exists():
            return f"ERROR: 文件不存在: {file}"
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"ERROR: 读取失败: {exc}"
    if not raw:
        return "ERROR: 需要 text 或 file"

    body = _md_simple(raw)
    if not full:
        return body

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Document</title>
<style>
body {{ max-width: 780px; margin: 40px auto; padding: 0 20px;
        font-family: -apple-system, sans-serif; line-height: 1.6;
        color: #333; }}
pre {{ background: #f5f5f5; padding: 12px 16px;
       border-radius: 6px; overflow-x: auto; }}
code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 3px solid #ddd; padding-left: 16px;
              color: #666; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #ddd; padding: 6px 12px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def text_stats(text: str = "", file: str = "",
               root: Path | None = None) -> str:
    raw = text
    if file:
        if root is None:
            return "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return err
        if not p.exists():
            return f"ERROR: 文件不存在: {file}"
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"ERROR: 读取失败: {exc}"
    if raw is None:
        return "ERROR: 需要 text 或 file"

    lines = raw.splitlines()
    chars = len(raw)
    chars_no_ws = len(re.sub(r"\s", "", raw))
    words = len(re.findall(r"[A-Za-z0-9]+", raw))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", raw))
    sentences = len(re.findall(r"[.!?。！？]+", raw))
    paragraphs = len([p for p in re.split(r"\n\s*\n", raw) if p.strip()])

    return (f"字符数: {chars}\n"
            f"字符数（无空白）: {chars_no_ws}\n"
            f"行数: {len(lines)}\n"
            f"非空行: {len([l for l in lines if l.strip()])}\n"
            f"段落数: {paragraphs}\n"
            f"英文单词: {words}\n"
            f"中文字符: {cjk}\n"
            f"句子数: {sentences}")