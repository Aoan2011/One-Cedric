"""系统工具：env_info / process_info / calculate / clipboard / system_metrics。"""
from __future__ import annotations

import ast
import math
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import ENV_SENSITIVE_KEYWORDS
from .sandbox import _as_int


def _shade_env_value(key: str, value: str) -> str:
    low = key.lower()
    for kw in ENV_SENSITIVE_KEYWORDS:
        if kw in low:
            return "***（已屏蔽）"
    if len(value) > 30 and re.fullmatch(r"[A-Za-z0-9_\-\.=+/:]+",
                                        value):
        return value[:6] + "..." + value[-4:]
    return value


def env_info(root: Path, include: str = "all") -> str:
    include = (include or "all").lower()
    parts: list = []
    if include in ("all", "system"):
        parts.append("## 系统")
        parts.append(f"平台: {platform.platform()}")
        parts.append(f"架构: {platform.machine()}")
        parts.append(f"处理器: {platform.processor() or '未知'}")
        parts.append(f"Python: {sys.version.split()[0]} "
                     f"({sys.executable})")
        parts.append(f"工作目录: {root}")
    if include in ("all", "python"):
        parts.append("\n## Python 环境")
        parts.append(f"实现: {platform.python_implementation()}")
        parts.append(f"版本: {sys.version}")
        parts.append(f"venv: {sys.prefix != sys.base_prefix}")
        parts.append(f"prefix: {sys.prefix}")
    if include in ("all", "packages"):
        parts.append("\n## 关键包")
        try:
            from importlib.metadata import distributions
            wanted = {"requests", "rich", "pyyaml", "pytest", "ruff",
                      "black", "mypy", "flask", "fastapi", "django",
                      "numpy", "pandas", "torch"}
            found = {}
            for d in distributions():
                name = (d.metadata.get("Name") or "").lower()
                if name in wanted:
                    found[name] = d.version
            for name in sorted(found):
                parts.append(f"  {name}: {found[name]}")
            if not found:
                parts.append("  （未发现关键包）")
        except Exception as exc:
            parts.append(f"  （无法枚举: {exc}）")
    if include in ("all", "env"):
        parts.append("\n## 环境变量")
        try:
            for k in sorted(os.environ.keys()):
                v = os.environ.get(k, "")
                parts.append(f"  {k}={_shade_env_value(k, v)}")
        except Exception as exc:
            parts.append(f"  （无法读取: {exc}）")
    return "\n".join(parts)


def process_info(scope: str = "processes", filter: str = "",
                 limit=None) -> str:
    scope = (scope or "processes").lower()
    lim = _as_int(limit, 30)
    if lim <= 0:
        lim = 30
    lines: list = []
    if scope in ("processes", "all"):
        lines.append("## 进程")
        try:
            if os.name == "nt":
                cmd = ["tasklist", "/FO", "CSV"]
            else:
                cmd = ["ps", "-eo", "pid,ppid,pcpu,pmem,etime,cmd"]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=10)
            out = (r.stdout or "").splitlines()
            if scope == "all" and not filter:
                out = out[:lim + 1]
            elif filter:
                out = [out[0]] + [l for l in out[1:] if filter in l][:lim]
            else:
                out = out[:lim + 1]
            lines.extend(out)
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"（获取失败: {exc}）")
        lines.append("")
    if scope in ("ports", "all"):
        lines.append("## 端口")
        try:
            if os.name == "nt":
                cmd = ["netstat", "-ano"]
            else:
                if shutil.which("ss"):
                    cmd = ["ss", "-tlnp"]
                else:
                    cmd = ["netstat", "-tlnp"]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=10)
            out = (r.stdout or "").splitlines()
            if filter:
                out = [out[0]] + [l for l in out[1:] if filter in l][:lim]
            else:
                out = out[:lim + 1]
            lines.extend(out)
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"（获取失败: {exc}）")
    return "\n".join(lines) if lines else "（无信息）"


_SAFE_MATH = {k: getattr(math, k) for k in dir(math)
              if not k.startswith("_")}
