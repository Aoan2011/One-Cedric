"""Python code execution.

用途：让 AI 写一段 Python 做数据分析、画图表、算法验证、文本处理。

执行会在子进程中运行并受超时限制。CLI 每次运行前都会请求确认；
获准后不再通过 AST 导入或函数白名单限制 Python 代码。
"""
from __future__ import annotations

import ast
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .sandbox import _as_int, _resolve_path


# 允许的第三方库（用于白名单提示 AI）
ALLOWED_LIBS = [
    "numpy", "pandas", "matplotlib", "PIL", "scipy",
    "sklearn", "sympy", "seaborn", "plotly", "csv", "json",
    "re", "math", "statistics", "datetime", "collections", "itertools",
    "functools", "random", "string", "textwrap", "hashlib",
    "base64", "uuid", "decimal", "fractions", "cmath", "heapq",
    "bisect", "array", "copy", "pprint", "traceback", "warnings",
]


def _scan_code(code: str) -> str:
    """Validate Python syntax without imposing an import or call allowlist."""
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return f"ERROR: 语法错误 第 {exc.lineno} 行: {exc.msg}"
    return ""


def _build_prelude(work_dir: str, artifact_dir: str) -> str:
    """注入一段前置代码：配置 matplotlib 无头 + 设定工作目录。"""
    prelude = f'''
import sys as _sys
import os as _os

_WORK_DIR = {work_dir!r}
_ARTIFACT_DIR = {artifact_dir!r}

_os.makedirs(_ARTIFACT_DIR, exist_ok=True)
_os.chdir(_WORK_DIR)

# matplotlib 无头配置（若已导入）
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
    _plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "SimHei"]
    _plt.rcParams["axes.unicode_minus"] = False
except Exception:
    pass

import warnings as _warnings
_warnings.filterwarnings("ignore")

'''
    return prelude


def _build_postlude(artifact_dir: str) -> str:
    """保存所有未 savefig 的 matplotlib figure。

    注意：路径统一用 {artifact_dir!r} 的 repr 嵌入（Windows 反斜杠安全），
    避免 f-string 嵌套把路径塞进字符串字面量造成转义错误。
    """
    postlude = f'''
# 保存所有未关闭的 matplotlib figure
try:
    import matplotlib.pyplot as _plt
    _fignums = _plt.get_fignums()
    for _i, _num in enumerate(_fignums, 1):
        _f = _plt.figure(_num)
        _f.savefig(
            _os.path.join({artifact_dir!r}, "figure_" + str(_i) + ".png"),
            dpi=120, bbox_inches="tight"
        )
except Exception:
    pass

# 打印生成的文件列表
try:
    import os as _os
    _files = sorted(_os.listdir({artifact_dir!r}))
    if _files:
        print()
        print("=== ARTIFACTS ===")
        for _f in _files:
            _p = _os.path.join({artifact_dir!r}, _f)
            _sz = _os.path.getsize(_p)
            print(_f + "|" + str(_sz))
except Exception:
    pass
'''
    return postlude


