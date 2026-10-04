"""文件属性：Windows ReadOnly/Hidden/System/Archive；Unix 权限/属主。

读取 attr 直接执行；修改 attr 由 core 层确认。
"""
from __future__ import annotations

import os
import platform
import stat
import subprocess
from pathlib import Path

from .sandbox import _resolve_path

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

WIN_ATTR_MAP = {
    "readonly": stat.FILE_ATTRIBUTE_READONLY,
    "hidden": stat.FILE_ATTRIBUTE_HIDDEN,
    "system": stat.FILE_ATTRIBUTE_SYSTEM,
    "archive": stat.FILE_ATTRIBUTE_ARCHIVE,
    "not_indexed": getattr(stat, "FILE_ATTRIBUTE_NOT_CONTENT_INDEXED", 0x2000),
    "temporary": stat.FILE_ATTRIBUTE_TEMPORARY,
    "offline": stat.FILE_ATTRIBUTE_OFFLINE,
    "compressed": stat.FILE_ATTRIBUTE_COMPRESSED,
    "encrypted": stat.FILE_ATTRIBUTE_ENCRYPTED,
}

WIN_FLAG_LETTER = {
    "R": "readonly", "H": "hidden", "S": "system", "A": "archive",
    "I": "not_indexed", "T": "temporary", "O": "offline",
    "C": "compressed", "E": "encrypted",
}


# ═══════════════════════════════════════════════════════════════════════ #
# 读取
# ═══════════════════════════════════════════════════════════════════════ #

def _format_mode(st_mode: int) -> str:
    """Unix 权限转 rwxr-xr-x 形式。"""
    return stat.filemode(st_mode)


def _oct(n: int) -> str:
    return format(n & 0o777, "03o")