_SAFE_CONSTANTS = {
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "inf": math.inf, "nan": math.nan,
}


def _safe_calc(expr: str):
    if not expr or not expr.strip():
        raise ValueError("表达式为空")

    def _eval(n):
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant):
            if (isinstance(n.value, (int, float, complex))
                    and not isinstance(n.value, bool)):
                return n.value
            raise ValueError(
                f"不支持的常量类型: {type(n.value).__name__}")
        if isinstance(n, ast.BinOp):
            l, r = _eval(n.left), _eval(n.right)
            op = n.op
            if isinstance(op, ast.Add): return l + r
            if isinstance(op, ast.Sub): return l - r
            if isinstance(op, ast.Mult): return l * r
            if isinstance(op, ast.Div): return l / r
            if isinstance(op, ast.FloorDiv): return l // r
            if isinstance(op, ast.Mod): return l % r
            if isinstance(op, ast.Pow): return l ** r
            raise ValueError(f"不支持的运算符: {type(op).__name__}")
        if isinstance(n, ast.UnaryOp):
            v = _eval(n.operand)
            if isinstance(n.op, ast.UAdd): return +v
            if isinstance(n.op, ast.USub): return -v
            raise ValueError("不支持的一元运算符")
        if isinstance(n, ast.Name):
            if n.id in _SAFE_CONSTANTS:
                return _SAFE_CONSTANTS[n.id]
            raise ValueError(f"未知名称: {n.id}")
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name):
                raise ValueError("只允许直接调用 math 函数")
            fn = _SAFE_MATH.get(n.func.id)
            if fn is None:
                raise ValueError(f"未知函数: {n.func.id}")
            args = [_eval(a) for a in n.args]
            kwargs = {k.arg: _eval(k.value)
                      for k in n.keywords if k.arg}
            return fn(*args, **kwargs)
        raise ValueError(f"不支持的语法: {type(n).__name__}")

    tree = ast.parse(expr, mode="eval")
    return _eval(tree)


def calculate(expression: str) -> str:
    if not expression or not expression.strip():
        return "ERROR: 表达式为空。"
    try:
        result = _safe_calc(expression)
    except (SyntaxError, ValueError, ZeroDivisionError,
            OverflowError, TypeError, RecursionError) as exc:
        return f"ERROR: 求值失败: {exc}"
    return f"{expression.strip()} = {result}"


def _clipboard_available():
    if os.name == "nt":
        if shutil.which("powershell"):
            return (
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                ["powershell", "-NoProfile", "-Command",
                 "$input | Set-Clipboard"],
            )
        return None
    if sys.platform == "darwin":
        if shutil.which("pbcopy") and shutil.which("pbpaste"):
            return (["pbpaste"], ["pbcopy"])
        return None
    for read_c, write_c in (
        (["wl-paste"], ["wl-copy"]),
        (["xclip", "-selection", "clipboard", "-o"],
         ["xclip", "-selection", "clipboard"]),
        (["xsel", "--clipboard", "--output"],
         ["xsel", "--clipboard", "--input"]),
    ):
        if shutil.which(read_c[0]) and shutil.which(write_c[0]):
            return (read_c, write_c)
    return None


