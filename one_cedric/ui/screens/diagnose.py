"""诊断界面：依赖检查 + 运行环境 / 项目健康检查。

从旧的“关于”界面拆分而来：关于只保留项目信息，
依赖与其它检查合并到这里，作为主菜单首页的“诊断”入口。
"""
from __future__ import annotations

import importlib

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn,
)
from rich.table import Table

from ...config import (
    BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, BETA_VERSION,
    PROJECT_NAME, PROJECT_REPO, PROJECT_LICENSE,
)
from ..keys import wait_for_return

# 可选依赖清单：只读检查，不影响基础功能
DEPS = [
    ("requests", "HTTP 请求（核心）", True),
    ("rich", "终端渲染（核心）", True),
    ("readchar", "键盘输入（核心）", True),
    ("fastapi", "Gateway", False),
    ("uvicorn", "Gateway", False),
    ("pyyaml", "YAML 解析", False),
    ("pypdf", "PDF 处理", False),
    ("jsonschema", "JSON Schema", False),
    ("psutil", "系统指标", False),
    ("bs4", "网页解析", False),
    ("lxml", "网页解析（快）", False),
    ("trafilatura", "正文提取", False),
    ("readability", "正文提取（备）", False),
    ("docx", "Word 处理", False),
    ("pptx", "PPT 处理", False),
    ("openpyxl", "Excel 处理", False),
    ("msoffcrypto", "Office 加密", False),
    ("PIL", "图像处理", False),
    ("qrcode", "二维码", False),
    ("cv2", "图像处理（高级）", False),
    ("numpy", "数值计算", False),
    ("pandas", "数据分析", False),
    ("matplotlib", "图表绘制", False),
    ("sympy", "符号计算", False),
    ("jieba", "中文分词", False),
    ("opencc", "繁简转换", False),
    ("cryptography", "加密解密", False),
    ("pyzbar", "二维码识别", False),
    ("pytesseract", "OCR", False),
    ("pyautogui", "Computer Use", False),
    ("pyperclip", "剪贴板", False),
    ("pygetwindow", "窗口管理", False),
    ("psycopg2", "PostgreSQL", False),
    ("pymysql", "MySQL", False),
    ("pymongo", "MongoDB", False),
    ("py7zr", "7z 压缩", False),
    ("rarfile", "RAR 压缩", False),
    ("zstandard", "zstd 压缩", False),
    ("lz4", "lz4 压缩", False),
    ("brotli", "brotli 压缩", False),
    ("ruff", "代码检查", False),
    ("mypy", "类型检查", False),
    ("black", "代码格式化", False),
]


def _lsp_config_ok(copilot) -> bool:
    try:
        from ...lsp.config import default_lsp_config_path
        return bool(default_lsp_config_path().exists())
    except Exception:
        return False


def _check_dependencies(console: Console) -> tuple[list[str], list[str]]:
    """返回 (missing_core, missing_optional)。"""
    missing_core: list[str] = []
    missing_optional: list[str] = []
    tbl = Table(box=None, padding=(0, 1))
    tbl.add_column("状态", justify="center", width=4)
    tbl.add_column("包名", style="bold")
    tbl.add_column("用途", style="dim")
    tbl.add_column("版本", style="dim")

    with Progress(
        SpinnerColumn(style=BRAND),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=32, complete_style=ACCENT, finished_style=OK_C),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("正在检查依赖", total=len(DEPS))
        for name, desc, core in DEPS:
            try:
                mod = importlib.import_module(name)
                ver = getattr(mod, "__version__", "")
                if not ver and name == "PIL":
                    from PIL import __version__ as _v
                    ver = _v
                tbl.add_row(f"[{OK_C}]✓[/]", name, desc,
                            str(ver)[:20] if ver else "")
            except ImportError:
                if core:
                    missing_core.append(name)
                    tbl.add_row(f"[{ERR_C}]✗[/]", name, desc, "[err]核心[/]")
                else:
                    missing_optional.append(name)
                    tbl.add_row(f"[{DIM_C}]·[/]", name, desc, "[dim]未安装[/]")
            progress.advance(task)

    console.print(tbl)
    console.print()
    return missing_core, missing_optional


def _check_environment(console: Console, copilot) -> None:
    console.print(f"  [bold {BRAND}]运行环境[/]")
    tbl = Table(box=None, padding=(0, 1))
    tbl.add_column("检查项", style="dim")
    tbl.add_column("结果", style="accent")

    import sys

    def row(name, ok, detail, warn=False):
        mark = f"[{OK_C}]✓[/]" if ok else (f"[{WARN_C}]⚠[/]" if warn
                                           else f"[{ERR_C}]✗[/]")
        tbl.add_row(mark, name, f"{detail}")

    row("Python", True, sys.version.split()[0])
    row("Git", copilot.git_enabled,
        "可用" if copilot.git_enabled else "未检测到（快照/回滚不可用）",
        warn=not copilot.git_enabled)
    row("LSP 配置", _lsp_config_ok(copilot),
        "已生成" if _lsp_config_ok(copilot) else "缺失（将自动生成）",
        warn=not _lsp_config_ok(copilot))
    row("已注册工具", True,
        f"{len(copilot._current_tool_schemas)} 个")
    row("沙箱终端", copilot.sandbox_terminal,
        "开启" if copilot.sandbox_terminal else "关闭")
    try:
        from ...agents_skills import list_agents_skills
        _skills = list_agents_skills()
        row("第三方技能(~/.agents/skills)",
            True if _skills else False,
            (f"只读加载 {len(_skills)} 个技能（"
             + "、".join(s["name"] for s in _skills[:5])
             + ("…" if len(_skills) > 5 else "") + "）")
            if _skills else "未发现（技能由 agent 运行时安装）",
            warn=not _skills)
    except Exception as exc:
        row("第三方技能(~/.agents/skills)", False, f"检查失败: {exc}")
    row("访问模式", True, str(copilot.access_mode))
    row("配置(全局)", True, str(copilot.config_path))
    row("配置(项目)", True, str(copilot.project_config_path))
    row("会话保存", True, str(copilot.root))

    console.print(tbl)
    console.print()


def run_diagnose_screen(console: Console, copilot) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ 诊断 · {PROJECT_NAME} "
                  f"{BETA_VERSION}[/]")
    console.print()
    console.print(Panel(
        f"[dim]依赖与运行环境检查（原“关于”中的检查项已合并至此）[/]\n"
        f"[dim]仓库: [/][accent]{PROJECT_REPO}[/]  "
        f"[dim]协议: [/][accent]{PROJECT_LICENSE}[/]",
        border_style=BRAND,
        padding=(0, 1),
        expand=False,
    ))
    console.print()

    missing_core, missing_optional = _check_dependencies(console)

    if missing_core:
        console.print(f"  [err]✗ 缺少核心依赖：{', '.join(missing_core)}[/]")
        console.print(f"  [dim]安装：pip install {' '.join(missing_core)}[/]")
    else:
        console.print(f"  [ok]✓ 核心依赖完整[/]")

    if missing_optional:
        console.print(f"  [dim]· 可选依赖缺失 {len(missing_optional)} 个"
                      f"（不影响基础功能）[/]")
    console.print()

    _check_environment(console, copilot)

    console.print("  [dim]提示：[/][accent]/tools[/][dim] 查看工具，[/]"
                  "[accent]/model[/][dim] 查看模型设置[/]")
    console.print()
    wait_for_return(console)
