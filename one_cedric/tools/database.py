"""数据库客户端：PostgreSQL / MySQL / SQLite / MongoDB。

凭证配置：环境变量
  PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
  MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE
  MONGO_URI
或直接传 conn / uri 参数。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .sandbox import _as_int, _resolve_path


MAX_ROWS = 500
QUERY_TIMEOUT = 30


def _row_limit(n):
    try:
        return max(1, min(_as_int(n, 100), MAX_ROWS))
    except Exception:
        return 100


# ═══════════════════════════════════════════════════════════════════════ #
# PostgreSQL
# ═══════════════════════════════════════════════════════════════════════ #

def _pg_connect(conn: str, database: str = ""):
    try:
        import psycopg2
    except ImportError:
        return None, "ERROR: 需要 psycopg2-binary（pip install psycopg2-binary）"

    params = {}
    if conn:
        try:
            params = json.loads(conn)
        except json.JSONDecodeError:
            # 尝试 DSN 字符串
            params = {"dsn": conn}

    if "dsn" in params:
        try:
            return psycopg2.connect(params["dsn"]), ""
        except Exception as exc:
            return None, f"ERROR: 连接失败: {exc}"

    host = params.get("host") or os.environ.get("PGHOST", "localhost")
    port = int(params.get("port") or os.environ.get("PGPORT", 5432))
    user = params.get("user") or os.environ.get("PGUSER", "")
    password = params.get("password") or os.environ.get("PGPASSWORD", "")
    db = database or params.get("database") or os.environ.get("PGDATABASE", "")

    if not user:
        return None, "ERROR: 需要 user（或设置 PGUSER）"
    if not db:
        return None, "ERROR: 需要 database"

    try:
        return psycopg2.connect(host=host, port=port, user=user,
                                password=password, dbname=db,
                                connect_timeout=10), ""
    except Exception as exc:
        return None, f"ERROR: 连接失败: {exc}"


def postgres_query(conn: str, query: str, database: str = "",
                   params: list | None = None, limit: int = 100) -> str:
    if not query or not query.strip():
        return "ERROR: query 不能为空"
    c, err = _pg_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute(query, params or [])
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(_row_limit(limit))
            lines = ["\t".join(cols), "-" * 40]
            for r in rows:
                lines.append("\t".join(
                    "NULL" if v is None else str(v)[:80] for v in r
                ))
            return f"返回 {len(rows)} 行\n" + "\n".join(lines)
        else:
            c.commit()
            return f"影响 {cur.rowcount} 行"
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


def postgres_list_tables(conn: str, database: str = "") -> str:
    c, err = _pg_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        rows = cur.fetchall()
        lines = [f"表（{len(rows)}）："]
        for schema, name in rows:
            lines.append(f"  {schema}.{name}")
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


def postgres_describe(conn: str, table: str, database: str = "") -> str:
    if not table:
        return "ERROR: 需要 table"
    c, err = _pg_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, [table])
        rows = cur.fetchall()
        if not rows:
            return f"未找到表 {table}"
        lines = [f"表 {table}:", ""]
        for name, dtype, nullable, default in rows:
            nn = "NULL" if nullable == "YES" else "NOT NULL"
            dft = f" DEFAULT {default}" if default else ""
            lines.append(f"  {name:<30} {dtype:<20} {nn}{dft}")
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════ #
# MySQL
# ═══════════════════════════════════════════════════════════════════════ #

def _mysql_connect(conn: str, database: str = ""):
    try:
        import pymysql
    except ImportError:
        try:
            import mysql.connector as pymysql
        except ImportError:
            return None, ("ERROR: 需要 pymysql 或 mysql-connector-python\n"
                          "  pip install pymysql")

    params = {}
    if conn:
        try:
            params = json.loads(conn)
        except json.JSONDecodeError:
            params = {"host": conn}

    host = params.get("host") or os.environ.get("MYSQL_HOST", "localhost")
    port = int(params.get("port") or os.environ.get("MYSQL_PORT", 3306))
    user = params.get("user") or os.environ.get("MYSQL_USER", "root")
    password = params.get("password") or os.environ.get("MYSQL_PASSWORD", "")
    db = database or params.get("database") or os.environ.get("MYSQL_DATABASE", "")

    try:
        if hasattr(pymysql, "connect"):
            kw = {"host": host, "port": port, "user": user,
                  "password": password, "connect_timeout": 10,
                  "charset": "utf8mb4"}
            if db:
                kw["database"] = db
            return pymysql.connect(**kw), ""
    except Exception as exc:
        return None, f"ERROR: 连接失败: {exc}"
    return None, "ERROR: 无法建立 MySQL 连接"


def mysql_query(conn: str, query: str, database: str = "",
                params: list | None = None, limit: int = 100) -> str:
    if not query or not query.strip():
        return "ERROR: query 不能为空"
    c, err = _mysql_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute(query, params or [])
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(_row_limit(limit))
            lines = ["\t".join(cols), "-" * 40]
            for r in rows:
                lines.append("\t".join(
                    "NULL" if v is None else str(v)[:80] for v in r
                ))
            return f"返回 {len(rows)} 行\n" + "\n".join(lines)
        else:
            c.commit()
            return f"影响 {cur.rowcount} 行"
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


def mysql_list_tables(conn: str, database: str = "") -> str:
    c, err = _mysql_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute("SHOW TABLES")
        rows = cur.fetchall()
        lines = [f"表（{len(rows)}）："]
        for r in rows:
            lines.append(f"  {r[0]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


def mysql_describe(conn: str, table: str, database: str = "") -> str:
    if not table:
        return "ERROR: 需要 table"
    c, err = _mysql_connect(conn, database)
    if err:
        return err
    try:
        cur = c.cursor()
        cur.execute(f"DESCRIBE `{table}`")
        rows = cur.fetchall()
        if not rows:
            return f"未找到表 {table}"
        lines = [f"表 {table}:", ""]
        for r in rows:
            field, typ, nullable, key, default, extra = (r + (None,) * 6)[:6]
            lines.append(f"  {field:<30} {typ:<20} "
                         f"{'NULL' if nullable == 'YES' else 'NOT NULL'}"
                         f"  {key or ''}  {extra or ''}")
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        try:
            c.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════ #
# SQLite（增强版：多文件/DDL）
# ═══════════════════════════════════════════════════════════════════════ #

def sqlite_tables(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 数据库不存在: {path}"

    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error as exc:
        return f"ERROR: {exc}"

    try:
        cur = conn.cursor()
        cur.execute("SELECT name, type FROM sqlite_master "
                    "WHERE type IN ('table','view') ORDER BY name")
        rows = cur.fetchall()
        lines = [f"数据库: {path}", f"表/视图: {len(rows)}", ""]
        for name, typ in rows:
            try:
                cur.execute(f"SELECT COUNT(*) FROM `{name}`")
                cnt = cur.fetchone()[0]
                lines.append(f"  [{typ}] {name}  ({cnt} 行)")
            except Exception:
                lines.append(f"  [{typ}] {name}")
        return "\n".join(lines)
    except sqlite3.Error as exc:
        return f"ERROR: {exc}"
    finally:
        conn.close()


def sqlite_schema(path: str, table: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 数据库不存在: {path}"

    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error as exc:
        return f"ERROR: {exc}"

    try:
        cur = conn.cursor()
        if table:
            cur.execute(
                "SELECT sql FROM sqlite_master WHERE name = ?",
                (table,))
            row = cur.fetchone()
            if not row:
                return f"未找到表 {table}"
            return f"表 {table} 的 DDL:\n\n{row[0]}"

        cur.execute("SELECT name, sql FROM sqlite_master "
                    "WHERE type='table' AND sql IS NOT NULL ORDER BY name")
        lines = []
        for name, sql in cur.fetchall():
            lines.append(f"--- {name} ---")
            lines.append(sql or "(无)")
            lines.append("")
        return "\n".join(lines) if lines else "（无表）"
    except sqlite3.Error as exc:
        return f"ERROR: {exc}"
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════ #
# MongoDB
# ═══════════════════════════════════════════════════════════════════════ #

def _mongo_client(uri: str):
    try:
        from pymongo import MongoClient
    except ImportError:
        return None, "ERROR: 需要 pymongo（pip install pymongo）"

    uri = uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.server_info()
        return client, ""
    except Exception as exc:
        return None, f"ERROR: 连接失败: {exc}"


def mongo_list_databases(uri: str = "") -> str:
    client, err = _mongo_client(uri)
    if err:
        return err
    try:
        dbs = client.list_database_names()
        lines = [f"数据库（{len(dbs)}）："]
        for name in dbs:
            try:
                size = client[name].command("dbstats").get("dataSize", 0)
                lines.append(f"  {name}  ({size} bytes)")
            except Exception:
                lines.append(f"  {name}")
        return "\n".join(lines)
    finally:
        client.close()


def mongo_list_collections(uri: str, database: str) -> str:
    if not database:
        return "ERROR: 需要 database"
    client, err = _mongo_client(uri)
    if err:
        return err
    try:
        cols = client[database].list_collection_names()
        lines = [f"{database} 的集合（{len(cols)}）："]
        for c in cols:
            try:
                cnt = client[database][c].estimated_document_count()
                lines.append(f"  {c}  (~{cnt} 文档)")
            except Exception:
                lines.append(f"  {c}")
        return "\n".join(lines)
    finally:
        client.close()


def mongo_find(uri: str, database: str, collection: str,
               filter_json: str = "", limit: int = 20,
               projection_json: str = "") -> str:
    if not database or not collection:
        return "ERROR: 需要 database 和 collection"
    try:
        flt = json.loads(filter_json) if filter_json else {}
    except json.JSONDecodeError as exc:
        return f"ERROR: filter_json 解析失败: {exc}"
    try:
        proj = json.loads(projection_json) if projection_json else None
    except json.JSONDecodeError as exc:
        return f"ERROR: projection_json 解析失败: {exc}"

    client, err = _mongo_client(uri)
    if err:
        return err
    try:
        col = client[database][collection]
        cursor = col.find(flt, proj).limit(_row_limit(limit))
        docs = list(cursor)
        if not docs:
            return "无匹配文档"
        lines = [f"返回 {len(docs)} 个文档：", ""]
        for i, d in enumerate(docs, 1):
            lines.append(f"[{i}]")
            lines.append(json.dumps(d, ensure_ascii=False,
                                    default=str, indent=2)[:2000])
            lines.append("")
        return "\n".join(lines)
    finally:
        client.close()


def mongo_aggregate(uri: str, database: str, collection: str,
                    pipeline_json: str, limit: int = 50) -> str:
    if not database or not collection or not pipeline_json:
        return "ERROR: 需要 database / collection / pipeline_json"
    try:
        pipeline = json.loads(pipeline_json)
    except json.JSONDecodeError as exc:
        return f"ERROR: pipeline_json 解析失败: {exc}"
    if not isinstance(pipeline, list):
        return "ERROR: pipeline_json 必须是数组"

    client, err = _mongo_client(uri)
    if err:
        return err
    try:
        col = client[database][collection]
        docs = list(col.aggregate(pipeline))[: _row_limit(limit)]
        lines = [f"返回 {len(docs)} 个文档：", ""]
        for i, d in enumerate(docs, 1):
            lines.append(f"[{i}]")
            lines.append(json.dumps(d, ensure_ascii=False,
                                    default=str, indent=2)[:2000])
            lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: {exc}"
    finally:
        client.close()


def mongo_stats(uri: str, database: str) -> str:
    if not database:
        return "ERROR: 需要 database"
    client, err = _mongo_client(uri)
    if err:
        return err
    try:
        stats = client[database].command("dbstats")
        lines = [f"数据库 {database} 统计:", ""]
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    finally:
        client.close()