def clipboard_op(op: str, text: str = "") -> tuple:
    op = (op or "").strip().lower()
    cmds = _clipboard_available()
    if cmds is None:
        return "", False, ("ERROR: 找不到剪贴板工具。"
                           "Linux 请安装 wl-clipboard 或 xclip 或 xsel；"
                           "macOS 应有 pbcopy/pbpaste；"
                           "Windows 需 PowerShell。")
    read_c, write_c = cmds
    if op == "read":
        try:
            r = subprocess.run(read_c, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", False, f"ERROR: 读取剪贴板失败: {exc}"
        if r.returncode != 0:
            return "", False, (f"ERROR: 读取失败"
                               f"（rc={r.returncode}）: "
                               f"{r.stderr.strip()}")
        content = r.stdout
        if len(content) > 8000:
            content = (content[:8000]
                       + f"\n... (截断，原始 {len(r.stdout)} 字符)")
        return "剪贴板内容：\n" + (content or "(空)"), False, ""
    if op == "write":
        if not isinstance(text, str):
            return "", False, "ERROR: text 必须是字符串。"
        if len(text.encode("utf-8")) > 1_000_000:
            return "", False, "ERROR: 文本超过 1MB 上限。"
        return f"将写入剪贴板（{len(text)} 字符）", True, ""
    return "", False, f"ERROR: 不支持的 op: {op}"


def _clipboard_write(text: str) -> str:
    cmds = _clipboard_available()
    if cmds is None:
        return "ERROR: 找不到剪贴板工具。"
    _, write_c = cmds
    try:
        r = subprocess.run(write_c, input=text, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: 写入失败: {exc}"
    if r.returncode != 0:
        return (f"ERROR: 写入失败（rc={r.returncode}）: "
                f"{r.stderr.strip()}")
    return f"已写入剪贴板（{len(text)} 字符）"


def system_metrics(include: str = "all") -> str:
    include = (include or "all").lower()
    try:
        import psutil
    except ImportError:
        psutil = None
    parts: list = []
    if psutil is None:
        parts.append("[警告] 未安装 psutil，部分信息不可用。"
                     "pip install psutil")
        try:
            import shutil as _sh
            total, used, free = _sh.disk_usage(str(Path.home()))
            parts.append("\n## 磁盘")
            parts.append(f"总计 {total // (1024**3)} GB · "
                         f"已用 {used // (1024**3)} GB · "
                         f"剩余 {free // (1024**3)} GB")
        except Exception as exc:
            parts.append(f"（磁盘信息失败: {exc}）")
        return "\n".join(parts)

    if include in ("all", "cpu"):
        parts.append("## CPU")
        parts.append(f"物理核: {psutil.cpu_count(logical=False)}  "
                     f"逻辑核: {psutil.cpu_count(logical=True)}")
        pct = psutil.cpu_percent(interval=0.5)
        parts.append(f"使用率: {pct:.1f}%")
        try:
            freq = psutil.cpu_freq()
            if freq:
                parts.append(f"频率: {freq.current:.0f} MHz")
        except Exception:
            pass
        try:
            load = psutil.getloadavg()
            parts.append(f"负载: {load[0]:.2f} {load[1]:.2f} "
                         f"{load[2]:.2f}")
        except Exception:
            pass

    if include in ("all", "memory"):
        parts.append("\n## 内存")
        vm = psutil.virtual_memory()
        parts.append(f"总计 {vm.total // (1024**3)} GB · "
                     f"已用 {vm.used // (1024**3)} GB "
                     f"({vm.percent}%) · "
                     f"可用 {vm.available // (1024**3)} GB")
        try:
            sw = psutil.swap_memory()
            parts.append(f"Swap: {sw.used // (1024**3)} / "
                         f"{sw.total // (1024**3)} GB "
                         f"({sw.percent}%)")
        except Exception:
            pass

    if include in ("all", "disk"):
        parts.append("\n## 磁盘")
        try:
            home_disk = Path.home().drive or "/"
            usage = psutil.disk_usage(home_disk)
            parts.append(f"{home_disk} 总计 "
                         f"{usage.total // (1024**3)} GB · "
                         f"已用 {usage.used // (1024**3)} GB "
                         f"({usage.percent}%) · "
                         f"剩余 {usage.free // (1024**3)} GB")
        except Exception as exc:
            parts.append(f"（磁盘信息失败: {exc}）")

    if include in ("all", "network"):
        parts.append("\n## 网络")
        try:
            io = psutil.net_io_counters()
            parts.append(f"发送 {io.bytes_sent // (1024**2)} MB · "
                         f"接收 {io.bytes_recv // (1024**2)} MB")
        except Exception:
            pass
        try:
            for name, snic in psutil.net_if_stats().items():
                status = "up" if snic.isup else "down"
                parts.append(f"  {name}: {status} · "
                             f"{snic.speed} Mbps")
        except Exception:
            pass

    return "\n".join(parts)