def file_attrs_get(path: str, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"

    rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
    try:
        st = p.lstat()
    except OSError as exc:
        return f"ERROR: 无法获取属性: {exc}"

    lines = [
        f"路径: {rel}",
        f"类型: {'目录' if p.is_dir() else '文件' if p.is_file() else '其他'}",
        f"大小: {st.st_size} bytes",
    ]

    if IS_WINDOWS:
        try:
            win_attrs = p.stat().st_file_attributes
        except (AttributeError, OSError):
            win_attrs = 0

        active = []
        for name, flag in WIN_ATTR_MAP.items():
            if win_attrs & flag:
                letter = next((k for k, v in WIN_FLAG_LETTER.items() if v == name), "")
                active.append(f"{name}({letter})" if letter else name)

        lines.append("")
        lines.append("Windows 属性:")
        if active:
            for a in active:
                lines.append(f"  ✓ {a}")
        else:
            lines.append("  (无特殊属性)")

        lines.append("")
        lines.append(f"原始属性值: 0x{win_attrs:08X}")

    else:
        perms = stat.S_IMODE(st.st_mode)
        lines.append("")
        lines.append("Unix 权限:")
        lines.append(f"  符号: {_format_mode(st.st_mode)}")
        lines.append(f"  八进制: {_oct(perms)}")
        lines.append(f"  可读: {'是' if os.access(p, os.R_OK) else '否'}")
        lines.append(f"  可写: {'是' if os.access(p, os.W_OK) else '否'}")
        lines.append(f"  可执行: {'是' if os.access(p, os.X_OK) else '否'}")

        try:
            import pwd, grp
            lines.append("")
            lines.append(f"属主: {pwd.getpwuid(st.st_uid).pw_name} (uid={st.st_uid})")
            lines.append(f"属组: {grp.getgrgid(st.st_gid).gr_name} (gid={st.st_gid})")
        except (ImportError, KeyError):
            lines.append("")
            lines.append(f"属主: uid={st.st_uid}")
            lines.append(f"属组: gid={st.st_gid}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════ #
# 修改：Windows 属性
# ═══════════════════════════════════════════════════════════════════════ #

def file_attrs_preview(path: str, action: str, attrs: list,
                       root: Path) -> tuple[str, bool, str]:
    """返回 (preview, is_write, error)。"""
    a = (action or "").lower()
    if a not in ("add", "remove", "set", "clear"):
        return "", False, "ERROR: action 必须是 add / remove / set / clear"

    if not IS_WINDOWS:
        return "", False, (
            "ERROR: 该操作仅 Windows 可用。\n"
            "Unix 请用 op='set_perms' 或 op='set_owner'。"
        )

    p, err = _resolve_path(root, path)
    if err:
        return "", False, err
    if not p.exists():
        return "", False, f"ERROR: 路径不存在: {path}"

    rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)

    if a == "clear":
        return f"路径: {rel}\n将清除所有可清除的 Windows 属性", True, ""

    if not attrs:
        return "", False, "ERROR: 需要 attrs 列表"

    normalized = []
    for x in attrs:
        s = str(x).strip().lower()
        if s in WIN_ATTR_MAP:
            normalized.append(s)
        elif s.upper() in WIN_FLAG_LETTER:
            normalized.append(WIN_FLAG_LETTER[s.upper()])
        else:
            return "", False, (
                f"ERROR: 未知属性 '{x}'。"
                f"可选: {', '.join(sorted(WIN_ATTR_MAP.keys()))}"
            )

    verb = {"add": "添加", "remove": "移除", "set": "设置（替换）"}[a]
    return (f"路径: {rel}\n"
            f"操作: {verb}\n"
            f"属性: {', '.join(normalized)}"), True, ""


def file_attrs_apply(path: str, action: str, attrs: list,
                     root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists():
        return f"ERROR: 路径不存在: {path}"

    a = (action or "").lower()
    current = 0
    try:
        current = p.stat().st_file_attributes
    except (AttributeError, OSError):
        current = 0

    if a == "clear":
        if IS_WINDOWS:
            try:
                subprocess.run(["attrib", "-R", "-H", "-S", "-A", str(p)],
                               capture_output=True, text=True, timeout=10)
                return f"已清除 {path} 的属性"
            except (OSError, subprocess.TimeoutExpired) as exc:
                return f"ERROR: {exc}"
        return "ERROR: 仅 Windows 可用"

    target_flags = 0
    for name in attrs:
        s = str(name).strip().lower()
        if s in WIN_ATTR_MAP:
            target_flags |= WIN_ATTR_MAP[s]

    if a == "add":
        new_flags = current | target_flags
    elif a == "remove":
        new_flags = current & ~target_flags
    else:  # set
        new_flags = target_flags

    try:
        os.chmod(str(p), new_flags)
    except (OSError, NotImplementedError) as exc:
        # 降级到 attrib
        cmd = ["attrib"]
        for flag_name, flag_val in WIN_ATTR_MAP.items():
            if flag_val not in WIN_FLAG_LETTER.values():
                continue
            letter = next((k for k, v in WIN_FLAG_LETTER.items()
                           if v == flag_name), "")
            if not letter:
                continue
            if flag_name in attrs:
                cmd.append(f"+{letter}")
            else:
                cmd.append(f"-{letter}")
        cmd.append(str(p))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return f"已更新 {path} 的属性（via attrib）"
            return f"ERROR: attrib 失败: {r.stderr or r.stdout}"
        except (OSError, subprocess.TimeoutExpired) as exc2:
            return f"ERROR: {exc} / attrib: {exc2}"

    return f"已更新 {path} 的属性"


# ═══════════════════════════════════════════════════════════════════════ #
# 修改：Unix 权限 / 属主
# ═══════════════════════════════════════════════════════════════════════ #

def _parse_mode(mode: str) -> tuple[int | None, str]:
    """支持 '644' / '0755' / 'rwxr-xr-x' / 'u+x'。返回 (bits, error)。"""
    if mode is None:
        return None, "mode 不能为空"
    s = str(mode).strip()

    if s.isdigit() and len(s) in (3, 4):
        try:
            return int(s, 8), ""
        except ValueError:
            return None, f"八进制解析失败: {s}"

    if len(s) == 9 and all(c in "rwx-" for c in s):
        bits = 0
        for i, c in enumerate(s):
            if c == "-":
                continue
            bits |= 1 << (8 - i)
        return bits, ""

    return None, f"不支持的权限格式: {s}（用 '644' 或 'rwxr-xr-x'）"


def file_perms_preview(path: str, mode: str, root: Path) -> tuple[str, bool, str]:
    if IS_WINDOWS:
        return "", False, "ERROR: Unix 权限仅 Linux/macOS 可用"

    p, err = _resolve_path(root, path)
    if err:
        return "", False, err
    if not p.exists():
        return "", False, f"ERROR: 路径不存在: {path}"

    bits, merr = _parse_mode(mode)
    if merr:
        return "", False, f"ERROR: {merr}"

    rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
    try:
        old = stat.S_IMODE(p.stat().st_mode)
    except OSError as exc:
        return "", False, f"ERROR: {exc}"

    return (f"路径: {rel}\n"
            f"旧权限: {_oct(old)} ({stat.filemode(old)[1:]})\n"
            f"新权限: {_oct(bits)} ({stat.filemode(bits | 0o100000)[1:]})"), True, ""


def file_perms_apply(path: str, mode: str, recursive: bool,
                     root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err
    bits, merr = _parse_mode(mode)
    if merr:
        return f"ERROR: {merr}"

    count = 0
    try:
        if recursive and p.is_dir():
            for f in p.rglob("*"):
                os.chmod(str(f), bits)
                count += 1
            os.chmod(str(p), bits)
            count += 1
        else:
            os.chmod(str(p), bits)
            count = 1
    except OSError as exc:
        return f"ERROR: 修改失败: {exc}"

    return f"已修改 {count} 个路径的权限为 {_oct(bits)}"


def file_owner_preview(path: str, user: str = "", group: str = "",
                       root: Path | None = None) -> tuple[str, bool, str]:
    if IS_WINDOWS:
        return "", False, "ERROR: 属主修改仅 Linux/macOS 可用"
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not user and not group:
        return "", False, "ERROR: 需要 user 或 group"

    p, err = _resolve_path(root, path)
    if err:
        return "", False, err
    if not p.exists():
        return "", False, f"ERROR: 路径不存在: {path}"

    rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
    parts = []
    if user:
        parts.append(f"属主 → {user}")
    if group:
        parts.append(f"属组 → {group}")

    try:
        st = p.stat()
        import pwd, grp
        old_user = pwd.getpwuid(st.st_uid).pw_name
        old_group = grp.getgrgid(st.st_gid).gr_name
    except (ImportError, KeyError):
        old_user = old_group = "?"

    return (f"路径: {rel}\n"
            f"当前: {old_user}:{old_group}\n"
            f"改为: {' '.join(parts)}"), True, ""


def file_owner_apply(path: str, user: str, group: str,
                     recursive: bool, root: Path) -> str:
    p, err = _resolve_path(root, path)
    if err:
        return err

    uid = -1
    gid = -1
    if user:
        try:
            import pwd
            uid = pwd.getpwnam(user).pw_uid
        except (ImportError, KeyError) as exc:
            return f"ERROR: 找不到用户 '{user}': {exc}"
    if group:
        try:
            import grp
            gid = grp.getgrnam(group).gr_gid
        except (ImportError, KeyError) as exc:
            return f"ERROR: 找不到组 '{group}': {exc}"

    count = 0
    try:
        if recursive and p.is_dir():
            for f in p.rglob("*"):
                os.chown(str(f), uid, gid)
                count += 1
            os.chown(str(p), uid, gid)
            count += 1
        else:
            os.chown(str(p), uid, gid)
            count = 1
    except PermissionError:
        return "ERROR: 权限不足（通常需要 root/sudo）"
    except OSError as exc:
        return f"ERROR: {exc}"

    return f"已修改 {count} 个路径的属主/属组"


# ═══════════════════════════════════════════════════════════════════════ #
# 目录批量查看
# ═══════════════════════════════════════════════════════════════════════ #

def file_attrs_bulk(path: str = ".", root: Path | None = None,
                    filter: str = "", max_items: int = 100) -> str:
    """批量查看目录下文件的属性。"""
    if root is None:
        return "ERROR: 需要 root"
    p, err = _resolve_path(root, path)
    if err:
        return err
    if not p.exists() or not p.is_dir():
        return f"ERROR: 不是目录: {path}"

    try:
        n = max(1, min(int(max_items), 500))
    except (TypeError, ValueError):
        n = 100

    lines = []
    count = 0
    for f in sorted(p.iterdir()):
        if filter and filter.lower() not in f.name.lower():
            continue
        if count >= n:
            break
        try:
            st = f.lstat()
        except OSError:
            continue

        name = f.name + ("/" if f.is_dir() else "")
        if IS_WINDOWS:
            try:
                wa = f.stat().st_file_attributes
            except (AttributeError, OSError):
                wa = 0
            flags = ""
            for letter, fname in WIN_FLAG_LETTER.items():
                flag_val = WIN_ATTR_MAP.get(fname, 0)
                if flag_val and (wa & flag_val):
                    flags += letter
            flags = flags or "-"
            lines.append(f"{flags:6} {name}")
        else:
            perms = _oct(stat.S_IMODE(st.st_mode))
            lines.append(f"{perms:6} {name}")

        count += 1

    if not lines:
        return f"目录 {path} 为空或无匹配项"

    header = f"目录: {path}（{count} 项）"
    if IS_WINDOWS:
        header += "\n标志: R=只读 H=隐藏 S=系统 A=归档 I=未索引 T=临时 O=离线"
    else:
        header += "\n权限: 八进制（644=rw-r--r--，755=rwxr-xr-x）"

    return header + "\n\n" + "\n".join(lines)