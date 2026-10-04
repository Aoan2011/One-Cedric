"""写工具：edit_file / write_file + unified diff 应用。"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import MAX_WRITE_BYTES
from .sandbox import _resolve_path


def compute_edit(text: str, old_string: str, new_string: str,
                 replace_all: bool) -> tuple:
    if not old_string:
        return None, 0, "ERROR: old_string 不能为空。"
    if old_string == new_string:
        return None, 0, "ERROR: old_string 与 new_string 相同，无需修改。"
    count = text.count(old_string)
    if count == 0:
        return None, 0, ("ERROR: 未在文件中找到 old_string"
                         "（需逐字符匹配）。"
                         "建议先用 read_file 查看文件当前内容。")
    if count > 1 and not replace_all:
        return None, count, (
            f"ERROR: old_string 在文件中出现 {count} 次，不唯一。"
            f"请提供更多上下文使其唯一，"
            f"或设置 replace_all=true 替换全部。")
    if replace_all:
        return text.replace(old_string, new_string), count, ""
    return text.replace(old_string, new_string, 1), 1, ""


def edit_file(root: Path, path: str, old_string: str,
              new_string: str, replace_all=False) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root))
    if not p.exists():
        return f"ERROR: 文件不存在: {rel}"
    if not p.is_file():
        return f"ERROR: 不是普通文件: {rel}"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"
    new_text, count, err = compute_edit(
        text, old_string, new_string, bool(replace_all))
    if err:
        return err
    try:
        p.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: 写入失败: {exc}"
    return f"已更新 {rel}（替换 {count} 处）"


def write_file(root: Path, path: str, content: str) -> str:
    if not isinstance(content, str):
        return "ERROR: content 必须是字符串。"
    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        return f"ERROR: 内容超过 {MAX_WRITE_BYTES // 1000}KB 上限。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    rel = str(p.relative_to(root))
    if p.exists() and p.is_dir():
        return f"ERROR: 目标是目录: {rel}"
    existed = p.exists()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: 写入失败: {exc}"
    verb = "已覆盖" if existed else "已创建"
    return (f"{verb} {rel}（{len(content.splitlines())} 行，"
            f"{len(content.encode('utf-8'))} bytes）")


def _parse_unified_diff(text: str) -> tuple:
    files: list = []
    cur: dict | None = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old_path = line[4:].split("\t")[0].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
            if (i + 1 >= len(lines)
                    or not lines[i + 1].startswith("+++ ")):
                return [], "diff 格式错误: '---' 之后缺少 '+++'。"
            new_path = lines[i + 1][4:].split("\t")[0].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            cur = {"old_path": old_path, "new_path": new_path,
                   "hunks": []}
            files.append(cur)
            i += 2
            continue
        if line.startswith("@@ "):
            if cur is None:
                return [], "diff 格式错误: 在文件头之前出现 '@@'。"
            m = re.match(
                r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
                line)
            if not m:
                return [], f"无法解析 hunk 头: {line}"
            hunk = {
                "old_start": int(m.group(1)),
                "old_count": int(m.group(2) or 1),
                "new_start": int(m.group(3)),
                "new_count": int(m.group(4) or 1),
                "lines": [],
            }
            cur["hunks"].append(hunk)
            i += 1
            while i < len(lines):
                l = lines[i]
                if l.startswith("@@ ") or l.startswith("--- "):
                    break
                if l.startswith("\\"):
                    i += 1
                    continue
                if (l.startswith("+") or l.startswith("-")
                        or l.startswith(" ") or l == ""):
                    hunk["lines"].append(l)
                else:
                    hunk["lines"].append(" " + l)
                i += 1
            continue
        i += 1
    if not files:
        return [], "diff 中没有找到任何文件块。"
    return files, ""


def _apply_hunks_to_text(old_text: str,
                         hunks: list) -> tuple:
    old_lines = old_text.splitlines()
    result: list = []
    cursor = 0
    for h in hunks:
        target = h["old_start"] - 1
        if target < cursor:
            return None, f"hunk 重叠（old_start={h['old_start']}）"
        if target > len(old_lines):
            return None, (f"hunk 起始行 {h['old_start']} "
                          f"超出文件范围")
        result.extend(old_lines[cursor:target])
        cursor = target
        for l in h["lines"]:
            if l.startswith(" "):
                ctx = l[1:]
                if cursor >= len(old_lines) \
                        or old_lines[cursor] != ctx:
                    got = (old_lines[cursor]
                           if cursor < len(old_lines) else "<EOF>")
                    return None, (f"上下文不匹配"
                                  f"（第 {cursor + 1} 行）: "
                                  f"期望 {ctx!r}，实际 {got!r}")
                result.append(old_lines[cursor])
                cursor += 1
            elif l.startswith("-"):
                rem = l[1:]
                if cursor >= len(old_lines) \
                        or old_lines[cursor] != rem:
                    got = (old_lines[cursor]
                           if cursor < len(old_lines) else "<EOF>")
                    return None, (f"待删行不匹配"
                                  f"（第 {cursor + 1} 行）: "
                                  f"期望 {rem!r}，实际 {got!r}")
                cursor += 1
            elif l.startswith("+"):
                result.append(l[1:])
            else:
                if cursor >= len(old_lines) \
                        or old_lines[cursor] != l:
                    got = (old_lines[cursor]
                           if cursor < len(old_lines) else "<EOF>")
                    return None, (f"上下文不匹配"
                                  f"（第 {cursor + 1} 行）: "
                                  f"期望 {l!r}，实际 {got!r}")
                result.append(old_lines[cursor])
                cursor += 1
    result.extend(old_lines[cursor:])
    trailing = "\n" if old_text.endswith("\n") or not old_text else ""
    return "\n".join(result) + trailing, ""