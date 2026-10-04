"""工具的 JSON schema（OpenAI function calling 格式）。纯数据。"""
from __future__ import annotations

from ..config import (
    MAX_GLOB_RESULTS, MAX_SEARCH_RESULTS, MAX_SQLITE_ROWS,
    MAX_CSV_ROWS, MAX_WEB_BYTES, DEFAULT_SHELL_TIMEOUT,
    HTTP_DEFAULT_TIMEOUT,
)

TOOLS = [
    # ==================== 文件读 ====================
    {"type": "function", "function": {
        "name": "read_file",
        "description": (
            "读取本地文本文件，带行号。\n"
            "自动检测编码（UTF-8 / GBK / Big5 / Shift-JIS 等）。\n"
            "可用 start_line/end_line 读取指定行范围。"
        ),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件路径。"},
            "start_line": {"type": "integer", "description": "起始行号，从 1 开始。"},
            "end_line": {"type": "integer", "description": "结束行号（含）。"},
            "encoding": {"type": "string",
                         "description": "强制指定编码（如 gbk），留空则自动检测。"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "列出目录下的文件和子目录。可选择递归列出。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目录路径。"},
            "recursive": {"type": "boolean", "description": "是否递归。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "search_in_files",
        "description": "在指定目录下的文件中搜索关键词。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "关键词。"},
            "path": {"type": "string", "description": "搜索目录。"},
            "file_pattern": {"type": "string", "description": "文件名通配符。"},
        }, "required": ["pattern"]},
    }},
    {"type": "function", "function": {
        "name": "file_info",
        "description": "获取文件信息：大小、行数、修改时间。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件路径。"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "glob",
        "description": "按通配符查找文件。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "通配符。"},
            "path": {"type": "string", "description": "搜索起点。"},
            "max_results": {"type": "integer",
                            "description": f"最多条数，默认 {MAX_GLOB_RESULTS}。"},
        }, "required": ["pattern"]},
    }},
    {"type": "function", "function": {
        "name": "grep_regex",
        "description": "用正则表达式在文件中搜索。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Python 正则。"},
            "path": {"type": "string", "description": "搜索目录。"},
            "file_pattern": {"type": "string", "description": "文件名通配符。"},
            "case_insensitive": {"type": "boolean", "description": "忽略大小写。"},
            "max_results": {"type": "integer",
                            "description": f"最多条数，默认 {MAX_SEARCH_RESULTS}。"},
        }, "required": ["pattern"]},
    }},

    # ==================== 网络 ====================
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "抓取 http/https URL 内容。私有地址会被拒绝。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL。"},
            "max_bytes": {"type": "integer",
                          "description": f"最多字节数，默认 {MAX_WEB_BYTES}。"},
            "raw": {"type": "boolean", "description": "true 返回原始 HTML。"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "http_request",
        "description": "发 HTTP 请求。私有地址会被拒绝。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL。"},
            "method": {"type": "string", "description": "HTTP 方法。"},
            "headers": {"type": "object", "description": "请求头。"},
            "body": {"type": "string", "description": "请求体。"},
            "timeout": {"type": "integer",
                        "description": f"超时秒数，默认 {HTTP_DEFAULT_TIMEOUT}。"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": (
            "多引擎聚合搜索（Bing 国内 + Bing 国际 + 百度），"
            "BM25 语义重排 + 位置权重融合。返回 Top N 标题+摘要+URL。"
            "适合快速扫一遍有什么。需要内容时用 web_research。"
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词。"},
            "max_results": {"type": "integer",
                            "description": "返回条数，默认 13，最大 30。"},
            "engines": {"type": "array",
                        "items": {"type": "string",
                                  "enum": ["bing_cn", "bing_intl", "baidu"]},
                        "description": "指定引擎，默认全部。"},
            "include_aggregates": {"type": "boolean",
                                    "description": "是否包含知识卡片，默认 true。"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "web_research",
        "description": (
            "搜索 + 抓取 top N 网页正文（trafilatura / readability 提取，"
            "BM25 重排后取最相关页面）。返回：知识卡片 + 网页正文。"
            "需要基于内容回答问题时优先用这个。"
            "mode=fast(5页/1.5k字/快) / balanced(8页/2.5k字/默认) / deep(12页/5k字/慢)。"
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词。"},
            "mode": {"type": "string",
                     "enum": ["fast", "balanced", "deep"],
                     "description": "抓取强度，默认 balanced。"},
            "top_n": {"type": "integer",
                      "description": "覆盖 mode 的页面数（1-15）。"},
            "max_chars_per_page": {"type": "integer",
                                    "description": "覆盖 mode 的每页字符数。"},
            "engines": {"type": "array",
                        "items": {"type": "string",
                                  "enum": ["bing_cn", "bing_intl", "baidu"]},
                        "description": "指定引擎，默认全部。"},
        }, "required": ["query"]},
    }},

    # ==================== 数据 ====================
    {"type": "function", "function": {
        "name": "json_query",
        "description": "查询 JSON 或 YAML 文件。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string", "description": "文件路径。"},
            "path": {"type": "string", "description": "点号路径。"},
        }, "required": ["file"]},
    }},
    {"type": "function", "function": {
        "name": "csv_query",
        "description": "读取 CSV 文件。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "CSV 路径。"},
            "columns": {"type": "array", "items": {"type": "string"},
                        "description": "列过滤。"},
            "limit": {"type": "integer",
                      "description": f"最大行数，默认 {MAX_CSV_ROWS}。"},
            "delimiter": {"type": "string", "description": "分隔符。"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "sqlite",
        "description": "查询 SQLite 数据库。默认只读。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "数据库路径。"},
            "query": {"type": "string", "description": "SQL 语句。"},
            "params": {"type": "array", "items": {},
                       "description": "参数化绑定值。"},
            "allow_write": {"type": "boolean", "description": "允许写操作。"},
            "max_rows": {"type": "integer",
                         "description": f"最大行数，默认 {MAX_SQLITE_ROWS}。"},
        }, "required": ["path", "query"]},
    }},
    {"type": "function", "function": {
        "name": "json_schema_validate",
        "description": "用 JSON Schema 校验 JSON/YAML 文件。需安装 jsonschema。",
        "parameters": {"type": "object", "properties": {
            "data_file": {"type": "string",
                          "description": "待校验的 JSON/YAML 文件。"},
            "schema_file": {"type": "string",
                            "description": "JSON Schema 文件。"},
        }, "required": ["data_file", "schema_file"]},
    }},
    {"type": "function", "function": {
        "name": "sqlite_tables",
        "description": "列出 SQLite 表/视图及行数。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "sqlite_schema",
        "description": "查看 SQLite 表 DDL。table 留空则列出所有表。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "table": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "postgres_query",
        "description": "PostgreSQL 查询。conn 是 JSON 字符串或 DSN；"
                       "或依赖 PG* 环境变量。写操作会弹确认。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"},
            "database": {"type": "string"},
            "query": {"type": "string"},
            "params": {"type": "array"},
            "limit": {"type": "integer", "description": "默认 100，上限 500。"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "postgres_list_tables",
        "description": "列出 PostgreSQL 表。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"}, "database": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "postgres_describe",
        "description": "查看 PostgreSQL 表结构。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"}, "database": {"type": "string"},
            "table": {"type": "string"},
        }, "required": ["table"]},
    }},
    {"type": "function", "function": {
        "name": "mysql_query",
        "description": "MySQL 查询。conn 是 JSON 或 host；"
                       "或依赖 MYSQL_* 环境变量。写操作会弹确认。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"},
            "database": {"type": "string"},
            "query": {"type": "string"},
            "params": {"type": "array"},
            "limit": {"type": "integer"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "mysql_list_tables",
        "description": "列出 MySQL 表。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"}, "database": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "mysql_describe",
        "description": "查看 MySQL 表结构。",
        "parameters": {"type": "object", "properties": {
            "conn": {"type": "string"}, "database": {"type": "string"},
            "table": {"type": "string"},
        }, "required": ["table"]},
    }},
    {"type": "function", "function": {
        "name": "mongo_list_databases",
        "description": "列出 MongoDB 数据库。uri 留空则用 MONGO_URI。",
        "parameters": {"type": "object", "properties": {
            "uri": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "mongo_list_collections",
        "description": "列出 MongoDB 集合。",
        "parameters": {"type": "object", "properties": {
            "uri": {"type": "string"}, "database": {"type": "string"},
        }, "required": ["database"]},
    }},
    {"type": "function", "function": {
        "name": "mongo_find",
        "description": "MongoDB 查询文档。",
        "parameters": {"type": "object", "properties": {
            "uri": {"type": "string"}, "database": {"type": "string"},
            "collection": {"type": "string"},
            "filter_json": {"type": "string"},
            "projection_json": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["database", "collection"]},
    }},
    {"type": "function", "function": {
        "name": "mongo_aggregate",
        "description": "MongoDB 聚合管道。",
        "parameters": {"type": "object", "properties": {
            "uri": {"type": "string"}, "database": {"type": "string"},
            "collection": {"type": "string"},
            "pipeline_json": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["database", "collection", "pipeline_json"]},
    }},
    {"type": "function", "function": {
        "name": "mongo_stats",
        "description": "MongoDB 数据库统计。",
        "parameters": {"type": "object", "properties": {
            "uri": {"type": "string"}, "database": {"type": "string"},
        }, "required": ["database"]},
    }},

    # ==================== 系统 ====================
    {"type": "function", "function": {
        "name": "env_info",
        "description": "运行环境信息。",
        "parameters": {"type": "object", "properties": {
            "include": {"type": "string",
                        "enum": ["all", "system", "python", "packages", "env"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "process_info",
        "description": "查看进程或端口。",
        "parameters": {"type": "object", "properties": {
            "scope": {"type": "string",
                      "enum": ["processes", "ports", "all"]},
            "filter": {"type": "string", "description": "过滤子串。"},
            "limit": {"type": "integer", "description": "最大行数。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "calculate",
        "description": "算术表达式求值。",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "表达式。"},
        }, "required": ["expression"]},
    }},
    {"type": "function", "function": {
        "name": "system_metrics",
        "description": "系统资源快照：CPU、内存、磁盘、网络。",
        "parameters": {"type": "object", "properties": {
            "include": {"type": "string",
                        "enum": ["all", "cpu", "memory", "disk", "network"],
                        "description": "采集内容，默认 all。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "diff_files",
        "description": "对比两个文件或目录。",
        "parameters": {"type": "object", "properties": {
            "a": {"type": "string", "description": "左路径。"},
            "b": {"type": "string", "description": "右路径。"},
            "context": {"type": "integer", "description": "上下文行数。"},
        }, "required": ["a", "b"]},
    }},
    {"type": "function", "function": {
        "name": "pip_list",
        "description": "列出已安装的 Python 包。",
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "string"},
            "outdated": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "pip_show",
        "description": "显示某个 Python 包的详细信息。",
        "parameters": {"type": "object", "properties": {
            "package": {"type": "string"},
        }, "required": ["package"]},
    }},
    {"type": "function", "function": {
        "name": "disk_tree",
        "description": "递归列出目录下文件大小（Top N）+ 按扩展名聚合。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "max_depth": {"type": "integer"},
            "top": {"type": "integer"},
            "min_size": {"type": "integer"},
        }},
    }},    # ==================== 写 ====================
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "对已有文件做精确字符串替换。old_string 必须逐字符匹配。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件路径。"},
            "old_string": {"type": "string", "description": "原文本。"},
            "new_string": {"type": "string", "description": "新文本。"},
            "replace_all": {"type": "boolean", "description": "替换全部。"},
        }, "required": ["path", "old_string", "new_string"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "创建新文件或整体覆盖已有文件。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件路径。"},
            "content": {"type": "string", "description": "完整内容。"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "apply_patch",
        "description": "应用 unified diff 补丁。",
        "parameters": {"type": "object", "properties": {
            "patch": {"type": "string", "description": "unified diff 文本。"},
        }, "required": ["patch"]},
    }},
    {"type": "function", "function": {
        "name": "file_ops",
        "description": "文件系统操作：copy / move / delete / mkdir。",
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["copy", "move", "delete", "mkdir"]},
            "src": {"type": "string", "description": "源路径。"},
            "dst": {"type": "string", "description": "目标路径。"},
            "recursive": {"type": "boolean", "description": "目录操作时递归。"},
            "overwrite": {"type": "boolean", "description": "覆盖已存在目标。"},
        }, "required": ["op"]},
    }},
    {"type": "function", "function": {
        "name": "find_replace",
        "description": "跨文件批量替换（带 diff 预览 + 确认）。支持 glob 过滤 + 正则模式。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "要查找的文本或正则。"},
            "replacement": {"type": "string", "description": "替换文本。"},
            "glob": {"type": "string", "description": "文件通配符，默认 **/*。"},
            "path": {"type": "string", "description": "搜索起点目录。"},
            "use_regex": {"type": "boolean", "description": "按正则匹配。"},
            "case_insensitive": {"type": "boolean", "description": "忽略大小写。"},
            "max_files": {"type": "integer", "description": "最多修改文件数，默认 20。"},
        }, "required": ["pattern", "replacement"]},
    }},
    {"type": "function", "function": {
        "name": "file_attrs",
        "description": (
            "读取或修改文件属性。\n"
            "op=get 读属性（只读）；op=attrs / perms / owner 需确认。\n"
            "attrs: Windows R/H/S/A 属性；perms: Unix 权限；"
            "owner: Unix 属主。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["get", "attrs", "perms", "owner", "bulk"]},
            "path": {"type": "string"},
            "action": {"type": "string",
                       "enum": ["add", "remove", "set", "clear"]},
            "attrs": {"type": "array", "items": {"type": "string"}},
            "mode": {"type": "string"},
            "user": {"type": "string"},
            "group": {"type": "string"},
            "recursive": {"type": "boolean"},
            "filter": {"type": "string"},
            "max_items": {"type": "integer"},
        }, "required": ["op", "path"]},
    }},

    # ==================== 执行 ====================
    {"type": "function", "function": {
        "name": "bash",
        "description": "执行白名单命令。不支持 shell 操作符。",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "命令。"},
            "timeout_seconds": {"type": "integer",
                                "description": f"超时秒数，默认 {DEFAULT_SHELL_TIMEOUT}。"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "bash_bg",
        "description": "后台运行白名单命令。",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "命令。"},
            "log_file": {"type": "string", "description": "日志文件路径。"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "git",
        "description": "执行 git 操作。只读子命令直接执行，写需确认。",
        "parameters": {"type": "object", "properties": {
            "subcommand": {"type": "string", "description": "git 子命令。"},
            "args": {"type": "array", "items": {"type": "string"},
                     "description": "附加参数。"},
        }, "required": ["subcommand"]},
    }},
    {"type": "function", "function": {
        "name": "docker",
        "description": "执行 docker 命令。",
        "parameters": {"type": "object", "properties": {
            "subcommand": {"type": "string", "description": "docker 子命令。"},
            "args": {"type": "array", "items": {"type": "string"},
                     "description": "附加参数。"},
        }, "required": ["subcommand"]},
    }},
    {"type": "function", "function": {
        "name": "python_exec",
        "description": (
            "执行 Python 代码，用于数据分析、图表生成、算法验证和文本处理。"
            "每次执行前都会向用户请求许可；获准后代码以当前用户权限运行，"
            "不受导入或内建函数白名单限制。\n"
            "install_packages 可在获得许可后 pip install 所需依赖。\n"
            "matplotlib 图表自动保存到 .cedric_artifacts/。"
        ),
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": "Python 代码。"},
            "work_dir": {"type": "string", "description": "工作目录。"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 30。"},
            "save_code": {"type": "boolean",
                          "description": "保存代码到 cedric_script.py。"},
            "install_packages": {"type": "array",
                                  "items": {"type": "string"},
                                  "description": "许可后要 pip install 的包名列表。"},
            "auto_install": {"type": "boolean",
                             "description": "把未安装的 import 模块加入 pip 安装列表。"},
        }, "required": ["code"]},
    }},
    {"type": "function", "function": {
        "name": "python_check",
        "description": "检查 Python 语法，不执行代码。",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string"},
        }, "required": ["code"]},
    }},
    {"type": "function", "function": {
        "name": "python_libs",
        "description": "列出 python_exec 可用的库和版本。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== 文本处理 ====================
    {"type": "function", "function": {
        "name": "regex_extract",
        "description": "用正则从文件/目录中提取匹配（返回捕获组）。"
                       "适合抓 IP、URL、日志字段。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Python 正则。"},
            "path": {"type": "string", "description": "文件或目录。"},
            "file_pattern": {"type": "string", "description": "文件名通配符。"},
            "unique": {"type": "boolean",
                       "description": "只返回唯一值，默认 true。"},
            "max_results": {"type": "integer",
                            "description": "最多返回条数，默认 100。"},
        }, "required": ["pattern", "path"]},
    }},
    {"type": "function", "function": {
        "name": "code_stats",
        "description": "统计代码：按语言统计文件数、总行数、"
                       "有效行、注释行、函数/类数。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目录。"},
            "exclude": {"type": "string",
                        "description": "排除模式（逗号分隔）。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "markdown_toc",
        "description": "提取 Markdown 文件的标题结构（TOC）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Markdown 文件。"},
            "max_level": {"type": "integer",
                          "description": "最大标题层级，默认 6。"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "template_render",
        "description": "简单的模板渲染：把 {{变量}} 替换成给定值。",
        "parameters": {"type": "object", "properties": {
            "template": {"type": "string", "description": "模板文本。"},
            "variables": {"type": "object", "description": "变量字典。"},
        }, "required": ["template", "variables"]},
    }},
    {"type": "function", "function": {
        "name": "word_frequency",
        "description": "词频统计（中英文混合）。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "file": {"type": "string"},
            "top": {"type": "integer", "description": "前 N 个，默认 30。"},
            "min_len": {"type": "integer", "description": "中文片段最小长度，默认 2。"},
            "stopwords": {"type": "string", "description": "逗号分隔的停用词。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "tokenize",
        "description": "分词（jieba 中文 + 英文正则）。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "file": {"type": "string"},
            "mode": {"type": "string", "enum": ["cn", "en", "mix", "all"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "simplify_chinese",
        "description": "繁简转换。direction: t2s/s2t/t2s_p/s2tw/s2hk。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "file": {"type": "string"},
            "direction": {"type": "string",
                          "enum": ["t2s", "s2t", "t2s_p", "s2tw", "s2hk"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "dedupe_lines",
        "description": "行去重（保留顺序）。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "file": {"type": "string"},
            "case_insensitive": {"type": "boolean"},
            "strip_whitespace": {"type": "boolean"},
            "keep_order": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "text_similarity",
        "description": "计算两段文本相似度。"
                       "algorithm: jaccard/dice/cosine/levenshtein。",
        "parameters": {"type": "object", "properties": {
            "text1": {"type": "string"}, "text2": {"type": "string"},
            "file1": {"type": "string"}, "file2": {"type": "string"},
            "algorithm": {"type": "string",
                          "enum": ["jaccard", "dice", "cosine",
                                   "levenshtein"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "strip_invisible",
        "description": "清除不可见字符（零宽、控制符、BOM 等）。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
        }},
    }},

    # ==================== 文件工具 ====================
    {"type": "function", "function": {
        "name": "hash_file",
        "description": "计算文件哈希（md5/sha1/sha256/sha512）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件路径。"},
            "algorithm": {"type": "string",
                          "enum": ["md5", "sha1", "sha256", "sha512"]},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "find_duplicates",
        "description": "查找重复文件（按内容 hash 分组）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目录。"},
            "min_size": {"type": "integer",
                         "description": "忽略小于此字节的文件。"},
            "max_groups": {"type": "integer",
                           "description": "最多返回组数，默认 50。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "pdf_extract",
        "description": "提取 PDF 文本。需安装 pypdf。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "PDF 文件。"},
            "start_page": {"type": "integer", "description": "起始页（1-based）。"},
            "end_page": {"type": "integer", "description": "结束页。"},
            "max_chars": {"type": "integer",
                          "description": "最多返回字符数，默认 20000。"},
        }, "required": ["path"]},
    }},

    # ==================== 编码 / 哈希 ====================
    {"type": "function", "function": {
        "name": "base64_codec",
        "description": "Base64 编码/解码。可以处理文本或文件。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["encode", "decode"]},
            "data": {"type": "string"},
            "file": {"type": "string"},
        }, "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "hash_text",
        "description": "计算文本或文件的哈希（支持 HMAC）。",
        "parameters": {"type": "object", "properties": {
            "data": {"type": "string"}, "file": {"type": "string"},
            "algorithm": {"type": "string",
                          "enum": ["md5", "sha1", "sha256", "sha512",
                                   "blake2b", "blake2s"]},
            "hmac_key": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "url_codec",
        "description": "URL 编码/解码。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["encode", "decode"]},
            "text": {"type": "string"},
        }, "required": ["action", "text"]},
    }},
    {"type": "function", "function": {
        "name": "password_gen",
        "description": "生成随机密码。",
        "parameters": {"type": "object", "properties": {
            "length": {"type": "integer", "description": "长度，默认 20。"},
            "count": {"type": "integer", "description": "生成个数，默认 1。"},
            "charset": {"type": "string",
                        "enum": ["mixed", "letters", "digits", "alnum"]},
            "symbols": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "jwt_decode",
        "description": "解码 JWT 的 header 和 payload（不验证签名）。",
        "parameters": {"type": "object", "properties": {
            "token": {"type": "string"},
        }, "required": ["token"]},
    }},
    {"type": "function", "function": {
        "name": "random_bytes",
        "description": "生成安全随机数（hex/base64/url/uuid）。",
        "parameters": {"type": "object", "properties": {
            "length": {"type": "integer", "description": "字节数，默认 32。"},
            "fmt": {"type": "string",
                    "enum": ["hex", "base64", "url", "uuid"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "hash_data",
        "description": "哈希文本或文件（支持 HMAC）。",
        "parameters": {"type": "object", "properties": {
            "data": {"type": "string"}, "file": {"type": "string"},
            "algorithm": {"type": "string",
                          "enum": ["md5", "sha1", "sha256", "sha512",
                                   "blake2b", "blake2s"]},
            "hmac_key": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "symmetric_encrypt",
        "description": "AES-256-GCM 加密。key 或 password 二选一。",
        "parameters": {"type": "object", "properties": {
            "plaintext": {"type": "string"}, "file": {"type": "string"},
            "key": {"type": "string"},
            "password": {"type": "string"},
            "out": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "symmetric_decrypt",
        "description": "AES-256-GCM 解密。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "key": {"type": "string"},
            "password": {"type": "string"}, "out": {"type": "string"},
        }, "required": ["file"]},
    }},
    {"type": "function", "function": {
        "name": "rsa_generate_keypair",
        "description": "生成 RSA 密钥对（2048/3072/4096）。写操作。",
        "parameters": {"type": "object", "properties": {
            "bits": {"type": "integer", "enum": [2048, 3072, 4096]},
            "out_dir": {"type": "string"},
            "name": {"type": "string"},
            "password": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "rsa_encrypt",
        "description": "用 RSA 公钥加密小数据。",
        "parameters": {"type": "object", "properties": {
            "plaintext": {"type": "string"}, "file": {"type": "string"},
            "pubkey": {"type": "string"}, "out": {"type": "string"},
        }, "required": ["pubkey"]},
    }},
    {"type": "function", "function": {
        "name": "rsa_decrypt",
        "description": "用 RSA 私钥解密。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "privkey": {"type": "string"},
            "password": {"type": "string"}, "out": {"type": "string"},
        }, "required": ["file", "privkey"]},
    }},

    # ==================== 时间 ====================
    {"type": "function", "function": {
        "name": "now_info",
        "description": "获取当前时间信息（本地/UTC/Unix 时间戳）。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "date_calc",
        "description": "日期计算。offset 支持 +1d/-3w/+2h/+30M。"
                       "单位 s/M/h/d/w/m/y。",
        "parameters": {"type": "object", "properties": {
            "base": {"type": "string", "description": "基准时间（ISO），默认现在。"},
            "offset": {"type": "string", "description": "如 +1d。"},
            "format": {"type": "string"},
        }, "required": ["offset"]},
    }},
    {"type": "function", "function": {
        "name": "timezone_convert",
        "description": "时区转换。",
        "parameters": {"type": "object", "properties": {
            "time_str": {"type": "string"},
            "from_tz": {"type": "string"},
            "to_tz": {"type": "string"},
        }, "required": ["time_str", "from_tz", "to_tz"]},
    }},
    {"type": "function", "function": {
        "name": "cron_next",
        "description": "计算 cron 表达式下次执行时间。",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "5 段 cron。"},
            "count": {"type": "integer"},
        }, "required": ["expression"]},
    }},

    # ==================== 格式转换 ====================
    {"type": "function", "function": {
        "name": "json_format",
        "description": "JSON 美化/压缩。",
        "parameters": {"type": "object", "properties": {
            "data": {"type": "string"}, "file": {"type": "string"},
            "indent": {"type": "integer"}, "compact": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "json_diff",
        "description": "对比两个 JSON。",
        "parameters": {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "string"},
            "file_a": {"type": "string"}, "file_b": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "csv_to_json",
        "description": "CSV 转 JSON 数组。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "delimiter": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "json_to_csv",
        "description": "JSON 数组转 CSV。",
        "parameters": {"type": "object", "properties": {
            "data": {"type": "string"}, "file": {"type": "string"},
            "delimiter": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "md_to_html",
        "description": "Markdown 转 HTML。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
            "full": {"type": "boolean", "description": "完整 HTML 文档。"},
        }},
    }},
    {"type": "function", "function": {
        "name": "text_stats",
        "description": "统计文本：字符/行/单词/中文字符数等。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
        }},
    }},

    # ==================== 图片 ====================
    {"type": "function", "function": {
        "name": "image_info",
        "description": "图片元数据（格式、尺寸、色彩模式、DPI）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "image_process",
        "description": (
            "图像处理。op=info 只读；其他 op 会确认。\n"
            "  resize/thumbnail/crop/convert/rotate/flip/"
            "watermark/compress"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["info", "resize", "thumbnail", "crop",
                            "convert", "rotate", "flip", "watermark",
                            "compress"]},
            "path": {"type": "string"},
            "out": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "percent": {"type": "integer"},
            "quality": {"type": "integer"},
            "box": {"type": "array", "items": {"type": "integer"}},
            "angle": {"type": "number"},
            "flip": {"type": "string", "enum": ["h", "v"]},
            "text": {"type": "string"},
            "position": {"type": "string",
                         "enum": ["tl", "tr", "bl", "br", "center"]},
            "font_size": {"type": "integer"},
            "color": {"type": "string"},
            "to_format": {"type": "string"},
        }, "required": ["op", "path"]},
    }},
    {"type": "function", "function": {
        "name": "ocr_image",
        "description": "图片 OCR 文字识别。需 tesseract/paddleocr/easyocr。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "lang": {"type": "string"},
            "backend": {"type": "string",
                        "enum": ["tesseract", "paddleocr", "easyocr"]},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "ocr_status",
        "description": "检查 OCR 后端。",
        "parameters": {"type": "object", "properties": {}},
    }},    # ==================== 二维码 ====================
    {"type": "function", "function": {
        "name": "qrcode_generate",
        "description": "生成二维码图片（png/jpg/svg）。",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string", "description": "要编码的内容。"},
            "out": {"type": "string", "description": "输出路径。"},
            "size": {"type": "integer", "description": "每模块像素数，默认 10。"},
            "border": {"type": "integer", "description": "边框模块数，默认 4。"},
            "error_level": {"type": "string", "enum": ["L", "M", "Q", "H"]},
            "color": {"type": "string", "description": "前景色，如 #000000。"},
            "bg": {"type": "string", "description": "背景色，如 #ffffff。"},
        }, "required": ["content"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_decode",
        "description": "从图片中识别二维码/条形码（需 pyzbar）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_styled",
        "description": (
            "生成风格化二维码。\n"
            "style: square / rounded / circle / dots / gradient / art。\n"
            "支持 logo 嵌入、标题文字、任意前后景色。"
        ),
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"},
            "out": {"type": "string"},
            "style": {"type": "string",
                      "enum": ["square", "rounded", "circle", "dots",
                               "gradient", "art"]},
            "fg": {"type": "string"},
            "bg": {"type": "string"},
            "gradient_end": {"type": "string"},
            "logo": {"type": "string"},
            "logo_scale": {"type": "integer", "description": "10-35，默认 22。"},
            "size": {"type": "integer"},
            "border": {"type": "integer"},
            "error_level": {"type": "string", "enum": ["L", "M", "Q", "H"]},
            "caption": {"type": "string"},
            "caption_color": {"type": "string"},
            "module_radius": {"type": "number"},
        }, "required": ["content"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_batch",
        "description": "批量生成二维码（最多 200 个）。",
        "parameters": {"type": "object", "properties": {
            "items": {"type": "array",
                      "description": "字符串数组，或 [{content, name}]。",
                      "items": {}},
            "out_dir": {"type": "string"},
            "style": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "gradient_end": {"type": "string"},
            "size": {"type": "integer"},
            "error_level": {"type": "string",
                            "enum": ["L", "M", "Q", "H"]},
        }, "required": ["items"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_wifi",
        "description": "生成 Wi-Fi 连接二维码（扫码直接连网）。",
        "parameters": {"type": "object", "properties": {
            "ssid": {"type": "string"}, "password": {"type": "string"},
            "encryption": {"type": "string",
                           "enum": ["WPA", "WEP", "NOPASS"]},
            "hidden": {"type": "boolean"},
            "style": {"type": "string"}, "out": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "size": {"type": "integer"},
        }, "required": ["ssid"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_vcard",
        "description": "生成名片二维码（vCard 3.0）。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "phone": {"type": "string"},
            "email": {"type": "string"}, "org": {"type": "string"},
            "title": {"type": "string"}, "url": {"type": "string"},
            "address": {"type": "string"}, "note": {"type": "string"},
            "style": {"type": "string"}, "out": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "size": {"type": "integer"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_email",
        "description": "生成邮件二维码（扫码打开邮件草稿）。",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"}, "subject": {"type": "string"},
            "body": {"type": "string"},
            "style": {"type": "string"}, "out": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "size": {"type": "integer"},
        }, "required": ["to"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_sms",
        "description": "生成短信二维码（扫码打开短信）。",
        "parameters": {"type": "object", "properties": {
            "phone": {"type": "string"}, "message": {"type": "string"},
            "style": {"type": "string"}, "out": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "size": {"type": "integer"},
        }, "required": ["phone"]},
    }},
    {"type": "function", "function": {
        "name": "qrcode_geo",
        "description": "生成地理坐标二维码（扫码打开地图）。",
        "parameters": {"type": "object", "properties": {
            "lat": {"type": "number", "description": "纬度。"},
            "lng": {"type": "number", "description": "经度。"},
            "style": {"type": "string"}, "out": {"type": "string"},
            "fg": {"type": "string"}, "bg": {"type": "string"},
            "size": {"type": "integer"},
        }, "required": ["lat", "lng"]},
    }},

    # ==================== ANSI ====================
    {"type": "function", "function": {
        "name": "ansi_strip",
        "description": "去除文本或文件里的 ANSI 转义序列。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
            "keep_osc": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "ansi_scan",
        "description": "扫描文本/文件里的 ANSI 序列，统计类型和颜色。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
            "show_examples": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "ansi_to_html",
        "description": "把带 ANSI 颜色的文本转成 HTML。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "file": {"type": "string"},
            "dark_bg": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "ansi_palette",
        "description": "显示当前终端支持的 ANSI 调色板。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== 压缩 ====================
    {"type": "function", "function": {
        "name": "archive",
        "description": (
            "压缩包操作。支持 zip / tar.* / 7z / rar(只读) / "
            "单文件 gz/bz2/xz/zst/lz4/br。\n"
            "op=list 列内容 / info 查信息 / extract 解压 / create 打包。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["list", "info", "extract", "create"]},
            "archive": {"type": "string"},
            "dst": {"type": "string"},
            "srcs": {"type": "array", "items": {"type": "string"}},
            "compression": {"type": "string"},
            "overwrite": {"type": "boolean"},
        }, "required": ["op"]},
    }},

    # ==================== 视频 ====================
    {"type": "function", "function": {
        "name": "video_probe",
        "description": "查看视频/音频文件信息。需 ffmpeg。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_convert",
        "description": "视频格式转换/转码。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "fmt": {"type": "string"},
            "video_codec": {"type": "string"},
            "audio_codec": {"type": "string"},
            "crf": {"type": "integer"},
            "preset": {"type": "string"},
            "scale": {"type": "string"},
            "bitrate": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_clip",
        "description": "视频剪辑。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "start": {"type": "string"}, "duration": {"type": "string"},
            "end": {"type": "string"}, "reencode": {"type": "boolean"},
        }, "required": ["path", "start"]},
    }},
    {"type": "function", "function": {
        "name": "video_extract_audio",
        "description": "从视频提取音轨。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "fmt": {"type": "string",
                    "enum": ["mp3", "aac", "wav", "flac", "m4a"]},
            "bitrate": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_thumbnail",
        "description": "视频某一帧截图。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "time": {"type": "string"}, "width": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_to_gif",
        "description": "视频转 GIF。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "start": {"type": "string"}, "duration": {"type": "string"},
            "fps": {"type": "integer"}, "width": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_compress",
        "description": "压缩视频（H.264 + 缩放）。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "crf": {"type": "integer"},
            "preset": {"type": "string"},
            "target_height": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "video_merge",
        "description": "合并多个视频。写操作。",
        "parameters": {"type": "object", "properties": {
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"},
        }, "required": ["files"]},
    }},

    # ==================== 音频 ====================
    {"type": "function", "function": {
        "name": "audio_probe",
        "description": "查看音频文件信息。需 ffmpeg。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "audio_convert",
        "description": "音频格式转换。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "fmt": {"type": "string",
                    "enum": ["mp3", "aac", "m4a", "wav", "flac",
                             "ogg", "opus"]},
            "bitrate": {"type": "string"},
            "sample_rate": {"type": "integer"},
            "channels": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "audio_clip",
        "description": "音频剪辑。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "start": {"type": "string"}, "duration": {"type": "string"},
            "end": {"type": "string"},
        }, "required": ["path", "start"]},
    }},
    {"type": "function", "function": {
        "name": "audio_volume",
        "description": "调整音量/标准化。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "db": {"type": "number"}, "percent": {"type": "integer"},
            "normalize": {"type": "boolean"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "audio_concat",
        "description": "拼接多个音频。写操作。",
        "parameters": {"type": "object", "properties": {
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"},
        }, "required": ["files"]},
    }},

    # ==================== PDF 高级 ====================
    {"type": "function", "function": {
        "name": "pdf_watermark",
        "description": "PDF 加水印。写操作。需 pypdf + reportlab。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "text": {"type": "string"},
            "opacity": {"type": "number"},
            "font_size": {"type": "integer"},
            "angle": {"type": "integer"},
            "color": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "pdf_compress",
        "description": "压缩 PDF。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "quality": {"type": "string",
                        "enum": ["low", "medium", "high"]},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "pdf_extract_images",
        "description": "提取 PDF 内嵌图片。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out_dir": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "pdf_rotate",
        "description": "旋转 PDF 页。写操作。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "angle": {"type": "integer", "enum": [90, 180, 270]},
            "pages": {"type": "string"},
        }, "required": ["path", "angle"]},
    }},
    {"type": "function", "function": {
        "name": "pdf_add_page_numbers",
        "description": "给 PDF 加页码。写操作。需 reportlab。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "out": {"type": "string"},
            "position": {"type": "string",
                         "enum": ["top-left", "top-center", "top-right",
                                  "bottom-left", "bottom-center",
                                  "bottom-right"]},
            "fmt": {"type": "string"},
            "font_size": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "pdf_metadata",
        "description": "读写 PDF 元数据。op=get 只读。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "op": {"type": "string", "enum": ["get", "set"]},
            "out": {"type": "string"},
            "title": {"type": "string"}, "author": {"type": "string"},
            "subject": {"type": "string"},
            "keywords": {"type": "string"},
        }, "required": ["path"]},
    }},

    # ==================== Office ====================
    {"type": "function", "function": {
        "name": "docx",
        "description": (
            "Word 文档操作。op：read/info/extract_images 只读；"
            "edit/merge/encrypt/print 需确认。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["read", "info", "extract_images", "edit",
                            "merge", "encrypt", "print"]},
            "path": {"type": "string"},
            "find": {"type": "string"}, "replace": {"type": "string"},
            "append": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"}, "out_dir": {"type": "string"},
            "password": {"type": "string"}, "printer": {"type": "string"},
        }, "required": ["op"]},
    }},
    {"type": "function", "function": {
        "name": "pdf",
        "description": (
            "PDF 文档操作。op：read/info/extract_pages_list/"
            "extract_images 只读；merge/split/encrypt/decrypt/"
            "print/ocr 需确认。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["read", "info", "extract_pages_list",
                            "extract_images", "merge", "split",
                            "encrypt", "decrypt", "print", "ocr"]},
            "path": {"type": "string"},
            "start_page": {"type": "integer"},
            "end_page": {"type": "integer"},
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"}, "out_dir": {"type": "string"},
            "pages": {"type": "string"},
            "password": {"type": "string"}, "lang": {"type": "string"},
            "printer": {"type": "string"},
        }, "required": ["op"]},
    }},
    {"type": "function", "function": {
        "name": "pptx",
        "description": (
            "PowerPoint 操作。op：read/extract_content/info 只读；"
            "edit/merge/encrypt/print 需确认。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["read", "extract_content", "info", "edit",
                            "merge", "encrypt", "print"]},
            "path": {"type": "string"},
            "find": {"type": "string"}, "replace": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"},
            "password": {"type": "string"}, "printer": {"type": "string"},
        }, "required": ["op"]},
    }},
    {"type": "function", "function": {
        "name": "excel",
        "description": (
            "Excel 操作。op：read/info/worksheets/list_sheets/"
            "formulas 只读；edit/merge/encrypt/print 需确认。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["read", "info", "worksheets",
                            "list_sheets", "formulas", "edit",
                            "merge", "encrypt", "print"]},
            "path": {"type": "string"}, "sheet": {"type": "string"},
            "cell": {"type": "string"}, "value": {},
            "max_rows": {"type": "integer"},
            "max_cols": {"type": "integer"},
            "files": {"type": "array", "items": {"type": "string"}},
            "out": {"type": "string"},
            "password": {"type": "string"}, "printer": {"type": "string"},
        }, "required": ["op"]},
    }},    # ==================== 系统操作 sysop ====================
    {"type": "function", "function": {
        "name": "sysop",
        "description": (
            "操作系统级控制。op：\n"
            "  音量：volume_get / volume_set / volume_mute / volume_unmute\n"
            "  亮度：brightness_get / brightness_set\n"
            "  主题：theme_get / theme_set\n"
            "  WLAN：wifi_status / wifi_list / wifi_connect / wifi_disconnect\n"
            "  蓝牙：bt_status / bt_list / bt_on / bt_off\n"
            "  打印：printer_list / printer_default / printer_print\n"
            "  电源：power / power_battery / power_plan_list / power_plan_set\n"
            "  服务：services_list / services_status / services_action\n"
            "        process_kill / process_priority\n"
            "  时区：timezone_get / timezone_set / time_sync / time_sync_force\n"
            "  通知：notify\n"
            "  网络：hosts_show / proxy_get / proxy_set\n"
            "        dns_get / dns_set / dns_reset / dns_flush\n"
            "        firewall_status / firewall_rule_list / firewall_toggle\n"
            "        firewall_port_allow / firewall_port_deny / firewall_port_check\n"
            "        system_proxy_get / system_proxy_set / system_proxy_clear\n"
            "  其它：monitors_list / temperature / clipboard_history_check\n"
            "        check_update\n"
            "只读 op 直接执行；写 op 会先确认。"
        ),
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string", "enum": [
                "volume_get", "volume_set", "volume_mute", "volume_unmute",
                "brightness_get", "brightness_set",
                "theme_get", "theme_set",
                "wifi_status", "wifi_list", "wifi_connect",
                "wifi_disconnect",
                "bt_status", "bt_list", "bt_on", "bt_off",
                "printer_list", "printer_default", "printer_print",
                "power", "power_battery", "power_plan_list",
                "power_plan_set",
                "services_list", "services_status", "services_action",
                "process_kill", "process_priority",
                "timezone_get", "timezone_set", "time_sync",
                "time_sync_force",
                "notify",
                "hosts_show", "proxy_get", "proxy_set",
                "dns_get", "dns_set", "dns_reset", "dns_flush",
                "firewall_status", "firewall_rule_list",
                "firewall_toggle", "firewall_port_allow",
                "firewall_port_deny", "firewall_port_check",
                "system_proxy_get", "system_proxy_set",
                "system_proxy_clear",
                "monitors_list", "temperature",
                "clipboard_history_check", "check_update",
            ]},
            "value": {"type": "integer"},
            "action": {"type": "string"},
            "delay": {"type": "integer"},
            "plan": {"type": "string"},
            "theme": {"type": "string", "enum": ["dark", "light"]},
            "ssid": {"type": "string"},
            "password": {"type": "string"},
            "path": {"type": "string"},
            "printer": {"type": "string"},
            "chain": {"type": "string"},
            "protocol": {"type": "string", "enum": ["tcp", "udp"]},
            "port": {"type": "integer"},
            "servers": {"type": "array", "items": {"type": "string"}},
            "interface": {"type": "string"},
            "bypass": {"type": "string"},
            "filter": {"type": "string"},
            "limit": {"type": "integer"},
            "pid": {"type": "integer"},
            "force": {"type": "boolean"},
            "nice": {"type": "integer"},
            "tz": {"type": "string"},
            "url": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "timeout": {"type": "integer"},
        }, "required": ["op"]},
    }},

    # ==================== LSP ====================
    {"type": "function", "function": {
        "name": "lsp_hover",
        "description": "查看某个位置的类型/文档信息（悬停）。"
                       "line/column 从 1 开始。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "line": {"type": "integer"},
            "column": {"type": "integer"},
        }, "required": ["path", "line", "column"]},
    }},
    {"type": "function", "function": {
        "name": "lsp_definition",
        "description": "跳转到符号定义位置。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "line": {"type": "integer"},
            "column": {"type": "integer"},
        }, "required": ["path", "line", "column"]},
    }},
    {"type": "function", "function": {
        "name": "lsp_references",
        "description": "查找符号的所有引用。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "line": {"type": "integer"},
            "column": {"type": "integer"},
            "include_declaration": {"type": "boolean"},
        }, "required": ["path", "line", "column"]},
    }},
    {"type": "function", "function": {
        "name": "lsp_diagnostics",
        "description": "获取文件的编译/类型/lint 诊断。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "lsp_symbols",
        "description": "列出文件的符号（类/函数/方法/变量），带行号。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "lsp_status",
        "description": "查看已配置的 LSP 服务器状态。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== Computer Use ====================
    {"type": "function", "function": {
        "name": "screen_capture",
        "description": "截取屏幕。返回截图尺寸和文件路径。",
        "parameters": {"type": "object", "properties": {
            "region": {"type": "array", "items": {"type": "integer"},
                       "description": "[left, top, width, height]。"},
            "save_to": {"type": "string"},
            "return_base64": {"type": "boolean"},
            "max_width": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "screen_info",
        "description": "屏幕尺寸、光标位置、显示器数、活动窗口。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "mouse_action",
        "description": "鼠标操作。action：move/click/right_click/"
                       "double_click/drag/scroll。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["move", "click", "right_click",
                                "double_click", "drag", "scroll"]},
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "x1": {"type": "integer"}, "y1": {"type": "integer"},
            "x2": {"type": "integer"}, "y2": {"type": "integer"},
            "button": {"type": "string",
                       "enum": ["left", "right", "middle"]},
            "clicks": {"type": "integer"},
            "amount": {"type": "integer"},
            "duration": {"type": "number"},
        }, "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "keyboard_action",
        "description": "键盘操作。action：type/press/hotkey。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["type", "press", "hotkey"]},
            "text": {"type": "string"},
            "key": {"type": "string"},
            "keys": {"type": "array", "items": {"type": "string"}},
            "interval": {"type": "number"},
        }, "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "window_action",
        "description": "窗口管理。action：list/activate/minimize/maximize。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["list", "activate", "minimize",
                                "maximize"]},
            "title": {"type": "string"},
        }, "required": ["action"]},
    }},

    # ==================== Sub agent ====================
    {"type": "function", "function": {
        "name": "spawn_agent",
        "description": (
            "派生子 agent 在独立上下文里完成探索/分析任务。\n"
            "子 agent 只有只读工具，返回精炼结果。\n"
            "mode：explore（默认）/ code / plan。"
        ),
        "parameters": {"type": "object", "properties": {
            "task": {"type": "string"},
            "mode": {"type": "string",
                     "enum": ["explore", "code", "plan"]},
            "max_steps": {"type": "integer", "description": "默认 6，上限 20。"},
            "timeout": {"type": "integer", "description": "默认 300。"},
        }, "required": ["task"]},
    }},
    {"type": "function", "function": {
        "name": "multi_review",
        "description": "对单个文件派 3 个 sub-agent 并行审查"
                       "（安全 / 性能 / 可读性）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "dimensions": {"type": "array", "items": {"type": "string"}},
            "max_steps": {"type": "integer"},
            "timeout": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": (
            "向用户提问并等待回答。\n"
            "单问题：question / options / default。\n"
            "多问题：questions 数组一次问完。"
        ),
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "object"}},
            "options": {"type": "array", "items": {"type": "string"}},
            "default": {"type": "string"},
            "allow_custom": {"type": "boolean"},
            "timeout": {"type": "integer"},
            "header": {"type": "string"},
        }},
    }},

    # ==================== 记忆 ====================
    {"type": "function", "function": {
        "name": "memory_remember",
        "description": "记住一个跨会话的偏好或事实。"
                       "category: preference/context/profile/project/other。",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}, "value": {"type": "string"},
            "category": {"type": "string",
                         "enum": ["preference", "context", "profile",
                                  "project", "other"]},
            "tags": {"type": "array", "items": {"type": "string"}},
        }, "required": ["key", "value"]},
    }},
    {"type": "function", "function": {
        "name": "memory_recall",
        "description": "查找长期记忆。query 为空则列出全部。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "category": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "memory_forget",
        "description": "删除一条长期记忆（按 id 或 key）。",
        "parameters": {"type": "object", "properties": {
            "token": {"type": "string"},
        }, "required": ["token"]},
    }},
    {"type": "function", "function": {
        "name": "memory_list",
        "description": "统计长期记忆。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== 定时任务 ====================
    {"type": "function", "function": {
        "name": "cron_add",
        "description": "创建定时任务。cron 表达式：标准 5 段。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "schedule": {"type": "string"},
            "prompt": {"type": "string"},
        }, "required": ["name", "schedule", "prompt"]},
    }},
    {"type": "function", "function": {
        "name": "cron_list",
        "description": "列出所有定时任务。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "cron_remove",
        "description": "删除定时任务。",
        "parameters": {"type": "object", "properties": {
            "token": {"type": "string"},
        }, "required": ["token"]},
    }},
    {"type": "function", "function": {
        "name": "cron_enable",
        "description": "启用/禁用定时任务。",
        "parameters": {"type": "object", "properties": {
            "token": {"type": "string"},
            "enabled": {"type": "boolean"},
        }, "required": ["token"]},
    }},
    {"type": "function", "function": {
        "name": "cron_logs",
        "description": "查看定时任务的执行历史。",
        "parameters": {"type": "object", "properties": {
            "token": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["token"]},
    }},

    # ==================== 梦境 ====================
    {"type": "function", "function": {
        "name": "dream_run",
        "description": "「做梦」：回顾最近 N 天的会话，生成洞察、"
                       "记忆候选和明日建议。",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer"},
            "focus": {"type": "string"},
            "save_memories": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "dream_list",
        "description": "列出最近的梦境记录。",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "dream_read",
        "description": "读取某个梦境的完整内容。",
        "parameters": {"type": "object", "properties": {
            "dream_id": {"type": "string"},
        }, "required": ["dream_id"]},
    }},
    {"type": "function", "function": {
        "name": "dream_stats",
        "description": "梦境统计信息。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== 成本 ====================
    {"type": "function", "function": {
        "name": "cost_report",
        "description": "查看成本报告（今日/本周/本月/全部/图表）。",
        "parameters": {"type": "object", "properties": {
            "period": {"type": "string",
                       "enum": ["today", "week", "month", "all"]},
            "chart": {"type": "boolean"},
            "by_model": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "budget_status",
        "description": "查看当前预算状态。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "cost_anomaly",
        "description": "检测成本异常（突增）。"
                       "sensitivity: low(3σ) / medium(2σ) / high(1.5σ)。",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer"},
            "sensitivity": {"type": "string",
                            "enum": ["low", "medium", "high"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "cost_forecast",
        "description": "基于历史数据预测未来成本（线性回归）。",
        "parameters": {"type": "object", "properties": {
            "days_ahead": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "cost_export",
        "description": "导出成本明细为 CSV。写操作。",
        "parameters": {"type": "object", "properties": {
            "detail": {"type": "string",
                       "enum": ["turn", "daily", "model", "session"]},
            "period": {"type": "string",
                       "enum": ["today", "week", "month", "all"]},
            "path": {"type": "string"},
        }},
    }},

    # ==================== 通知 ====================
    {"type": "function", "function": {
        "name": "notify",
        "description": "发送桌面系统通知。level: info/warn/error/success/ask。",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"},
            "level": {"type": "string",
                      "enum": ["info", "warn", "error",
                               "success", "done", "ask"]},
            "sound": {"type": "boolean"},
            "timeout": {"type": "integer"},
        }, "required": ["title"]},
    }},
    {"type": "function", "function": {
        "name": "notify_check",
        "description": "检查当前平台的通知支持情况。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "notify_actions",
        "description": "发送带按钮和图片的桌面通知"
                       "（Windows/macOS 支持按钮）。",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "object"}},
            "image_path": {"type": "string"},
            "level": {"type": "string"},
            "sound": {"type": "boolean"},
            "timeout": {"type": "integer"},
        }, "required": ["title"]},
    }},

    # ==================== 应用管理 ====================
    {"type": "function", "function": {
        "name": "open_app",
        "description": "打开应用、文件或 URL。",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
        }, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "list_apps",
        "description": "列出已安装的应用。",
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "string"},
            "limit": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "find_app",
        "description": "按名字模糊搜索已安装应用。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "max_results": {"type": "integer"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "pkg_manager_info",
        "description": "显示当前系统的包管理器。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "pkg_search",
        "description": "搜索可安装的包。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "source": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "pkg_list_installed",
        "description": "列出已安装的包。",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "pkg_install",
        "description": "安装包（写操作）。",
        "parameters": {"type": "object", "properties": {
            "package": {"type": "string"}, "source": {"type": "string"},
        }, "required": ["package"]},
    }},
    {"type": "function", "function": {
        "name": "pkg_uninstall",
        "description": "卸载包（写操作）。",
        "parameters": {"type": "object", "properties": {
            "package": {"type": "string"}, "source": {"type": "string"},
        }, "required": ["package"]},
    }},

    # ==================== 下载 ====================
    {"type": "function", "function": {
        "name": "download",
        "description": (
            "多线程智能下载文件。\n"
            "特性：HTTP Range 分块并行、断点续传、"
            "服务端不支持时降级单线程。"
        ),
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
            "out": {"type": "string"},
            "threads": {"type": "integer", "description": "0=自动。"},
            "timeout": {"type": "integer"},
            "resume": {"type": "boolean"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "download_info",
        "description": "查看 URL 的文件信息（不下载）。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},

    # ==================== 网络探测 ====================
    {"type": "function", "function": {
        "name": "ping_host",
        "description": "ping 主机。",
        "parameters": {"type": "object", "properties": {
            "host": {"type": "string"},
            "count": {"type": "integer"},
        }, "required": ["host"]},
    }},
    {"type": "function", "function": {
        "name": "port_scan",
        "description": "扫描主机端口。ports 可用 'common' / '1-1024' / "
                       "'80,443,8080' / '8000-8100'。",
        "parameters": {"type": "object", "properties": {
            "host": {"type": "string"},
            "ports": {"type": "string"},
            "timeout": {"type": "number"},
            "workers": {"type": "integer"},
        }, "required": ["host"]},
    }},
    {"type": "function", "function": {
        "name": "traceroute",
        "description": "路由跟踪。",
        "parameters": {"type": "object", "properties": {
            "host": {"type": "string"}, "max_hops": {"type": "integer"},
        }, "required": ["host"]},
    }},
    {"type": "function", "function": {
        "name": "get_public_ip",
        "description": "查询本机公网出口 IP。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "dns_lookup",
        "description": "DNS 查询（A/AAAA/MX/TXT/NS/CNAME）。",
        "parameters": {"type": "object", "properties": {
            "host": {"type": "string"},
            "record_type": {"type": "string",
                            "enum": ["A", "AAAA", "MX", "TXT",
                                     "NS", "CNAME"]},
        }, "required": ["host"]},
    }},
    {"type": "function", "function": {
        "name": "ssl_check",
        "description": "检查 HTTPS 站点的 SSL 证书信息。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}, "port": {"type": "integer"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "http_head",
        "description": "发送 HTTP HEAD 请求查看响应头。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}, "timeout": {"type": "integer"},
        }, "required": ["url"]},
    }},

    # ==================== 天气 ====================
    {"type": "function", "function": {
        "name": "weather",
        "description": (
            "查询全球天气（wttr.in）。\n"
            "默认返回原生 ASCII 艺术天气图，包含详细天气。"
            "format='full' 或 '' 用原生大图（推荐）；"
            "'3' 一行简版；'j1' JSON。"
            "中文用 lang=zh。"
        ),
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string"},
            "format": {"type": "string"},
            "lang": {"type": "string"},
        }, "required": ["location"]},
    }},

    # ==================== 定位 ====================
    {"type": "function", "function": {
        "name": "locate_rough",
        "description": "网络定位粗查（通过 IP）。"
                       "返回国家/省/市/坐标等。"
                       "使用后应询问用户是否提供更精确的位置。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "locate_set_exact",
        "description": "保存用户提供的精确位置（需要用户明确同意）。"
                       "仅在本会话有效。",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string"},
            "consent": {"type": "boolean"},
        }, "required": ["location", "consent"]},
    }},
    {"type": "function", "function": {
        "name": "locate_current",
        "description": "获取当前已保存的位置（粗查或精确）。",
        "parameters": {"type": "object", "properties": {}},
    }},

    # ==================== 高德地图 ====================
    {"type": "function", "function": {
        "name": "amap_geocode",
        "description": "地理编码：地址 → 经纬度坐标。",
        "parameters": {"type": "object", "properties": {
            "address": {"type": "string"}, "city": {"type": "string"},
        }, "required": ["address"]},
    }},
    {"type": "function", "function": {
        "name": "amap_regeocode",
        "description": "逆地理编码：经纬度 → 地址。",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string"},
            "radius": {"type": "integer"},
            "extensions": {"type": "string", "enum": ["base", "all"]},
        }, "required": ["location"]},
    }},
    {"type": "function", "function": {
        "name": "amap_search_poi",
        "description": "POI 搜索（关键词 + 城市/类型）。",
        "parameters": {"type": "object", "properties": {
            "keywords": {"type": "string"}, "city": {"type": "string"},
            "types": {"type": "string"},
            "location": {"type": "string"},
            "radius": {"type": "integer"},
            "page": {"type": "integer"},
            "offset": {"type": "integer"},
            "extensions": {"type": "string", "enum": ["base", "all"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "amap_poi_detail",
        "description": "根据 POI ID 获取详细评分、营业时间、图片。",
        "parameters": {"type": "object", "properties": {
            "poi_id": {"type": "string"},
            "extensions": {"type": "string", "enum": ["base", "all"]},
        }, "required": ["poi_id"]},
    }},
    {"type": "function", "function": {
        "name": "amap_around",
        "description": "周边搜索：给定坐标，找附近 POI。",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string"},
            "keywords": {"type": "string"}, "types": {"type": "string"},
            "radius": {"type": "integer"},
            "offset": {"type": "integer"},
        }, "required": ["location"]},
    }},
    {"type": "function", "function": {
        "name": "amap_input_tips",
        "description": "输入提示/自动补全。",
        "parameters": {"type": "object", "properties": {
            "keywords": {"type": "string"}, "city": {"type": "string"},
        }, "required": ["keywords"]},
    }},
    {"type": "function", "function": {
        "name": "amap_weather",
        "description": "高德天气。",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string"},
            "extensions": {"type": "string", "enum": ["base", "all"]},
        }, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "amap_driving",
        "description": "驾车路径规划。",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "strategy": {"type": "integer"},
        }, "required": ["origin", "destination"]},
    }},
    {"type": "function", "function": {
        "name": "amap_walking",
        "description": "步行路径规划。",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
        }, "required": ["origin", "destination"]},
    }},
    {"type": "function", "function": {
        "name": "amap_bicycling",
        "description": "骑行路径规划。",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
        }, "required": ["origin", "destination"]},
    }},
    {"type": "function", "function": {
        "name": "amap_transit",
        "description": "公交路径规划。",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "city": {"type": "string"}, "cityd": {"type": "string"},
            "strategy": {"type": "integer"},
        }, "required": ["origin", "destination", "city"]},
    }},
    {"type": "function", "function": {
        "name": "amap_distance",
        "description": "两点距离测量。type: 0 直线，1 驾车，3 步行。",
        "parameters": {"type": "object", "properties": {
            "origins": {"type": "string"},
            "destination": {"type": "string"},
            "type_": {"type": "integer"},
        }, "required": ["origins", "destination"]},
    }},
    {"type": "function", "function": {
        "name": "amap_ip_location",
        "description": "IP 定位：根据 IP 获取所在省市。",
        "parameters": {"type": "object", "properties": {
            "ip": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "amap_district",
        "description": "行政区划查询。",
        "parameters": {"type": "object", "properties": {
            "keywords": {"type": "string"},
            "subdistrict": {"type": "integer"},
            "extensions": {"type": "string", "enum": ["base", "all"]},
        }},
    }},

    # ==================== 邮件 ====================
    {"type": "function", "function": {
        "name": "email_accounts",
        "description": "列出已配置的邮箱账号及连接状态。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "email_list_folders",
        "description": "IMAP：列出邮箱所有文件夹。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "email_list_messages",
        "description": "IMAP：列出指定文件夹最近邮件。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"},
            "folder": {"type": "string"},
            "count": {"type": "integer"},
            "unread_only": {"type": "boolean"},
            "since": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "email_search",
        "description": "IMAP：按条件搜索邮件。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"},
            "folder": {"type": "string"},
            "from_": {"type": "string"}, "to": {"type": "string"},
            "subject": {"type": "string"}, "body": {"type": "string"},
            "since": {"type": "string"}, "before": {"type": "string"},
            "unseen_only": {"type": "boolean"},
            "count": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "email_read",
        "description": "IMAP：读取指定 UID 的邮件全文。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"},
            "mark_seen": {"type": "boolean"},
            "include_html": {"type": "boolean"},
        }, "required": ["uid"]},
    }},
    {"type": "function", "function": {
        "name": "email_list_attachments",
        "description": "IMAP：列出指定邮件的附件。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"},
        }, "required": ["uid"]},
    }},
    {"type": "function", "function": {
        "name": "email_download_attachment",
        "description": "IMAP：下载邮件附件到工作目录（写操作）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"}, "index": {"type": "integer"},
            "save_to": {"type": "string"},
        }, "required": ["uid"]},
    }},
    {"type": "function", "function": {
        "name": "email_pop_list",
        "description": "POP3：列出邮件。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "count": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "email_pop_read",
        "description": "POP3：读取指定序号的邮件全文。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "index": {"type": "integer"},
            "delete_after": {"type": "boolean"},
        }, "required": ["index"]},
    }},
    {"type": "function", "function": {
        "name": "email_send",
        "description": "SMTP：发送邮件，支持附件（写操作）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "to": {"type": "string"},
            "subject": {"type": "string"}, "body": {"type": "string"},
            "cc": {"type": "string"}, "bcc": {"type": "string"},
            "html": {"type": "boolean"},
            "attachments": {"type": "array",
                            "items": {"type": "string"}},
        }, "required": ["to", "subject", "body"]},
    }},
    {"type": "function", "function": {
        "name": "email_reply",
        "description": "回复某封邮件（写操作）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"}, "body": {"type": "string"},
            "reply_all": {"type": "boolean"},
            "attachments": {"type": "array",
                            "items": {"type": "string"}},
        }, "required": ["uid", "body"]},
    }},
    {"type": "function", "function": {
        "name": "email_mark",
        "description": "IMAP：标记邮件状态（写操作）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"},
            "action": {"type": "string",
                       "enum": ["seen", "unseen", "flagged",
                                "unflagged", "answered"]},
        }, "required": ["uid", "action"]},
    }},
    {"type": "function", "function": {
        "name": "email_move",
        "description": "IMAP：移动邮件到另一文件夹（写操作）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"}, "dest": {"type": "string"},
        }, "required": ["uid", "dest"]},
    }},
    {"type": "function", "function": {
        "name": "email_delete",
        "description": "IMAP：删除邮件（写操作，不可撤销）。",
        "parameters": {"type": "object", "properties": {
            "account": {"type": "string"}, "folder": {"type": "string"},
            "uid": {"type": "string"},
        }, "required": ["uid"]},
    }},

    # ==================== 微信 ====================
    {"type": "function", "function": {
        "name": "wechat_status",
        "description": "检查微信 PC 版窗口状态。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "wechat_send",
        "description": "发送微信消息（Windows UI 自动化，写操作）。",
        "parameters": {"type": "object", "properties": {
            "contact": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["contact", "message"]},
    }},
    {"type": "function", "function": {
        "name": "wechat_read_recent",
        "description": "读取与某联系人的最近消息（截图 + OCR）。",
        "parameters": {"type": "object", "properties": {
            "contact": {"type": "string"}, "count": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "wechat_moments_read",
        "description": "读取朋友圈（需手动打开朋友圈窗口）。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "wechat_moments_post",
        "description": "发朋友圈（半自动，写操作）。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "images": {"type": "array", "items": {"type": "string"}},
        }, "required": ["text"]},
    }},

    # ==================== 代码质量 ====================
    {"type": "function", "function": {
        "name": "ruff_check",
        "description": "运行 ruff 检查 Python 代码。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "select": {"type": "string"},
            "ignore": {"type": "string"},
            "max_results": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "mypy_check",
        "description": "运行 mypy 类型检查。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "strict": {"type": "boolean"},
            "max_results": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "black_check",
        "description": "检查 Python 格式是否符合 black（不改文件）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "black_format",
        "description": "用 black 格式化（写操作）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "eslint_check",
        "description": "运行 eslint 检查 JS/TS 代码。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "max_results": {"type": "integer"},
        }},
    }},

    # ==================== Python AST ====================
    {"type": "function", "function": {
        "name": "py_outline",
        "description": "Python 文件结构：imports、类、函数、方法。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "py_imports",
        "description": "Python 文件的 imports，分标准库/第三方/本地。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "group": {"type": "boolean"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "py_find_def",
        "description": "在 Python 文件中查找符号定义。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "path": {"type": "string"},
        }, "required": ["name", "path"]},
    }},
    {"type": "function", "function": {
        "name": "py_unused_imports",
        "description": "检测 Python 文件中可能未使用的 import。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
        }, "required": ["path"]},
    }},

    # ==================== Docker Compose ====================
    {"type": "function", "function": {
        "name": "compose_status",
        "description": "查看 docker compose 容器状态。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_logs",
        "description": "查看 compose 服务日志。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "service": {"type": "string"},
            "tail": {"type": "integer"},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_config",
        "description": "查看 compose 解析后的最终配置。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_up",
        "description": "启动 compose 服务（写操作）。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "detach": {"type": "boolean"},
            "service": {"type": "string"}, "build": {"type": "boolean"},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_down",
        "description": "停止并删除 compose 服务（写操作）。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "volumes": {"type": "boolean"},
            "remove_images": {"type": "string",
                              "enum": ["", "local", "all"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_restart",
        "description": "重启 compose 服务（写操作）。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "service": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "compose_exec",
        "description": "在 compose 容器内执行命令（写操作）。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "service": {"type": "string"},
            "command": {"type": "string"},
        }, "required": ["service", "command"]},
    }},

    # ==================== Kubernetes ====================
    {"type": "function", "function": {
        "name": "k8s_get",
        "description": "kubectl get。",
        "parameters": {"type": "object", "properties": {
            "resource": {"type": "string"},
            "namespace": {"type": "string"},
            "all_namespaces": {"type": "boolean"},
            "output": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "k8s_describe",
        "description": "kubectl describe。",
        "parameters": {"type": "object", "properties": {
            "resource": {"type": "string"}, "name": {"type": "string"},
            "namespace": {"type": "string"},
        }, "required": ["resource"]},
    }},
    {"type": "function", "function": {
        "name": "k8s_logs",
        "description": "查看 pod 日志。",
        "parameters": {"type": "object", "properties": {
            "pod": {"type": "string"}, "namespace": {"type": "string"},
            "container": {"type": "string"},
            "tail": {"type": "integer"},
            "previous": {"type": "boolean"},
        }, "required": ["pod"]},
    }},
    {"type": "function", "function": {
        "name": "k8s_contexts",
        "description": "列出 kubeconfig 上下文。",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "k8s_apply",
        "description": "kubectl apply（写操作）。",
        "parameters": {"type": "object", "properties": {
            "file": {"type": "string"}, "manifest": {"type": "string"},
            "namespace": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "k8s_delete",
        "description": "kubectl delete（写操作）。",
        "parameters": {"type": "object", "properties": {
            "resource": {"type": "string"}, "name": {"type": "string"},
            "namespace": {"type": "string"}, "file": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "k8s_scale",
        "description": "kubectl scale（写操作）。",
        "parameters": {"type": "object", "properties": {
            "resource": {"type": "string"}, "name": {"type": "string"},
            "replicas": {"type": "integer"},
            "namespace": {"type": "string"},
        }, "required": ["name", "replicas"]},
    }},
    {"type": "function", "function": {
        "name": "k8s_exec",
        "description": "kubectl exec（写操作）。",
        "parameters": {"type": "object", "properties": {
            "pod": {"type": "string"}, "command": {"type": "string"},
            "namespace": {"type": "string"},
            "container": {"type": "string"},
        }, "required": ["pod", "command"]},
    }},
    {"type": "function", "function": {
        "name": "k8s_top",
        "description": "kubectl top（需 metrics-server）。",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["pods", "nodes"]},
            "namespace": {"type": "string"},
            "all_namespaces": {"type": "boolean"},
        }},
    }},

    # ==================== 会话/状态 ====================
    {"type": "function", "function": {
        "name": "todo",
        "description": "会话内任务清单。",
        "parameters": {"type": "object", "properties": {
            "op": {"type": "string",
                   "enum": ["add", "list", "update", "done",
                            "undone", "remove", "clear"]},
            "id": {"type": "integer"}, "text": {"type": "string"},
        }, "required": ["op"]},
    }},
]


# ═══════════════════════════════════════════════════════════════════════ #
# 工具集合常量
# ═══════════════════════════════════════════════════════════════════════ #

READONLY_TOOL_NAMES = {
    # 文件读
    "read_file", "list_files", "search_in_files", "file_info",
    "glob", "grep_regex",
    # 网络
    "web_fetch", "http_request", "web_search", "web_research",
    "download_info", "ping_host", "port_scan", "traceroute",
    "get_public_ip", "dns_lookup", "ssl_check", "http_head",
    # 数据
    "json_query", "csv_query", "sqlite",
    "json_schema_validate", "sqlite_tables", "sqlite_schema",
    "postgres_query", "postgres_list_tables", "postgres_describe",
    "mysql_query", "mysql_list_tables", "mysql_describe",
    "mongo_list_databases", "mongo_list_collections",
    "mongo_find", "mongo_aggregate", "mongo_stats",
    # 系统
    "env_info", "process_info", "calculate", "system_metrics",
    "diff_files", "pip_list", "pip_show", "disk_tree",
    # 文本
    "regex_extract", "code_stats", "markdown_toc", "template_render",
    "word_frequency", "tokenize", "simplify_chinese",
    "dedupe_lines", "text_similarity", "strip_invisible",
    # 文件工具
    "hash_file", "find_duplicates", "pdf_extract",
    # 编码
    "base64_codec", "hash_text", "url_codec", "password_gen",
    "jwt_decode", "random_bytes", "hash_data",
    # 时间
    "now_info", "date_calc", "timezone_convert", "cron_next",
    # 转换
    "json_format", "json_diff", "csv_to_json", "json_to_csv",
    "md_to_html", "text_stats",
    # 图片
    "image_info", "image_process",
    "ocr_image", "ocr_status",
    # 二维码
    "qrcode_decode",
    # ANSI
    "ansi_strip", "ansi_scan", "ansi_to_html", "ansi_palette",
    # 视频/音频 probe
    "video_probe", "audio_probe",
    # PDF 元数据（get）
    "pdf_metadata",
    # 系统操作（部分 op）
    "sysop",
    # LSP
    "lsp_hover", "lsp_definition", "lsp_references",
    "lsp_diagnostics", "lsp_symbols", "lsp_status",
    # Computer
    "screen_info",
    # Agent
    "spawn_agent", "multi_review", "ask_user",
    # 记忆
    "memory_recall", "memory_list",
    # 定时
    "cron_list", "cron_logs",
    # 梦境
    "dream_list", "dream_read", "dream_stats",
    # 成本
    "cost_report", "budget_status", "cost_anomaly", "cost_forecast",
    # 通知
    "notify_check",
    # 应用
    "list_apps", "find_app", "pkg_manager_info",
    "pkg_search", "pkg_list_installed",
    # 天气
    "weather",
    # 定位
    "locate_rough", "locate_current",
    # 高德
    "amap_geocode", "amap_regeocode",
    "amap_search_poi", "amap_poi_detail", "amap_around",
    "amap_input_tips", "amap_weather",
    "amap_driving", "amap_walking", "amap_bicycling",
    "amap_transit", "amap_distance",
    "amap_ip_location", "amap_district",
    # 邮件（只读）
    "email_accounts", "email_list_folders", "email_list_messages",
    "email_search", "email_read", "email_list_attachments",
    "email_pop_list", "email_pop_read",
    # 微信（只读）
    "wechat_status", "wechat_read_recent", "wechat_moments_read",
    # 代码质量
    "ruff_check", "mypy_check", "black_check", "eslint_check",
    # Python AST
    "py_outline", "py_imports", "py_find_def", "py_unused_imports",
    # Compose（只读）
    "compose_status", "compose_logs", "compose_config",
    # K8s（只读）
    "k8s_get", "k8s_describe", "k8s_logs", "k8s_contexts", "k8s_top",
}

CACHEABLE_TOOLS = {
    "read_file", "list_files", "file_info", "glob",
    "json_query", "env_info", "csv_query", "calculate",
    "hash_file", "markdown_toc",
    "lsp_hover", "lsp_definition", "lsp_references", "lsp_symbols",
    "hash_text", "hash_data", "random_bytes",
    "word_frequency", "tokenize", "simplify_chinese",
    "dedupe_lines", "text_similarity", "strip_invisible",
    "ansi_strip", "ansi_scan", "ansi_to_html",
    "py_outline", "py_imports", "py_find_def", "py_unused_imports",
    "dns_lookup", "ssl_check", "http_head",
    "pip_show", "disk_tree",
    "amap_geocode", "amap_regeocode",
    "amap_search_poi", "amap_poi_detail",
    "amap_around", "amap_input_tips", "amap_district",
}

WRITE_TOOLS = {
    "edit_file", "write_file", "apply_patch", "file_ops",
    "find_replace", "file_attrs",
    "bash", "bash_bg", "git", "docker",
    "python_exec", "black_format",
    "qrcode_generate", "qrcode_styled", "qrcode_batch",
    "qrcode_wifi", "qrcode_vcard", "qrcode_email",
    "qrcode_sms", "qrcode_geo",
    "symmetric_encrypt", "symmetric_decrypt",
    "rsa_generate_keypair", "rsa_encrypt", "rsa_decrypt",
    "image_process",
    "archive",
    "video_convert", "video_clip", "video_extract_audio",
    "video_thumbnail", "video_to_gif", "video_compress",
    "video_merge",
    "audio_convert", "audio_clip", "audio_volume", "audio_concat",
    "pdf_watermark", "pdf_compress", "pdf_extract_images",
    "pdf_rotate", "pdf_add_page_numbers", "pdf_metadata",
    "docx", "pdf", "pptx", "excel",
    "sysop",
    "screen_capture", "mouse_action", "keyboard_action",
    "window_action",
    "memory_remember", "memory_forget",
    "cron_add", "cron_remove", "cron_enable",
    "dream_run",
    "cost_export",
    "notify", "notify_actions",
    "open_app", "pkg_install", "pkg_uninstall",
    "download",
    "locate_set_exact",
    "email_download_attachment", "email_send", "email_reply",
    "email_mark", "email_move", "email_delete",
    "wechat_send", "wechat_moments_post",
    "compose_up", "compose_down", "compose_restart",
    "compose_exec",
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec",
    "todo",
}


TOOLS_READONLY = [
    t for t in TOOLS
    if t["function"]["name"] in READONLY_TOOL_NAMES
]