def _scan_imports(code: str) -> list[str]:
    """提取代码里 import 的顶层模块名（不含禁用的）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module.split(".")[0])
    return sorted(set(m for m in mods if m))


def _install_packages(packages: list) -> str:
    """用 pip 安装包。返回错误信息，成功返回空串。"""
    if not packages:
        return ""
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + list(packages)
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: pip install 超时（{' '.join(packages)}）"
    except OSError as exc:
        return f"ERROR: pip 执行失败: {exc}"
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip()[-500:]
        return f"ERROR: pip install 失败: {tail}"
    return ""


def python_exec_preview(code: str, work_dir: str = ".",
                        timeout: int = 30,
                        save_code: bool = False,
                        install_packages: list | None = None,
                        auto_install: bool = False,
                        root: Path | None = None):
    """返回 (preview, needs_confirm, error, meta)。

    - 直接执行不落盘，但会生成 artifact 文件（图表）。
    - save_code=True 时把代码存到工作目录。
    - 扫描非白名单第三方模块 → meta["unknown_modules"] / install_list。
    """
    meta: dict = {"unknown_modules": [], "install_list": []}
    if root is None:
        return "", False, "ERROR: 需要 root", meta
    if not code or not code.strip():
        return "", False, "ERROR: code 不能为空", meta

    err = _scan_code(code)
    if err:
        return "", False, err, meta

    try:
        t = max(3, min(int(timeout), 300))
    except (TypeError, ValueError):
        t = 30

    wd = str(_resolve_path(root, work_dir)[0]) if work_dir else str(root)

    # 统计行数
    n_lines = len(code.strip().splitlines())

    # 扫描未知第三方模块（非白名单、非标准库）
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    unknown = [m for m in _scan_imports(code)
               if m not in ALLOWED_LIBS and m not in stdlib]
    meta["unknown_modules"] = unknown

    user_pkgs = [p for p in (install_packages or [])
                 if isinstance(p, str) and p.strip()]
    install_list = list(dict.fromkeys(unknown + user_pkgs))
    meta["install_list"] = install_list

    needs_confirm = bool(install_list) and not auto_install

    preview = [
        f"执行 {n_lines} 行 Python 代码",
        f"工作目录: {work_dir or '.'}",
        f"超时: {t}s",
    ]
    if install_list:
        preview.append(f"将安装: {' '.join(install_list)}")
    if save_code:
        preview.append("同时保存代码到脚本文件")

    # 显示代码前 30 行
    preview.append("")
    preview.append("--- 代码 ---")
    lines = code.splitlines()
    show = lines[:30]
    for i, line in enumerate(show, 1):
        preview.append(f"{i:>3}| {line}")
    if len(lines) > 30:
        preview.append(f"    ... 还有 {len(lines) - 30} 行")

    # 是写操作吗？
    is_write = bool(save_code)
    return "\n".join(preview), needs_confirm, "", meta


def python_exec_apply(code: str, work_dir: str = ".", timeout: int = 30,
                      save_code: bool = False, root: Path | None = None,
                      progress_cb=None, install_packages: list | None = None
                      ) -> str:
    """执行代码。返回 stdout + 生成文件。"""
    if install_packages:
        pkg_err = _install_packages(install_packages)
        if pkg_err:
            return pkg_err

    try:
        t = max(3, min(int(timeout), 300))
    except (TypeError, ValueError):
        t = 30

    wd = str(_resolve_path(root, work_dir)[0]) if work_dir else str(root)
    Path(wd).mkdir(parents=True, exist_ok=True)

    artifact_name = f".cedric_artifacts/{secrets.token_hex(4)}"
    artifact_dir = os.path.join(wd, artifact_name)

    # 组装完整脚本
    prelude = _build_prelude(wd, artifact_dir)
    postlude = _build_postlude(artifact_dir)
    full_code = prelude + "\n" + code + "\n" + postlude

    # 写临时文件
    script_path = None
    try:
        fd, script_path = tempfile.mkstemp(prefix="cedric_exec_",
                                            suffix=".py",
                                            dir=wd)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(full_code)
    except OSError as exc:
        return f"ERROR: 无法创建临时脚本: {exc}"

    # 环境变量
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = os.path.join(wd, ".cedric_artifacts", ".mpl")
    Path(env["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-u", script_path],
            cwd=wd, env=env,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=t,
        )
    except subprocess.TimeoutExpired:
        _cleanup_script(script_path)
        return f"ERROR: 执行超时（>{t}s）"
    except OSError as exc:
        _cleanup_script(script_path)
        return f"ERROR: 执行失败: {exc}"
    finally:
        if not save_code:
            _cleanup_script(script_path)
        else:
            # 用户想保留代码：改名为 user_script.py
            try:
                final = os.path.join(wd, "cedric_script.py")
                if os.path.exists(final):
                    os.remove(final)
                os.rename(script_path, final)
                _rename_msg = final
            except OSError:
                _cleanup_script(script_path)

    elapsed = time.time() - t0

    stdout = (r.stdout or "").rstrip()
    stderr = (r.stderr or "").rstrip()

    # 提取 artifact 列表
    artifacts = []
    if "=== ARTIFACTS ===" in stdout:
        out_lines = stdout.split("=== ARTIFACTS ===")
        stdout = out_lines[0].rstrip()
        meta = out_lines[1].strip()
        for line in meta.splitlines():
            line = line.strip()
            if "|" in line:
                name, _, size = line.partition("|")
                artifacts.append((name, size))

    # 输出限制
    MAX_OUT = 30000
    if len(stdout) > MAX_OUT:
        stdout = stdout[:MAX_OUT] + f"\n...（stdout 截断，原始 {len(stdout)} 字符）"
    if len(stderr) > 10000:
        stderr = stderr[:10000] + f"\n...（stderr 截断）"

    # 组装结果
    parts = [f"退出码: {r.returncode}   耗时: {elapsed:.2f}s"]

    if stdout:
        parts.append(f"--- stdout ---\n{stdout}")
    if stderr:
        parts.append(f"--- stderr ---\n{stderr}")

    if artifacts:
        parts.append("")
        parts.append(f"--- 生成文件（{len(artifacts)} 个） ---")
        for name, size in artifacts:
            try:
                sz = int(size)
            except ValueError:
                sz = 0
            parts.append(f"  {artifact_name}/{name}  {sz} bytes")
        parts.append("")
        parts.append("提示：图片文件可用 image_info 查看，或用 read_file 读取生成的文本/CSV。")

    if r.returncode != 0 and not stderr:
        parts.append("（无 stderr，但退出码非 0）")

    # 清理空 artifact 目录
    try:
        if os.path.isdir(artifact_dir) and not os.listdir(artifact_dir):
            os.rmdir(artifact_dir)
    except OSError:
        pass

    return "\n".join(parts)


def _cleanup_script(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def python_libs() -> str:
    """列出当前环境里可用于 python_exec 的库及版本。"""
    lines = ["python_exec 可用库：", ""]
    for name in ALLOWED_LIBS:
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "")
            if ver:
                lines.append(f"  ✓ {name:<16} {ver}")
            else:
                lines.append(f"  ✓ {name}")
        except ImportError:
            lines.append(f"  ✗ {name:<16} (未安装)")
    lines.append("")
    lines.append("如需安装：pip install numpy pandas matplotlib scipy scikit-learn seaborn plotly")
    lines.append("")
    lines.append("运行前会请求授权；获准后代码使用当前 Python 环境权限。")
    lines.append("  - 脚本在独立子进程中执行，并受超时限制")
    lines.append("  - 所有相对路径基于工作目录")
    lines.append("  - matplotlib 图表自动保存到 .cedric_artifacts/")
    return "\n".join(lines)


def python_check(code: str) -> str:
    """Check Python syntax and report imports without executing the code."""
    if not code or not code.strip():
        return "ERROR: code 不能为空"
    err = _scan_code(code)
    if err:
        return err

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"ERROR: 语法错误 第 {exc.lineno} 行: {exc.msg}"

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    defs = [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]

    lines = ["✓ 语法检查通过"]
    if imports:
        lines.append("")
        lines.append("imports:")
        for m in sorted(set(imports)):
            lines.append(f"  {m}")
    if defs:
        lines.append("")
        lines.append(f"定义（{len(defs)}）：")
        for d in defs[:20]:
            lines.append(f"  {d}")

    return "\n".join(lines)