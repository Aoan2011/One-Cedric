"""结构化数据：json_query / csv_query / sqlite / json_schema_validate。"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

from ..config import MAX_CSV_ROWS, MAX_SQLITE_ROWS
from .sandbox import _as_int, _resolve_path


def _json_path_get(obj, path: str):
    if not path:
        return obj
    tokens = []
    for part in path.split("."):
        if not part:
            continue
        m = re.match(r"^([^\[]*)((?:\[\d+\]|\[\*\])*)$", part)
        if not m:
            tokens.append(("key", part))
            continue
        name, idxs = m.group(1), m.group(2)
        if name:
            tokens.append(("key", name))
        for idx in re.findall(r"\[(\d+|\*)\]", idxs):
            tokens.append(("idx", idx))
    cur = [obj]
    for kind, val in tokens:
        nxt = []
        for c in cur:
            if kind == "key":
                if isinstance(c, dict) and val in c:
                    nxt.append(c[val])
            else:
                if isinstance(c, list):
                    if val == "*":
                        nxt.extend(c)
                    else:
                        i = int(val)
                        if 0 <= i < len(c):
                            nxt.append(c[i])
        cur = nxt
        if not cur:
            return None
    return cur[0] if len(cur) == 1 else cur


def json_query(root: Path, file: str, path: str = "") -> str:
    if not file:
        return "ERROR: file 不能为空。"
    p, err = _resolve_path(root, file)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {file}"
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR: 读取失败: {exc}"
    suffix = p.suffix.lower()
    data = None
    if suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return f"ERROR: JSON 解析失败: {exc}"
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(raw)
        except ImportError:
            return "ERROR: 需要 PyYAML（pip install pyyaml）才能解析 YAML。"
        except Exception as exc:
            return f"ERROR: YAML 解析失败: {exc}"
    else:
        return f"ERROR: 不支持的扩展名: {suffix}（需 .json/.yaml/.yml）"
    if path:
        val = _json_path_get(data, path)
        if val is None:
            return f"ERROR: 路径 {path!r} 未命中。"
        out = json.dumps(val, ensure_ascii=False, indent=2, default=str)
    else:
        out = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(out) > 20000:
        out = out[:20000] + f"\n... (输出截断，原始 {len(out)} 字符)"
    header = f"文件: {file}" + (f"  路径: {path}" if path else "  (整文档)")
    return header + "\n" + out


def _is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def csv_query(root: Path, path: str, columns: list | None = None,
              limit=None, delimiter: str = ",") -> str:
    if not path:
        return "ERROR: path 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_file():
        return f"ERROR: 文件不存在: {path}"
    try:
        with open(p, "r", encoding="utf-8", errors="replace",
                  newline="") as f:
            reader = csv.reader(
                f, delimiter=delimiter[0] if delimiter else ",")
            header = next(reader, None)
            if header is None:
                return f"文件: {path}\n(空文件)"
            rows = []
            for i, r in enumerate(reader):
                rows.append(r)
                if len(rows) > 10000:
                    break
    except (OSError, csv.Error) as exc:
        return f"ERROR: 读取失败: {exc}"
    n_rows = len(rows)
    n_cols = len(header)
    types = ["?"] * n_cols
    for ci in range(n_cols):
        col_vals = [r[ci] for r in rows if ci < len(r) and r[ci] != ""]
        if not col_vals:
            types[ci] = "empty"
            continue
        sample = col_vals[:100]
        if all(_is_int(v) for v in sample):
            types[ci] = "int"
        elif all(_is_float(v) for v in sample):
            types[ci] = "float"
        elif all(v.lower() in ("true", "false", "yes", "no", "0", "1")
                 for v in sample):
            types[ci] = "bool"
        else:
            types[ci] = "str"
    if columns:
        keep = [c for c in columns if c in header]
        missing = [c for c in columns if c not in header]
        if missing:
            return (f"ERROR: 找不到列: {', '.join(missing)}\n"
                    f"可用列: {', '.join(header)}")
        idx = [header.index(c) for c in keep]
        show_header = keep
        show_rows = [[r[i] if i < len(r) else "" for i in idx]
                     for r in rows]
    else:
        show_header = header
        show_rows = rows
    lim = _as_int(limit, MAX_CSV_ROWS)
    if lim <= 0:
        lim = MAX_CSV_ROWS
    truncated = len(show_rows) > lim
    show_rows = show_rows[:lim]
    lines = [f"文件: {path}", f"行数: {n_rows}  列数: {n_cols}"]
    if not columns:
        type_line = "  ".join(f"{h}({t})"
                              for h, t in zip(header, types))
        lines.append(f"列: {type_line}")
    lines.append("")
    lines.append("\t".join(show_header))
    lines.append("-" * 60)
    for r in show_rows:
        lines.append("\t".join(str(v) for v in r))
    if truncated:
        lines.append(f"... (还有 {len(rows) - lim} 行未显示)")
    return "\n".join(lines)


_WRITE_SQL_KEYWORDS = {
    "insert", "update", "delete", "create", "drop", "alter",
    "truncate", "grant", "revoke", "replace", "rename",
    "lock", "unlock", "analyze", "vacuum", "reindex",
    "call", "do", "merge",
}


def _sql_is_write(query: str) -> tuple:
    """判断 SQL 是否写操作。返回 (is_write, keyword)。"""
    if not query:
        return False, ""
    q = re.sub(r"--[^\n]*", "", query)
    q = re.sub(r"/\*.*?\*/", "", q, flags=re.DOTALL)
    q = q.strip().lower()
    if not q:
        return False, ""
    m = re.match(r"^(\w+)", q)
    if not m:
        return False, ""
    first = m.group(1)
    if first == "with":
        for kw in ("insert", "update", "delete", "create", "drop",
                   "alter", "truncate"):
            if re.search(rf"\b{kw}\s+\b", q):
                return True, kw.upper()
        return False, ""
    if first in _WRITE_SQL_KEYWORDS:
        return True, first.upper()
    return False, ""


# 兼容 core 里的 import
def sql_is_write(query: str) -> tuple:
    return _sql_is_write(query)


def sqlite_query(root: Path, path: str, query: str,
                 params: list | None = None,
                 allow_write: bool = False,
                 max_rows=None) -> tuple:
    if not path:
        return "", False, "ERROR: path 不能为空。"
    if not query or not query.strip():
        return "", False, "ERROR: query 不能为空。"
    p, err = _resolve_path(root, path)
    if err:
        return "", False, err
    if not p.exists() or not p.is_file():
        return "", False, f"ERROR: 数据库不存在: {path}"
    is_write, kw = _sql_is_write(query)
    if is_write and not allow_write:
        return "", False, (f"ERROR: 当前为只读模式。若要执行写操作，"
                           f"请传 allow_write=true 并等待用户确认。")
    if is_write and allow_write:
        return "", True, ""
    try:
        uri = f"file:{p}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.Error as exc:
        return "", False, f"ERROR: 打开数据库失败: {exc}"
    try:
        cur = conn.cursor()
        cur.execute(query, params or [])
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            limit = _as_int(max_rows, MAX_SQLITE_ROWS)
            if limit <= 0:
                limit = MAX_SQLITE_ROWS
            truncated = len(rows) > limit
            rows = rows[:limit]
            lines = ["\t".join(cols), "-" * 40]
            for r in rows:
                lines.append("\t".join(
                    "NULL" if v is None else str(v) for v in r))
            header = (f"查询成功，返回 {len(rows)} 行"
                      + ("（已截断）" if truncated else ""))
            return header + "\n" + "\n".join(lines), False, ""
        else:
            conn.commit()
            return f"执行完成，影响 {cur.rowcount} 行。", False, ""
    except sqlite3.Error as exc:
        return "", False, f"ERROR: SQL 执行失败: {exc}"
    finally:
        conn.close()


def json_schema_validate(root: Path, data_file: str,
                         schema_file: str) -> str:
    try:
        import jsonschema
    except ImportError:
        return "ERROR: 需要 jsonschema。运行：pip install jsonschema"
    p_data, err = _resolve_path(root, data_file)
    if err:
        return err
    p_schema, err = _resolve_path(root, schema_file)
    if err:
        return err
    if not p_data.exists():
        return f"ERROR: 数据文件不存在: {data_file}"
    if not p_schema.exists():
        return f"ERROR: Schema 文件不存在: {schema_file}"

    def _load(p: Path):
        txt = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
                return yaml.safe_load(txt)
            except ImportError:
                raise ValueError("需要 PyYAML 解析 YAML")
            except Exception as exc:
                raise ValueError(f"YAML 解析失败: {exc}")
        try:
            return json.loads(txt)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}")

    try:
        data = _load(p_data)
        schema = _load(p_schema)
    except ValueError as exc:
        return f"ERROR: {exc}"

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(p) for p in exc.absolute_path) or "(根)"
        return (f"校验失败 ✗\n"
                f"位置: {path}\n"
                f"错误: {exc.message}\n"
                f"规则: {exc.validator}={exc.validator_value}")
    except jsonschema.SchemaError as exc:
        return f"ERROR: Schema 本身有问题: {exc.message}"

    return f"校验通过 ✓\n文件: {data_file}\nSchema: {schema_file}"