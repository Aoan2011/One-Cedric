"""文本处理：find_replace / regex_extract / code_stats / markdown_toc / template_render。"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import MAX_SEARCH_FILE_SIZE
from .sandbox import _as_int, _resolve_path


def find_replace(root: Path, pattern: str, replacement: str,
                 glob: str = "**/*", path: str = ".",
                 use_regex: bool = False, case_insensitive: bool = False,
                 max_files=None) -> tuple:
    if not pattern:
        return [], "ERROR: pattern 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return [], err
    if not p.exists() or not p.is_dir():
        return [], f"ERROR: 目录不存在: {path}"
    limit = _as_int(max_files, 20)
    if limit <= 0:
        limit = 20
    flags = re.MULTILINE
    if case_insensitive:
        flags |= re.IGNORECASE
    rx = None
    if use_regex:
        try:
            rx = re.compile(pattern, flags)
        except re.error as exc:
            return [], f"ERROR: 正则编译失败: {exc}"
    changes: list = []
    try:
        for f in sorted(p.rglob(glob)):
            if not f.is_file():
                continue
            try:
                if f.stat().st_size > MAX_SEARCH_FILE_SIZE:
                    continue
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if use_regex:
                new_text, count = rx.subn(replacement, text)
            else:
                if case_insensitive:
                    pat = re.compile(re.escape(pattern), re.IGNORECASE)
                    new_text, count = pat.subn(
                        lambda _: replacement, text)
                else:
                    count = text.count(pattern)
                    new_text = text.replace(pattern, replacement)
            if count == 0 or new_text == text:
                continue
            changes.append({
                "path": f, "rel": str(f.relative_to(root)),
                "old_text": text, "new_text": new_text, "count": count,
            })
            if len(changes) >= limit:
                break
    except OSError as exc:
        return [], f"ERROR: 遍历失败: {exc}"
    return changes, ""


def regex_extract(root: Path, pattern: str, path: str,
                  file_pattern: str = "*",
                  unique: bool = True, max_results=None) -> str:
    if not pattern:
        return "ERROR: pattern 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"ERROR: 正则编译失败: {exc}"
    limit = _as_int(max_results, 100)
    if limit <= 0:
        limit = 100
    files: list = []
    if p.is_file():
        files = [p]
    else:
        files = sorted(p.rglob(file_pattern))
    results: list = []
    seen: set = set()
    n_groups = rx.groups
    for f in files:
        if not f.is_file():
            continue
        try:
            if f.stat().st_size > MAX_SEARCH_FILE_SIZE:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in rx.finditer(text):
            if n_groups >= 1:
                if n_groups == 1:
                    val = m.group(1)
                else:
                    val = "\t".join(str(g) for g in m.groups())
            else:
                val = m.group(0)
            if val is None:
                continue
            val = val.strip()
            if not val:
                continue
            if unique and val in seen:
                continue
            seen.add(val)
            results.append(val)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    if not results:
        return f"未在 {path} 中匹配到 {pattern!r}。"
    header = f"提取 {len(results)} 条"
    if n_groups >= 1:
        header += f"（{n_groups} 个捕获组）"
    header += "："
    return header + "\n" + "\n".join(results)


EXT_LANG = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "LESS",
    ".sql": "SQL", ".md": "Markdown", ".yml": "YAML",
    ".yaml": "YAML", ".json": "JSON", ".toml": "TOML", ".xml": "XML",
}

COMMENT_PREFIX = {
    "Python": "#", "Ruby": "#", "Shell": "#",
    "PowerShell": "#", "YAML": "#",
    "JavaScript": "//", "TypeScript": "//", "Go": "//",
    "Rust": "//", "Java": "//", "C": "//", "C++": "//",
    "C#": "//", "Swift": "//", "Kotlin": "//",
    "Scala": "//", "PHP": "//",
    "SQL": "--",
}


def code_stats(root: Path, path: str = ".",
               exclude: str = ("node_modules,__pycache__,.git,"
                               "venv,.venv,dist,build")) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_dir():
        return f"ERROR: 目录不存在: {path}"
    excluded = {s.strip() for s in exclude.split(",") if s.strip()}

    def _is_excluded(fp: Path) -> bool:
        return bool(set(fp.parts) & excluded)

    stats: dict = {}
    try:
        for f in p.rglob("*"):
            if not f.is_file() or _is_excluded(f):
                continue
            lang = EXT_LANG.get(f.suffix.lower())
            if not lang:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            total = len(lines)
            blank = sum(1 for l in lines if not l.strip())
            cp = COMMENT_PREFIX.get(lang, "")
            comment = 0
            if cp:
                comment = sum(1 for l in lines
                              if l.strip().startswith(cp))
            funcs = 0
            classes = 0
            if lang == "Python":
                funcs = len(re.findall(
                    r"^\s*(?:async\s+)?def\s+\w+", text,
                    re.MULTILINE))
                classes = len(re.findall(
                    r"^\s*class\s+\w+", text, re.MULTILINE))
            elif lang in ("JavaScript", "TypeScript"):
                funcs = len(re.findall(
                    r"\bfunction\s+\w+|\bconst\s+\w+\s*=\s*"
                    r"(?:async\s*)?\(", text))
                classes = len(re.findall(r"\bclass\s+\w+", text))
            elif lang == "Go":
                funcs = len(re.findall(r"^func\s+", text, re.MULTILINE))
            elif lang == "Rust":
                funcs = len(re.findall(r"^\s*fn\s+\w+", text,
                                        re.MULTILINE))
            s = stats.setdefault(lang, {
                "files": 0, "total": 0, "blank": 0,
                "comment": 0, "funcs": 0, "classes": 0,
            })
            s["files"] += 1
            s["total"] += total
            s["blank"] += blank
            s["comment"] += comment
            s["funcs"] += funcs
            s["classes"] += classes
    except OSError as exc:
        return f"ERROR: 遍历失败: {exc}"
    if not stats:
        return f"在 {path} 下未找到可识别的代码文件。"
    total_all = sum(s["total"] for s in stats.values())
    files_all = sum(s["files"] for s in stats.values())
    lines = [f"代码统计: {path}",
             f"总计 {files_all} 文件 · {total_all} 行", ""]
    lines.append(f"{'语言':<14} {'文件':>5} {'总行':>8} "
                 f"{'有效':>8} {'注释':>7} {'函数':>6} {'类':>5}")
    lines.append("-" * 60)
    for lang, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
        effective = s["total"] - s["blank"] - s["comment"]
        lines.append(
            f"{lang:<14} {s['files']:>5} {s['total']:>8} "
            f"{effective:>8} {s['comment']:>7} "
            f"{s['funcs']:>6} {s['classes']:>5}")
    return "\n".join(lines)


def markdown_toc(root: Path, path: str, max_level=None) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"
    max_lv = _as_int(max_level, 6)
    if max_lv < 1:
        max_lv = 6
    toc: list = []
    in_code = False
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.rstrip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", s)
        if not m:
            continue
        level = len(m.group(1))
        if level > max_lv:
            continue
        title = m.group(2).strip()
        toc.append((level, title, lineno))
    if not toc:
        return f"{path} 中没有找到标题。"
    lines = [f"# {path} 的目录", ""]
    for level, title, lineno in toc:
        indent = "  " * (level - 1)
        lines.append(f"{indent}{'#' * level} {title}  (L{lineno})")
    return "\n".join(lines)


def template_render(template: str, variables: dict) -> str:
    if not isinstance(template, str):
        return "ERROR: template 必须是字符串。"
    if not isinstance(variables, dict):
        return "ERROR: variables 必须是对象。"

    def _replace(m):
        key = m.group(1).strip()
        if key in variables:
            v = variables[key]
            return str(v) if v is not None else ""
        return m.group(0)

    rendered = re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _replace, template)
    missing = re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", rendered)
    out = f"渲染结果（{len(rendered)} 字符）：\n\n{rendered}"
    if missing:
        out += (f"\n\n[警告] 未提供的变量: "
                f"{', '.join(sorted(set(missing)))}")
    return out