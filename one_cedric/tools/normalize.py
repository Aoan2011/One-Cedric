"""工具调用参数归一化：容忍本地模型的常见错误。"""
from __future__ import annotations

import json
import re


TOOL_ALIASES: dict = {
    "readfile": "read_file", "read": "read_file", "cat": "read_file",
    "view": "read_file", "open_file": "read_file",
    "read_text": "read_file", "get_file_content": "read_file",
    "listfile": "list_files", "ls": "list_files",
    "listdir": "list_files", "list_directory": "list_files",
    "listfiles": "list_files", "list": "list_files",
    "dir": "list_files",
    "search": "search_in_files", "grep": "search_in_files",
    "search_files": "search_in_files",
    "find_in_files": "search_in_files",
    "searchinfiles": "search_in_files",
    "search_file": "search_in_files",
    "search_content": "search_in_files",
    "grep_regexp": "grep_regex", "regex_search": "grep_regex",
    "regexgrep": "grep_regex", "grep_pattern": "grep_regex",
    "info": "file_info", "stat": "file_info",
    "fileinfo": "file_info", "file_stat": "file_info",
    "find_files": "glob", "glob_files": "glob", "find": "glob",
    "list_by_pattern": "glob",
    "edit": "edit_file", "editfile": "edit_file",
    "replace": "edit_file", "modify_file": "edit_file",
    "patch_file": "edit_file",
    "replace_in_file": "edit_file", "update_file": "edit_file",
    "write": "write_file", "writefile": "write_file",
    "create_file": "write_file", "save_file": "write_file",
    "new_file": "write_file",
    "patch": "apply_patch", "applypatch": "apply_patch",
    "apply_diff": "apply_patch",
    "copy": "file_ops", "move": "file_ops", "delete": "file_ops",
    "remove_file": "file_ops", "mkdir": "file_ops",
    "create_dir": "file_ops", "fs": "file_ops",
    "file_op": "file_ops",
    "shell": "bash", "run": "bash", "exec": "bash",
    "execute": "bash", "command": "bash", "run_command": "bash",
    "terminal": "bash", "bash_command": "bash", "sh": "bash",
    "background": "bash_bg", "run_bg": "bash_bg",
    "shell_bg": "bash_bg", "background_run": "bash_bg",
    "git_command": "git", "git_cmd": "git",
    "docker_command": "docker", "docker_cmd": "docker",
    "fetch": "web_fetch", "curl": "web_fetch",
    "get_url": "web_fetch", "webfetch": "web_fetch",
    "http_get": "web_fetch",
    "http": "http_request", "request": "http_request",
    "httprequest": "http_request",
    "search_web": "web_search", "google": "web_search",
    "websearch": "web_search", "search_internet": "web_search",
    "jsonquery": "json_query", "json_path": "json_query",
    "query_json": "json_query", "jq": "json_query",
    "csvquery": "csv_query", "query_csv": "csv_query",
    "read_csv": "csv_query",
    "query_sql": "sqlite", "sql": "sqlite",
    "query_db": "sqlite", "query": "sqlite",
    "environment": "env_info", "system_info": "env_info",
    "envinfo": "env_info", "sysinfo": "env_info",
    "ps": "process_info", "processes": "process_info",
    "top": "process_info", "processinfo": "process_info",
    "ports": "process_info",
    "calc": "calculate", "math": "calculate", "eval": "calculate",
    "calculator": "calculate",
    "clipboard_read": "clipboard", "clip": "clipboard",
    "paste": "clipboard",
    "diff": "diff_files", "compare": "diff_files",
    "compare_files": "diff_files",
    "zip": "archive", "unzip": "archive", "tar": "archive",
    "compress": "archive", "extract": "archive",
    "task": "todo", "tasks": "todo", "task_list": "todo",
    "todos": "todo",
    "word": "docx", "word_doc": "docx",
    "ppt": "pptx", "powerpoint": "pptx",
    "xlsx": "excel", "xls": "excel", "spreadsheet": "excel",
    "sys": "sysop", "system": "sysop", "os": "sysop",
}


COMMON_PARAM_ALIASES: dict = {
    "path": {"path", "file", "filepath", "file_path", "filename",
             "file_name", "target", "target_path", "p", "f"},
    "pattern": {"pattern", "query", "keyword", "search", "text",
                "regex", "q", "search_term", "term", "needle"},
    "content": {"content", "text", "data", "body", "new_content"},
    "old_string": {"old_string", "old", "old_text", "find", "search",
                   "old_content", "from_text", "before", "original"},
    "new_string": {"new_string", "new", "new_text", "replace",
                   "replacement", "new_content", "to_text", "after",
                   "replacement_text"},
    "command": {"command", "cmd", "shell", "script", "command_line",
                "cmdline", "cmd_str", "command_str"},
    "url": {"url", "uri", "endpoint", "link", "target_url", "address"},
    "file_pattern": {"file_pattern", "glob", "filetype", "file_type",
                     "filter", "include", "pattern_filter"},
    "start_line": {"start_line", "start", "from_line", "line_start",
                   "begin", "startline", "line_from"},
    "end_line": {"end_line", "end", "to_line", "line_end", "finish",
                 "endline", "line_to"},
    "recursive": {"recursive", "recurse", "recur", "deep", "r"},
    "op": {"op", "operation", "action", "mode", "kind"},
    "src": {"src", "source", "from", "source_path", "src_path",
            "input"},
    "dst": {"dst", "dest", "destination", "to", "target_path",
            "dst_path", "output"},
    "subcommand": {"subcommand", "sub", "cmd", "command", "sub_cmd",
                   "subcmd"},
    "args": {"args", "arguments", "params", "params_list", "argv",
             "extra_args"},
    "query": {"query", "sql", "statement"},
    "patch": {"patch", "diff", "patch_text", "diff_text"},
    "text": {"text", "content", "value", "data"},
}


