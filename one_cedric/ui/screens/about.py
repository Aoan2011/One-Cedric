"""关于界面：版本 + 依赖检查。"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn,
)
from rich.table import Table

from ...config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C, BETA_VERSION
from ..keys import wait_for_return


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


def run_about_screen(console: Console, copilot) -> None:
    console.clear()
    console.print()
    console.print(f"  [bold {BRAND}]◆ One Cedric {BETA_VERSION}[/]")
    console.print()
    console.print(Panel(
        f"[dim]本地文件助手 · Claude Code 风格 · GPL-3.0[/]\n"
        f"[dim]模型: [/][accent]{copilot.model}[/]  "
        f"[dim]主机: [/][accent]{copilot.host}[/]\n"
        f"[dim]工作目录: [/][accent]{copilot.root}[/]",
        border_style=BRAND,
        padding=(0, 1),
        expand=False,
    ))
    console.print()

    # 依赖检查
    tbl = Table(box=None, padding=(0, 1))
    tbl.add_column("状态", justify="center", width=4)
    tbl.add_column("包名", style="bold")
    tbl.add_column("用途", style="dim")
    tbl.add_column("版本", style="dim")

    missing_core = []
    missing_optional = []

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
                mod = __import__(name)
                ver = getattr(mod, "__version__", "")
                if not ver and name == "PIL":
                    from PIL import __version__ as _v
                    ver = _v
                if not ver and name == "docx":
                    ver = getattr(mod, "__version__", "")
                if not ver and name == "pptx":
                    ver = getattr(mod, "__version__", "")
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

    if missing_core:
        console.print(f"  [err]✗ 缺少核心依赖：{', '.join(missing_core)}[/]")
        console.print(f"  [dim]安装：pip install {' '.join(missing_core)}[/]")
    else:
        console.print(f"  [ok]✓ 核心依赖完整[/]")

    if missing_optional:
        console.print(f"  [dim]· 可选依赖缺失 {len(missing_optional)} 个"
                      f"（不影响基础功能）[/]")

    console.print()
    console.print("  [dim]提示：[/][accent]/tools[/][dim] 查看工具，[/]"
                  "[accent]/model[/][dim] 查看模型设置[/]")
    console.print()
    wait_for_return(console)