"""@ 文件引用展开：把 @path 替换成文件内容。

支持形式：
    @README.md                整个文件
    @src/main.py#L10-L20      指定行范围
    @src/main.py#L10-20       同上
    @src/                     目录列表
    @src/**                   递归目录列表
    @F:\\绝对路径.png         绝对路径（若在沙箱内）
"""
from __future__ import annotations

import re
from pathlib import Path


AT_PATTERN = re.compile(r"@([^\s@]+)")


def build_attachment(root: Path, path_str: str) -> tuple:
    """把单个路径解析为上传/引用附件块。

    返回 (block, warning)：block 为可插入上下文的 Markdown 附件块
    （文件内容或目录列表）；warning 为失败原因（此时 block 为 None）。
    """
    from .tools.sandbox import _resolve_path

    raw = path_str.strip().rstrip(",.，。；;:：!！?？)）]】")
    if not raw:
        return None, "空路径"

    line_range = None
    if "#" in raw:
        path_part, _, range_part = raw.partition("#")
        m2 = re.match(r"L?(\d+)(?:-L?(\d+))?", range_part, re.IGNORECASE)
        if m2:
            start = int(m2.group(1))
            end = int(m2.group(2)) if m2.group(2) else start
            line_range = (start, end)
            raw = path_part

    is_dir_recursive = raw.endswith("/**")
    is_dir = raw.endswith("/") or is_dir_recursive
    if is_dir_recursive:
        raw = raw[:-3]

    p, err = _resolve_path(root, raw)
    if err:
        return None, f"{raw}: {err}"
    if not p.exists():
        return None, f"{raw}: 路径不存在"

    try:
        if p.is_file():
            content = _read_file_for_ref(p, line_range)
            label = str(p.relative_to(root)) if p.is_relative_to(root) \
                else str(p)
            if line_range:
                label += f"#L{line_range[0]}-{line_range[1]}"
            return f"### {label}\n```\n{content}\n```", None
        if p.is_dir():
            content = _list_dir_for_ref(root, p,
                                        recursive=is_dir_recursive)
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                rel = str(p)
            return f"### {rel}/\n```\n{content}\n```", None
    except OSError as exc:
        return None, f"{raw}: 读取失败 {exc}"
    return None, f"{raw}: 不支持的路径类型"


def expand_at_refs(root: Path, text: str) -> tuple:
    """展开 @ 引用。

    返回 (expanded_text, warnings, resolved_paths)
    """
    from .tools.sandbox import _resolve_path

    matches = list(AT_PATTERN.finditer(text))
    if not matches:
        return text, [], []

    attachments = []
    warnings = []
    resolved = []

    for m in matches:
        raw = m.group(1)
        # 去掉尾部标点
        raw = raw.rstrip(",.，。；;:：!！?？)）]】")
        if not raw:
            continue

        # 处理 #L10-L20 或 #L10-20
        line_range = None
        if "#" in raw:
            path_part, _, range_part = raw.partition("#")
            m2 = re.match(r"L?(\d+)(?:-L?(\d+))?", range_part, re.IGNORECASE)
            if m2:
                start = int(m2.group(1))
                end = int(m2.group(2)) if m2.group(2) else start
                line_range = (start, end)
                raw = path_part

        # 处理目录通配
        is_dir_recursive = raw.endswith("/**")
        is_dir = raw.endswith("/") or is_dir_recursive
        if is_dir_recursive:
            raw = raw[:-3]

        p, err = _resolve_path(root, raw)
        if err:
            warnings.append(f"{raw}: {err}")
            continue
        if not p.exists():
            warnings.append(f"{raw}: 路径不存在")
            continue

        try:
            if p.is_file():
                content = _read_file_for_ref(p, line_range)
                label = str(p.relative_to(root)) if p.is_relative_to(root) \
                    else str(p)
                if line_range:
                    label += f"#L{line_range[0]}-{line_range[1]}"
                attachments.append(f"### {label}\n```\n{content}\n```")
                resolved.append(str(p.relative_to(root))
                                if p.is_relative_to(root) else str(p))
            elif p.is_dir():
                content = _list_dir_for_ref(root, p, recursive=is_dir_recursive)
                try:
                    rel = str(p.relative_to(root))
                except ValueError:
                    rel = str(p)
                attachments.append(f"### {rel}/\n```\n{content}\n```")
                resolved.append(rel)
        except OSError as exc:
            warnings.append(f"{raw}: 读取失败 {exc}")
            continue

    if not attachments:
        return text, warnings, resolved

    block = "\n\n[用户引用的文件内容]\n\n" + "\n\n".join(attachments)
    return text + block, warnings, resolved


def _read_file_for_ref(p: Path, line_range) -> str:
    """读取文件内容（用于引用）。"""
    from .tools.encoding_detect import read_text_auto

    result = read_text_auto(p)
    if not result["ok"]:
        return f"（读取失败: {result['error']}）"

    text = result["text"]
    lines = text.splitlines()

    if line_range:
        start, end = line_range
        start = max(1, start)
        end = min(len(lines), end)
        if start > end:
            return f"（行范围无效: L{start}-L{end}）"
        selected = lines[start - 1:end]
        numbered = "\n".join(f"{i:>4}| {l}"
                              for i, l in enumerate(selected, start))
        return numbered

    # 全文件：截断到 100KB 或 2000 行
    if len(text) > 100_000:
        text = text[:100_000] + "\n... (截断)"
    if len(lines) > 2000:
        text = "\n".join(lines[:2000]) + "\n... (截断)"
    return text


def _list_dir_for_ref(root: Path, p: Path, recursive: bool) -> str:
    """目录列表（用于引用）。"""
    lines = []
    try:
        if recursive:
            for item in sorted(p.rglob("*")):
                try:
                    rel = item.relative_to(root)
                except ValueError:
                    continue
                if item.is_dir():
                    lines.append(f"[DIR]  {rel}/")
                else:
                    lines.append(f"[FILE] {rel}")
                if len(lines) > 500:
                    lines.append("... (截断)")
                    break
        else:
            for item in sorted(p.iterdir()):
                if item.is_dir():
                    lines.append(f"[DIR]  {item.name}/")
                else:
                    lines.append(f"[FILE] {item.name}")
                if len(lines) > 200:
                    lines.append("... (截断)")
                    break
    except OSError as exc:
        return f"（列出失败: {exc}）"
    return "\n".join(lines) if lines else "(空)"