def _param_alias_map(tool_name: str) -> dict:
    from .schema import TOOLS
    supported = set()
    for t in TOOLS:
        if t["function"]["name"] == tool_name:
            props = (t["function"].get("parameters", {})
                     .get("properties", {}))
            supported = set(props.keys())
            break
    if not supported:
        return {}
    alias_to_std: dict = {}
    for std, aliases in COMMON_PARAM_ALIASES.items():
        if std not in supported:
            continue
        for a in aliases:
            alias_to_std[a] = std
        alias_to_std[std] = std
    return alias_to_std


def repair_json(s: str) -> dict:
    if not s or not s.strip():
        return {}
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
        return {}
    except json.JSONDecodeError:
        pass
    if "'" in s and '"' not in s:
        try:
            return json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            pass
    fixed = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    for _ in range(5):
        opens = fixed.count("{") - fixed.count("}")
        brackets = fixed.count("[") - fixed.count("]")
        if opens <= 0 and brackets <= 0:
            break
        fixed += "]" * max(0, brackets) + "}" * max(0, opens)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            continue
    out: dict = {}
    for m in re.finditer(
        r'"?([A-Za-z_]\w*)"?\s*:\s*("([^"]*)"|\'([^\']*)\'|'
        r'[\d.]+|true|false|null)',
        s,
    ):
        k = m.group(1)
        v = (m.group(3) if m.group(3) is not None
             else (m.group(4) if m.group(4) is not None
                   else m.group(2)))
        if v in ("true", "false"):
            out[k] = (v == "true")
        elif v == "null":
            out[k] = None
        elif re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        elif re.fullmatch(r"-?\d+\.\d+", v):
            out[k] = float(v)
        else:
            out[k] = v
    return out


_INT_PARAMS = {"start_line", "end_line", "max_results", "max_rows",
               "max_bytes", "timeout", "timeout_seconds", "limit",
               "context"}
_BOOL_PARAMS = {"recursive", "replace_all", "case_insensitive",
                "allow_write", "raw", "overwrite"}
_LIST_PARAMS = {"args", "srcs", "columns", "params"}


def coerce_types(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if k in _INT_PARAMS and isinstance(v, str):
            try:
                out[k] = int(v)
                continue
            except ValueError:
                pass
        if k in _BOOL_PARAMS and isinstance(v, str):
            low = v.strip().lower()
            if low in ("true", "yes", "1", "on"):
                out[k] = True
                continue
            if low in ("false", "no", "0", "off"):
                out[k] = False
                continue
        if k in _LIST_PARAMS and isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        out[k] = parsed
                        continue
                except json.JSONDecodeError:
                    pass
        out[k] = v
    return out


def normalize_tool_name(name: str) -> str:
    if not name:
        return ""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    from .schema import TOOLS
    valid = {t["function"]["name"] for t in TOOLS}
    if key in valid:
        return key
    return TOOL_ALIASES.get(key, name)


def normalize_args(tool_name: str, raw_args: dict) -> dict:
    if not isinstance(raw_args, dict):
        return {}
    for wrapper in ("arguments", "args", "parameters", "params",
                    "input"):
        if (list(raw_args.keys()) == [wrapper]
                and isinstance(raw_args[wrapper], dict)):
            raw_args = raw_args[wrapper]
            break
    alias_map = _param_alias_map(tool_name)
    out: dict = {}
    for k, v in raw_args.items():
        key_low = k.strip().lower()
        std = alias_map.get(
            key_low,
            key_low if key_low in alias_map.values() else k,
        )
        if std in out and k not in alias_map:
            continue
        out[std] = v
    return coerce_types(out)


def prepare_tool_call(tc: dict) -> tuple:
    fn = tc.get("function") or {}
    raw_name = fn.get("name", "")
    name = normalize_tool_name(raw_name)
    raw_args_str = fn.get("arguments", "{}")
    if isinstance(raw_args_str, dict):
        args = raw_args_str
    else:
        args = repair_json(str(raw_args_str))
    args = normalize_args(name, args)
    err = ""
    if not name:
        err = "无法识别工具名。"
    return name, args, err