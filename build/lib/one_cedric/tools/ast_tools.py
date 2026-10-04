"""Python AST 分析工具。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from .sandbox import _resolve_path


def _parse_py(path: Path):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, None, f"ERROR: 读取失败: {exc}"
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return None, None, (f"ERROR: 语法错误 "
                            f"{exc.lineno}:{exc.offset} {exc.msg}")
    return src, tree, ""


def py_outline(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"
    if p.suffix.lower() not in (".py", ".pyi"):
        return f"ERROR: 不是 Python 文件: {path}"
    src, tree, err = _parse_py(p)
    if err:
        return err
    lines = [f"文件: {path}", ""]
    doc = ast.get_docstring(tree)
    if doc:
        lines.append("模块文档:")
        lines.append(f"  {doc.splitlines()[0][:80]}")
        lines.append("")
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append(f"{mod}.{', '.join(a.name for a in node.names)}")
    if imports:
        lines.append(f"imports ({len(imports)}):")
        for i in imports[:20]:
            lines.append(f"  {i}")
        if len(imports) > 20:
            lines.append(f"  ... 还有 {len(imports) - 20} 个")
        lines.append("")
    defs = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            defs.append(("class", node.name, node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            defs.append(("async def" if is_async else "def",
                         node.name, node.lineno))
    if defs:
        lines.append(f"顶层定义 ({len(defs)}):")
        for kind, name, lineno in defs:
            lines.append(f"  L{lineno:>4}  {kind:<9} {name}")
    method_lines = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef,
                                       ast.AsyncFunctionDef)):
                    is_async = isinstance(child, ast.AsyncFunctionDef)
                    method_lines.append((node.name,
                                          "async def" if is_async
                                          else "def",
                                          child.name, child.lineno))
    if method_lines:
        lines.append("")
        lines.append(f"方法 ({len(method_lines)}):")
        for cls, kind, name, lineno in method_lines[:40]:
            lines.append(f"  L{lineno:>4}  {cls}.{name}")
        if len(method_lines) > 40:
            lines.append(f"  ... 还有 {len(method_lines) - 40} 个")
    return "\n".join(lines)


def py_imports(path: str, root: Path, group: bool = True) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"
    src, tree, err = _parse_py(p)
    if err:
        return err
    stdlib: set = set()
    third: set = set()
    local: set = set()
    stdlib_mods = (sys.stdlib_module_names
                   if hasattr(sys, "stdlib_module_names") else set())

    def _classify(name: str):
        top = name.split(".")[0]
        if not top:
            return
        if top in stdlib_mods:
            stdlib.add(name)
        else:
            third.add(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                _classify(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                local.add("." * node.level + (node.module or ""))
                continue
            _classify(node.module or "")

    if not group:
        all_imports = sorted(stdlib | third | local)
        return "\n".join(all_imports) if all_imports else "(无 import)"
    lines = []
    if stdlib:
        lines.append(f"标准库 ({len(stdlib)}):")
        for m in sorted(stdlib):
            lines.append(f"  {m}")
    if third:
        lines.append("")
        lines.append(f"第三方 ({len(third)}):")
        for m in sorted(third):
            lines.append(f"  {m}")
    if local:
        lines.append("")
        lines.append(f"本地/相对 ({len(local)}):")
        for m in sorted(local):
            lines.append(f"  {m}")
    return "\n".join(lines) if lines else "(无 import)"


def py_find_def(name: str, path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"
    src, tree, err = _parse_py(p)
    if err:
        return err
    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            if node.name == name:
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                results.append((node.lineno, kind, node.name))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    results.append((node.lineno, "assign", name))
    if not results:
        return f"未在 {path} 找到 '{name}'"
    lines = [f"在 {path} 找到 {len(results)} 处:"]
    for ln, kind, nm in results:
        lines.append(f"  L{ln:>4}  {kind:<8} {nm}")
    return "\n".join(lines)


def py_unused_imports(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"
    src, tree, err = _parse_py(p)
    if err:
        return err
    imported: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias = a.asname or a.name.split(".")[0]
                imported[alias] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                alias = a.asname or a.name
                imported[alias] = node.lineno
    used: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            n = node
            while isinstance(n, ast.Attribute):
                n = n.value
            if isinstance(n, ast.Name):
                used.add(n.id)
    unused = [(name, ln) for name, ln in imported.items()
              if name not in used]
    if not unused:
        return f"{path}: 没有未使用的 import ✓"
    lines = [f"{path}: 发现 {len(unused)} 个可能未使用的 import:"]
    for name, ln in sorted(unused, key=lambda x: x[1]):
        lines.append(f"  L{ln:>4}  {name}")
    lines.append("")
    lines.append("（注意：可能通过 getattr/exec/字符串引用，"
                 "只是静态分析结果）")
    return "\n".join(lines)