"""bash 命令三层策略。

Level 1 - whitelist：直接执行
Level 2 - known：已知安全，单次确认
Level 3 - unknown：任意命令，强警告 + 强制确认
Level 0 - blocked：永久拒绝
"""
from __future__ import annotations

import shlex

from ..config import (
    SHELL_WHITELIST,
    SHELL_KNOWN_COMMANDS,
    SHELL_BLACKLIST,
    SHELL_DANGEROUS_PATTERNS,
    SHELL_FORBIDDEN_TOKENS,
)


def _has_shell_meta(command: str) -> str:
    in_single = False
    in_double = False
    esc = False
    for i, c in enumerate(command):
        if esc:
            esc = False
            continue
        if c == "\\" and not in_single:
            esc = True
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            continue
        if in_single or in_double:
            continue
        for meta in SHELL_FORBIDDEN_TOKENS:
            if command[i:i + len(meta)] == meta:
                return meta
    return ""


def _parse_shell_command(command: str) -> tuple:
    if not command or not command.strip():
        return None, "ERROR: 命令为空。"
    meta = _has_shell_meta(command)
    if meta:
        return None, (
            f"ERROR: 命令不能包含 shell 操作符 '{meta}'"
            f"（引号外）。"
            f"如需要管道/重定向，请让用户手动执行。"
        )
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return None, f"ERROR: 命令解析失败: {exc}"
    if not argv:
        return None, "ERROR: 命令为空。"
    return argv, ""


def _match_whitelist(argv: list) -> bool:
    for prefix in SHELL_WHITELIST:
        if len(argv) >= len(prefix) and argv[: len(prefix)] == prefix:
            return True
    return False


#: 解释器的“内联执行”开关。`python -c "..."`、`node -e "..."` 这类命令
#: 等价于执行任意代码，因此在词法层面就无法与普通脚本调用区分开：
#: 元字符检查会被双引号绕过（审计 SEC-04）。这里把它们一律降级为
#: "unknown"，让沙箱终端拦住、或在无沙箱时强制确认。
#: 注意：`python -m pytest` 这类不在其中，仍然走白名单。
INLINE_EXEC_FLAGS = {
    "python": {"-c"}, "python3": {"-c"}, "py": {"-c"},
    "node": {"-e", "--eval", "-p", "--print"},
    "perl": {"-e"}, "ruby": {"-e"}, "php": {"-r"},
    "bash": {"-c"}, "sh": {"-c"}, "zsh": {"-c"},
    "powershell": {"-c", "-command", "-encodedcommand", "-enc"},
    "pwsh": {"-c", "-command", "-encodedcommand", "-enc"},
    "cmd": {"/c", "/k"},
    "wscript": set(), "cscript": set(),
}


def _has_inline_exec(argv: list, base: str) -> bool:
    flags = INLINE_EXEC_FLAGS.get(base)
    if not flags:
        return False
    return any(a.lower() in flags for a in argv[1:])


def _match_allow_prefix(argv: list) -> bool:
    return _match_whitelist(argv)


def _shell_allow_display() -> list:
    seen: dict = {}
    for prefix in SHELL_WHITELIST:
        seen.setdefault(prefix[0], set()).add(" ".join(prefix))
    out = []
    for first, variants in sorted(seen.items()):
        out.append(" / ".join(sorted(variants)))
    return out


def merge_bash_prefixes(extra: list) -> None:
    for raw in extra:
        try:
            argv = shlex.split(raw)
        except ValueError:
            continue
        if not argv:
            continue
        if argv not in SHELL_WHITELIST:
            SHELL_WHITELIST.append(argv)


def _check_dangerous_pattern(command: str) -> str:
    low = command.lower()
    for pat in SHELL_DANGEROUS_PATTERNS:
        if pat.lower() in low:
            return pat
    return ""


def classify_command(command: str) -> tuple:
    """返回 (level, reason)。

    level ∈ {blocked, whitelist, known, unknown}
    """
    hit = _check_dangerous_pattern(command)
    if hit:
        return "blocked", f"命中危险模式: {hit}"
    argv, err = _parse_shell_command(command)
    if err:
        return "blocked", err
    first = argv[0].lower()
    base = first
    for suffix in (".exe", ".cmd", ".bat", ".sh", ".ps1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if base in SHELL_BLACKLIST or base.split(".")[0] in SHELL_BLACKLIST:
        # `base.split(".")` also catches versioned/variant binaries such as
        # mkfs.ext4, mkfs.ntfs or rm.exe, which would otherwise bypass the
        # exact-name blacklist and be downgraded to "unknown".
        return "blocked", f"命令 '{base}' 在永久拒绝名单"
    if _has_inline_exec(argv, base):
        return "unknown", f"解释器内联执行（{base}）"
    if _match_whitelist(argv):
        return "whitelist", ""
    if base in SHELL_KNOWN_COMMANDS:
        return "known", ""
    return "unknown", ""