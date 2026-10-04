"""应用管理：打开 / 列表 / 搜索 / 安装 / 卸载。

Windows: start / Get-StartApps / winget / choco / scoop
macOS:   open / /Applications / brew / mas
Linux:   xdg-open / .desktop / apt / snap / flatpak / pacman
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _run(cmd: list, timeout: int = 30, shell: bool = False):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, shell=shell,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return 127, "", f"命令不存在: {cmd[0] if cmd else '?'}"
    except subprocess.TimeoutExpired:
        return 124, "", f"超时（{timeout}s）"
    except OSError as exc:
        return 1, "", str(exc)


# ═══════════════════════════════════════════════════════════════════════ #
# 打开应用 / 文件
# ═══════════════════════════════════════════════════════════════════════ #

def open_app(target: str, args: list | None = None) -> str:
    """打开应用/文件/URL。

    Windows: start
    macOS:   open
    Linux:   xdg-open
    """
    if not target:
        return "ERROR: 需要 target"

    extra = [str(a) for a in (args or [])]

    if IS_WINDOWS:
        # Windows 用 start（通过 cmd /c）
        # start 第一个参数是窗口标题，给个空标题避免被当标题
        parts = ["cmd", "/c", "start", ""]
        parts.append(target)
        parts.extend(extra)
        try:
            r = subprocess.Popen(
                parts, shell=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return f"已启动: {target}"
        except OSError as exc:
            return f"ERROR: {exc}"

    if IS_MAC:
        cmd = ["open"]
        if extra:
            cmd.append("-a") if not target.endswith((".app",)) else None
            cmd.append(target)
            cmd.extend(["--args"] + extra)
        else:
            cmd.append(target)
        # 修正：不加 --args 更简单
        if extra:
            cmd = ["open", "-a", target, "--args"] + extra
        else:
            cmd = ["open", target]
        try:
            r = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return f"已启动: {target}"
        except OSError as exc:
            return f"ERROR: {exc}"

    if IS_LINUX:
        if not shutil.which("xdg-open"):
            return "ERROR: 需要 xdg-open（通常由 xdg-utils 提供）"
        cmd = ["xdg-open", target] + extra
        try:
            r = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return f"已启动: {target}"
        except OSError as exc:
            return f"ERROR: {exc}"

    return "ERROR: 当前平台不支持"


# ═══════════════════════════════════════════════════════════════════════ #
# 列出已安装应用
# ═══════════════════════════════════════════════════════════════════════ #

def list_apps(filter: str = "", limit: int = 100) -> str:
    """列出已安装应用。"""
    try:
        n = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        n = 100

    apps = []

    if IS_WINDOWS:
        apps = _list_apps_windows()
    elif IS_MAC:
        apps = _list_apps_mac()
    elif IS_LINUX:
        apps = _list_apps_linux()

    if filter:
        f = filter.lower()
        apps = [(name, path) for name, path in apps if f in name.lower()
                or f in path.lower()]

    if not apps:
        return f"未找到应用（filter={filter!r}）" if filter else "未找到已安装应用"

    apps.sort(key=lambda x: x[0].lower())
    total = len(apps)
    shown = apps[:n]

    lines = [f"共 {total} 个应用，显示前 {len(shown)}：", ""]
    for name, path in shown:
        lines.append(f"  {name}")
        if path and path != name:
            short = path if len(path) < 80 else "..." + path[-77:]
            lines.append(f"    [dim]{short}[/]")
    if total > n:
        lines.append(f"  ... 还有 {total - n} 个（用 limit 参数查看更多）")
    return "\n".join(lines)


def _list_apps_windows() -> list:
    """Windows: 从开始菜单 + 注册表获取。"""
    out = []

    # 方法 1: Get-StartApps（UWP + 传统）
    ps = ("Get-StartApps | ConvertTo-Json -Compress")
    rc, stdout, _ = _run(
        ["powershell", "-NoProfile", "-Command", ps], timeout=20,
    )
    if rc == 0 and stdout.strip():
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                name = item.get("Name", "")
                aid = item.get("AppID", "")
                if name:
                    out.append((name, aid))
        except json.JSONDecodeError:
            pass

    # 去重
    seen = set()
    unique = []
    for name, path in out:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((name, path))

    return unique


def _list_apps_mac() -> list:
    """macOS: 扫描 /Applications 和 ~/Applications。"""
    out = []
    dirs = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path("/Applications/Utilities"),
        Path.home() / "Applications",
    ]
    seen = set()
    for d in dirs:
        if not d.exists():
            continue
        try:
            for item in d.iterdir():
                if item.suffix == ".app":
                    name = item.stem
                    if name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    out.append((name, str(item)))
        except OSError:
            continue
    return out


def _list_apps_linux() -> list:
    """Linux: 扫描 .desktop 文件。"""
    out = []
    dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
        Path("/var/lib/snapd/desktop/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
    ]
    seen = set()
    for d in dirs:
        if not d.exists():
            continue
        try:
            for f in d.glob("*.desktop"):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                name = ""
                exec_cmd = ""
                for line in text.splitlines():
                    if line.startswith("Name=") and not name:
                        name = line[5:].strip()
                    elif line.startswith("Exec="):
                        exec_cmd = line[5:].strip()
                if not name:
                    continue
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append((name, exec_cmd))
        except OSError:
            continue
    return out


# ═══════════════════════════════════════════════════════════════════════ #
# 搜索应用
# ═══════════════════════════════════════════════════════════════════════ #

def find_app(name: str, max_results: int = 20) -> str:
    """模糊搜索应用。"""
    if not name:
        return "ERROR: 需要 name"

    apps = []
    if IS_WINDOWS:
        apps = _list_apps_windows()
    elif IS_MAC:
        apps = _list_apps_mac()
    elif IS_LINUX:
        apps = _list_apps_linux()

    q = name.lower()
    matches = []
    for app_name, path in apps:
        score = 0
        n = app_name.lower()
        if n == q:
            score = 100
        elif n.startswith(q):
            score = 80
        elif q in n:
            score = 60
        elif q in path.lower():
            score = 40
        if score:
            matches.append((score, app_name, path))

    if not matches:
        return f"未找到匹配 '{name}' 的应用"

    matches.sort(key=lambda x: -x[0])
    shown = matches[:max_results]
    lines = [f"找到 {len(matches)} 个匹配：", ""]
    for score, app_name, path in shown:
        lines.append(f"  {app_name}  [{score}]")
        if path:
            lines.append(f"    {path}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════ #
# 包管理器（安装 / 卸载）
# ═══════════════════════════════════════════════════════════════════════ #

def _detect_pkg_manager() -> str:
    if IS_WINDOWS:
        if shutil.which("winget"):
            return "winget"
        if shutil.which("choco"):
            return "choco"
        if shutil.which("scoop"):
            return "scoop"
        return ""
    if IS_MAC:
        if shutil.which("brew"):
            return "brew"
        if shutil.which("mas"):
            return "mas"
        return ""
    if IS_LINUX:
        for pm in ("apt", "dnf", "yum", "pacman", "zypper", "snap", "flatpak"):
            if shutil.which(pm):
                return pm
        return ""
    return ""


def list_pkg_manager() -> str:
    pm = _detect_pkg_manager()
    if not pm:
        return "未检测到可用的包管理器"
    info = [f"当前包管理器: {pm}"]
    if IS_WINDOWS:
        info.append("  winget  — Windows 官方包管理器")
        info.append("  choco   — Chocolatey")
        info.append("  scoop   — Scoop")
    elif IS_MAC:
        info.append("  brew    — Homebrew")
    elif IS_LINUX:
        info.append("  apt     — Debian / Ubuntu")
        info.append("  dnf     — Fedora / RHEL")
        info.append("  pacman  — Arch")
        info.append("  snap    — Snap")
        info.append("  flatpak — Flatpak")
    return "\n".join(info)


def install_preview(package: str, source: str = "") -> tuple:
    """安装预览。返回 (preview, is_write, err)。"""
    if not package:
        return "", False, "ERROR: 需要 package 名"

    pm = source or _detect_pkg_manager()
    if not pm:
        return "", False, "ERROR: 未找到包管理器"

    cmd = _install_cmd(pm, package)
    if not cmd:
        return "", False, f"ERROR: {pm} 不支持或未安装"

    return (f"包管理器: {pm}\n"
            f"包名: {package}\n"
            f"命令: {' '.join(cmd)}\n"
            f"⚠ 需要管理员/root 权限"), True, ""


def uninstall_preview(package: str, source: str = "") -> tuple:
    if not package:
        return "", False, "ERROR: 需要 package 名"
    pm = source or _detect_pkg_manager()
    if not pm:
        return "", False, "ERROR: 未找到包管理器"

    cmd = _uninstall_cmd(pm, package)
    if not cmd:
        return "", False, f"ERROR: {pm} 不支持或未安装"

    return (f"包管理器: {pm}\n"
            f"包名: {package}\n"
            f"命令: {' '.join(cmd)}\n"
            f"⚠ 不可撤销"), True, ""


def install_apply(package: str, source: str = "") -> str:
    pm = source or _detect_pkg_manager()
    cmd = _install_cmd(pm, package)
    if not cmd:
        return f"ERROR: {pm} 不支持"
    rc, out, err = _run(cmd, timeout=300)
    if rc == 0:
        return f"已安装 {package}\n{out[-500:]}"
    return f"ERROR (rc={rc}):\n{(err or out)[-800:]}"


def uninstall_apply(package: str, source: str = "") -> str:
    pm = source or _detect_pkg_manager()
    cmd = _uninstall_cmd(pm, package)
    if not cmd:
        return f"ERROR: {pm} 不支持"
    rc, out, err = _run(cmd, timeout=300)
    if rc == 0:
        return f"已卸载 {package}\n{out[-500:]}"
    return f"ERROR (rc={rc}):\n{(err or out)[-800:]}"


def _install_cmd(pm: str, pkg: str) -> list:
    if pm == "winget":
        return ["winget", "install", "--accept-source-agreements",
                "--accept-package-agreements", pkg]
    if pm == "choco":
        return ["choco", "install", "-y", pkg]
    if pm == "scoop":
        return ["scoop", "install", pkg]
    if pm == "brew":
        return ["brew", "install", pkg]
    if pm == "mas":
        return ["mas", "install", pkg]
    if pm == "apt":
        return ["sudo", "apt", "install", "-y", pkg]
    if pm == "dnf":
        return ["sudo", "dnf", "install", "-y", pkg]
    if pm == "yum":
        return ["sudo", "yum", "install", "-y", pkg]
    if pm == "pacman":
        return ["sudo", "pacman", "-S", "--noconfirm", pkg]
    if pm == "zypper":
        return ["sudo", "zypper", "install", "-y", pkg]
    if pm == "snap":
        return ["sudo", "snap", "install", pkg]
    if pm == "flatpak":
        return ["flatpak", "install", "-y", "flathub", pkg]
    return []


def _uninstall_cmd(pm: str, pkg: str) -> list:
    if pm == "winget":
        return ["winget", "uninstall", pkg]
    if pm == "choco":
        return ["choco", "uninstall", "-y", pkg]
    if pm == "scoop":
        return ["scoop", "uninstall", pkg]
    if pm == "brew":
        return ["brew", "uninstall", pkg]
    if pm == "apt":
        return ["sudo", "apt", "remove", "-y", pkg]
    if pm == "dnf":
        return ["sudo", "dnf", "remove", "-y", pkg]
    if pm == "yum":
        return ["sudo", "yum", "remove", "-y", pkg]
    if pm == "pacman":
        return ["sudo", "pacman", "-R", "--noconfirm", pkg]
    if pm == "zypper":
        return ["sudo", "zypper", "remove", "-y", pkg]
    if pm == "snap":
        return ["sudo", "snap", "remove", pkg]
    if pm == "flatpak":
        return ["flatpak", "uninstall", "-y", pkg]
    return []


def search_pkg(query: str, source: str = "", limit: int = 20) -> str:
    """搜索可安装的包。"""
    if not query:
        return "ERROR: 需要 query"
    pm = source or _detect_pkg_manager()
    if not pm:
        return "ERROR: 未找到包管理器"

    if pm == "winget":
        cmd = ["winget", "search", query]
    elif pm == "choco":
        cmd = ["choco", "search", query]
    elif pm == "scoop":
        cmd = ["scoop", "search", query]
    elif pm == "brew":
        cmd = ["brew", "search", query]
    elif pm == "apt":
        cmd = ["apt-cache", "search", query]
    elif pm == "dnf":
        cmd = ["dnf", "search", query]
    elif pm == "pacman":
        cmd = ["pacman", "-Ss", query]
    elif pm == "snap":
        cmd = ["snap", "find", query]
    elif pm == "flatpak":
        cmd = ["flatpak", "search", query]
    else:
        return f"ERROR: {pm} 不支持搜索"

    rc, out, err = _run(cmd, timeout=30)
    if rc != 0:
        return f"ERROR: {(err or out)[:500]}"
    lines = out.splitlines()[:limit + 5]
    return "\n".join(lines) if lines else "无结果"


def list_installed(pm: str = "") -> str:
    """列出已安装的包。"""
    manager = pm or _detect_pkg_manager()
    if not manager:
        return "ERROR: 未找到包管理器"

    if manager == "winget":
        cmd = ["winget", "list"]
    elif manager == "choco":
        cmd = ["choco", "list", "--local-only"]
    elif manager == "scoop":
        cmd = ["scoop", "list"]
    elif manager == "brew":
        cmd = ["brew", "list"]
    elif manager == "apt":
        cmd = ["apt", "list", "--installed"]
    elif manager == "dnf":
        cmd = ["dnf", "list", "installed"]
    elif manager == "pacman":
        cmd = ["pacman", "-Q"]
    elif manager == "snap":
        cmd = ["snap", "list"]
    elif manager == "flatpak":
        cmd = ["flatpak", "list"]
    else:
        return f"ERROR: {manager} 不支持"

    rc, out, err = _run(cmd, timeout=30)
    if rc != 0:
        return f"ERROR: {(err or out)[:500]}"
    lines = out.splitlines()
    if len(lines) > 100:
        lines = lines[:100] + [f"... 还有 {len(lines) - 100} 行"]
    return "\n".join(lines)