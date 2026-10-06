"""LSP 工具实现。所有工具都返回字符串。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.sandbox import _as_int, _resolve_path
from .manager import get_manager


def _client_for(root: Path, rel_path: str):
    p, err = _resolve_path(root, rel_path)
    if err:
        raise ValueError(err)
    if not p.exists() or not p.is_file():
        raise ValueError(f"文件不存在: {rel_path}")
    mgr = get_manager(root)
    if not mgr.enabled:
        raise ValueError("LSP 已禁用（~/.one-cedric/lsp.toml 中 settings.enabled = false）")
    name, cli = mgr.pick_client(p)
    return p, name, cli


def _fmt_hover(result: Any) -> str:
    if not result:
        return "（无悬停信息）"
    contents = result.get("contents") if isinstance(result, dict) else result
    if contents is None:
        return "（无悬停信息）"
    if isinstance(contents, str):
        return contents.strip()
    if isinstance(contents, dict):
        val = contents.get("value") or contents.get("language") or ""
        return str(val).strip()
    if isinstance(contents, list):
        parts = []
        for c in contents:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                parts.append(c.get("value") or "")
        return "\n".join(p for p in parts if p).strip()
    return str(contents)


def _fmt_location(loc: Any, root: Path) -> str:
    if not loc:
        return ""
    if isinstance(loc, list):
        return "\n".join(_fmt_location(x, root) for x in loc)
    if not isinstance(loc, dict):
        return str(loc)

    target_uri = loc.get("targetUri") or loc.get("uri")
    if target_uri is None:
        return str(loc)

    from .client import path_from_uri
    p = path_from_uri(target_uri)
    rel = ""
    if p is not None:
        try:
            rel = str(p.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(p)
    else:
        rel = target_uri

    rng = loc.get("targetSelectionRange") or loc.get("range") or {}
    start = rng.get("start") or {}
    line = int(start.get("line", 0)) + 1
    col = int(start.get("character", 0)) + 1
    return f"{rel}:{line}:{col}"


def lsp_hover(root: Path, path: str, line: int, column: int) -> str:
    try:
        p, name, cli = _client_for(root, path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    try:
        result = cli.hover(p, _as_int(line, 1), _as_int(column, 1))
    except Exception as exc:
        return f"ERROR: LSP hover 失败（{name}）: {exc}"
    text = _fmt_hover(result)
    if not text:
        return f"（{path}:{line}:{column} 无悬停信息）"
    return f"{path}:{line}:{column}  →  [{name}]\n\n{text}"


def lsp_definition(root: Path, path: str, line: int, column: int) -> str:
    try:
        p, name, cli = _client_for(root, path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    try:
        result = cli.definition(p, _as_int(line, 1), _as_int(column, 1))
    except Exception as exc:
        return f"ERROR: LSP definition 失败（{name}）: {exc}"
    if not result:
        return f"（{path}:{line}:{column} 未找到定义）"
    locations = result if isinstance(result, list) else [result]
    lines = [f"定义位置（{name}）:"]
    for loc in locations:
        s = _fmt_location(loc, root)
        if s:
            lines.append(f"  {s}")
    return "\n".join(lines)


def lsp_references(root: Path, path: str, line: int, column: int,
                   include_declaration: bool = True) -> str:
    try:
        p, name, cli = _client_for(root, path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    try:
        result = cli.references(p, _as_int(line, 1), _as_int(column, 1),
                                include_decl=bool(include_declaration))
    except Exception as exc:
        return f"ERROR: LSP references 失败（{name}）: {exc}"
    if not result:
        return f"（{path}:{line}:{column} 无引用）"
    locations = result if isinstance(result, list) else [result]
    lines = [f"引用 {len(locations)} 处（{name}）:"]
    for loc in locations[:200]:
        s = _fmt_location(loc, root)
        if s:
            lines.append(f"  {s}")
    if len(locations) > 200:
        lines.append(f"  …还有 {len(locations) - 200} 处")
    return "\n".join(lines)


def lsp_diagnostics(root: Path, path: str) -> str:
    try:
        p, name, cli = _client_for(root, path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    mgr = get_manager(root)
    try:
        diags = cli.diagnostics(p, wait=mgr.diagnostics_wait())
    except Exception as exc:
        return f"ERROR: LSP diagnostics 失败（{name}）: {exc}"

    if not diags:
        return f"（{path} 无诊断）"

    severity_label = {1: "错误", 2: "警告", 3: "信息", 4: "提示"}
    lines = [f"诊断 {len(diags)} 条（{name}）:"]
    for d in diags:
        rng = d.get("range") or {}
        start = rng.get("start") or {}
        line = int(start.get("line", 0)) + 1
        col = int(start.get("character", 0)) + 1
        sev = severity_label.get(d.get("severity", 4), "?")
        msg = (d.get("message") or "").strip().replace("\n", " ")
        code = d.get("code")
        tail = f"  [{code}]" if code else ""
        lines.append(f"  {path}:{line}:{col}  [{sev}]{tail} {msg[:200]}")
    return "\n".join(lines)


def lsp_symbols(root: Path, path: str) -> str:
    try:
        p, name, cli = _client_for(root, path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    try:
        result = cli.document_symbols(p)
    except Exception as exc:
        return f"ERROR: LSP documentSymbol 失败（{name}）: {exc}"
    if not result:
        return f"（{path} 无符号）"

    lines = [f"{path} 的符号（{name}）:"]

    def _emit(sym: dict, depth: int) -> None:
        name_ = sym.get("name", "?")
        kind = sym.get("kind", 0)
        rng = sym.get("range") or sym.get("location", {}).get("range") or {}
        start = rng.get("start") or {}
        line = int(start.get("line", 0)) + 1
        prefix = "  " * (depth + 1)
        kind_name = _SYM_KIND.get(kind, "?")
        lines.append(f"{prefix}{kind_name} {name_}  (L{line})")
        for child in sym.get("children") or []:
            _emit(child, depth + 1)

    for sym in result:
        if isinstance(sym, dict):
            if "location" in sym and "range" not in sym:
                loc = sym["location"]
                rng = loc.get("range") or {}
                start = rng.get("start") or {}
                line = int(start.get("line", 0)) + 1
                kind_name = _SYM_KIND.get(sym.get("kind", 0), "?")
                lines.append(f"  {kind_name} {sym.get('name','?')}  (L{line})")
            else:
                _emit(sym, 0)
    return "\n".join(lines)


_SYM_KIND = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package",
    5: "Class", 6: "Method", 7: "Property", 8: "Field",
    9: "Constructor", 10: "Enum", 11: "Interface",
    12: "Function", 13: "Variable", 14: "Constant",
    15: "String", 16: "Number", 17: "Boolean", 18: "Array",
    19: "Object", 20: "Key", 21: "Null", 22: "EnumMember",
    23: "Struct", 24: "Event", 25: "Operator", 26: "TypeParameter",
}


def lsp_status(root: Path) -> str:
    mgr = get_manager(root)
    rows = mgr.status()
    if not rows:
        return "未配置任何 LSP 服务器。"
    lines = ["LSP 服务器状态：", ""]
    for r in rows:
        tag = "运行中" if r["running"] else ("已启用" if r["enabled"] else "已禁用")
        cmd = " ".join([r["command"]] + r["args"])
        exts = ", ".join(r["extensions"]) or "(无)"
        lines.append(f"[{r['name']}] {tag}")
        lines.append(f"  命令: {cmd}")
        lines.append(f"  扩展名: {exts}")
        if r["last_error"]:
            lines.append(f"  最近错误: {r['last_error']}")
        lines.append("")
    return "\n".join(lines)