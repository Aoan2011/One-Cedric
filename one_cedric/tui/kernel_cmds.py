"""Shell C：slash 命令与内核的直连层。

CLI 的 REPL 循环（core.py:7441 起）有 ~50 条 `/` 命令。TUI 的原则是
**不复制第二份分发逻辑**：不管 CLI 还是 TUI，命令最终调用的都是
同一批内核方法（``_handle_*`` / ``_cmd_*`` / ``_do_*`` / 属性直改）。
TUI 只做两件外壳的事：

1. 输出 —— 内核方法往 ``copilot.console`` 打 Rich 内容；这里把
   console 换成一个捕获 Console，跑完把文本作为弹层展示；
2. 输入 —— 需要现场按键的路径（Rich 交互屏、confirm_yes_no）在
   TUI 里显式降级：确认类先守住并给出替代用法（确认弹窗在后续
   批次），绝不阻塞 worker 线程的 stdin。

``dispatch`` 返回的指令种类：

* ``notify``    纯提示，不开弹层不开线程；
* ``confirm``   需要确认弹窗才能安全继续（当前批次先守住）；
* ``modal``     在捕获 Console 里跑 ``fn``，结果作为弹层展示；
  ``busy_safe=True`` 表示只读、流式中也允许跑；
* ``send``      转成一条用户消息走正常流式（/upload、@ 引用）。

对齐清单：``tests/test_tui_commands.py`` 有一条 CLI↔TUI 命令对的
parity 断言，两边漂移它先红。
"""
from __future__ import annotations

import json
from typing import Callable

CAPTURE_WIDTH = 96

#: 这里登记的 slash 名由 kernel_cmds 直连内核；其余（/new /clear /stats
#: 等纯 UI 命令）仍走 commands.py 的 SLASH_ALIASES → 面板命令。
SLASH = frozenset({
    "resume", "save-as", "export", "model", "models", "think", "mode",
    "yes", "shell",
    "sandbox", "computer", "tools", "allow", "plan", "todos", "history",
    "diff", "tag", "untag", "undo", "rollback", "snapshots", "replay",
    "audit", "cache", "compact", "config", "save-config", "profile", "lang",
    "jobs", "log", "kill", "amap-key", "email-key", "email", "office-check",
    "agent", "review", "mem", "cron", "dream", "asks", "pricing", "peak",
    "cost", "budget", "dog", "upload",
})


# ---------------------------------------------------------------- 运行 #
def run_captured(copilot, fn: Callable) -> str:
    """把 ``copilot.console`` 换成捕获 Console 跑一段内核逻辑。

    终端宽度取 CAPTURE_WIDTH；色彩/emoji 关掉，文本纯净，装进弹层
    不花哨也不花屏。异常不入抛出路径，直接写进结果（内核方法的
    局部失败不该炸掉整个界面）。
    """
    import io

    from ..ui.console import CedricConsole

    buf = io.StringIO()
    capture = CedricConsole(
        file=buf, width=CAPTURE_WIDTH, emoji=False, highlight=False,
        color_system=None, legacy_windows=False,
    )
    old = getattr(copilot, "console", None)
    swapped = old is not None
    if swapped:
        copilot.console = capture
    try:
        fn(copilot)
    except Exception as exc:
        try:
            capture.print(f"[err]✗ 命令执行失败: {exc}[/]")
        except Exception:
            pass
    finally:
        if swapped:
            copilot.console = old
    value = buf.getvalue()
    return value.rstrip() + "\n" if value.strip() else ""


def _modal(label: str, busy_safe: bool, fn: Callable) -> dict:
    return {"kind": "modal", "label": label, "busy_safe": busy_safe,
            "fn": fn}


def _notify(text: str) -> dict:
    return {"kind": "notify", "text": text}


def _confirm(text: str) -> dict:
    return {"kind": "confirm", "text": text}


def _send(text: str) -> dict:
    return {"kind": "send", "text": text}


# -------------------------------------------------------------- 分发 #
def dispatch(engine, line: str) -> dict:
    """解析一条 slash 行，返回 app 可执行的指令。不触碰内核实例。

    真正的懒构造（import core / 建 OneCedric）发生在 ``modal`` 路径
    的 worker 线程里（跑 ``engine.copilot``），UI 线程零阻塞。
    """
    text = " ".join(line.split())
    if not text.startswith("/"):
        return _send(text)
    head, _, rest0 = text.partition(" ")
    head = head.lower()
    rest = rest0.strip()
    parts = [p for p in (rest.split() if rest else [])]

    # ── 转消息类（走正常流式回合） ────────────────────────────
    if head == "/upload":
        return upload_message(engine, rest0)

    # ── 确认守卫（TUI 确认弹窗介入前的临时提示） ─────────────
    if head == "/mem" and parts and parts[0].lower() in ("clear", "batch",
                                                         "batch-delete"):
        return _confirm("TUI 确认弹窗未上线：请用 CLI 执行 "
                        "`/mem clear` / `/mem batch`")
    if head == "/asks" and parts and parts[0].lower() == "clear":
        return _confirm("TUI 确认弹窗未上线：请用 CLI 执行 `/asks clear`")

    # ── 会话 ──────────────────────────────────────────────────
    if head == "/resume":
        return _modal("resume", False,
                      lambda cp: cp._do_resume(rest))
    if head == "/save-as":
        return _modal("save as", False,
                      lambda cp: cp._do_save_as(rest))
    if head == "/export":
        return _modal("export", False,
                      lambda cp: cp._export_session(rest or None))
    if head in ("/model", "/models"):
        if not rest:
            return _notify("/model <name> 直接切换；交互选择器稍后提供")
        def _set_model(cp, _v=rest):
            cp.model = _v
            cp.messages = [cp.system_msg]
            cp.console.print(
                f"[dim]已切换模型：[/][accent]{_v}[/]")
            cp._save_session()
        return _modal("model", False, _set_model)

    # ── 内核开关（改状态，流式中一律拒绝） ────────────────────
    if head == "/think":
        rest = rest.lower()
        if rest and rest not in _think_levels():
            return _notify(f"未知思考档位: {rest}"
                           f"（可选 {'/'.join(_think_levels())}）")
        def _think(cp, _v=rest):
            from ..config import THINK_LEVELS
            from ..core import THINK_LEVEL_DESC
            if not _v:
                cur = cp.think_level
                cp.console.print(
                    f"[dim]当前思考模式：[/][accent]{cur}[/]  "
                    f"[dim]（{THINK_LEVEL_DESC.get(cur, '')}）[/]")
                cp.console.print("[dim]可选项：[/]" + "  ".join(
                    f"[accent]{lv}[/]" for lv in THINK_LEVELS))
                return
            cp.think_level = _v
            cp.console.print(f"[ok]✓ 思考模式：[/][accent]{_v}[/]")
        return _modal("think", not rest, _think)
    if head == "/reasoning":
        def _reasoning(cp, _a=parts):
            if not _a:
                cp.show_reasoning = not cp.show_reasoning
            else:
                arg = _a[0].lower()
                if arg in ("on", "true", "1", "yes"):
                    cp.show_reasoning = True
                elif arg in ("off", "false", "0", "no"):
                    cp.show_reasoning = False
            cp.console.print(
                f"[dim]显示思考过程："
                f"{'开启' if cp.show_reasoning else '关闭'}[/]")
        return _modal("reasoning", False, _reasoning)
    if head == "/mode":
        if not rest:
            def _mode_report(cp):
                from ..config import ACCESS_MODES, ACCESS_MODE_DESC
                cur = getattr(cp, "access_mode", "ask")
                cp.console.print(
                    f"[dim]当前访问模式：[/][accent]{cur}[/]  "
                    f"[dim]（{ACCESS_MODE_DESC.get(cur, '')}）[/]")
                for m in ACCESS_MODES:
                    cp.console.print(
                        f"  [accent]{m:<14}[/] [dim]{ACCESS_MODE_DESC[m]}[/]")
            return _modal("mode", True, _mode_report)
        def _mode_set(cp, _v=rest):
            from ..config import ACCESS_MODE_ALIASES, ACCESS_MODES
            from ..tools.sandbox import set_access_mode
            arg = ACCESS_MODE_ALIASES.get(_v, _v)
            if arg not in ACCESS_MODES:
                cp.console.print(f"[err]✗ 未知模式: {_v}[/]")
                return
            cp.access_mode = arg
            set_access_mode(arg)
            cp.config.setdefault("default", {})["mode"] = arg
            cp.console.print(f"[ok]✓ 访问模式：[/][accent]{arg}[/]")
        return _modal("mode", False, _mode_set)
    if head == "/yes":
        def _yes(cp):
            cp.auto_yes = not cp.auto_yes
            cp.console.print(
                f"[dim]自动确认写操作："
                f"{'开启' if cp.auto_yes else '关闭'}[/]")
        return _modal("yes", False, _yes)
    if head == "/shell":
        def _shell(cp, _a=parts):
            arg = _a[0].lower() if _a else ""
            if arg in ("on", "enable"):
                cp.allow_arbitrary_shell = True
                cp.console.print("[ok]✓ 任意 shell 命令：开启[/]")
            elif arg in ("off", "disable"):
                cp.allow_arbitrary_shell = False
                cp.console.print("[dim]任意 shell 命令：关闭[/]")
            elif arg == "clear":
                n = len(getattr(cp, "session_allowed_cmds", []) or [])
                getattr(cp, "session_allowed_cmds", set()).clear()
                cp.console.print(f"[ok]✓ 已清除 {n} 条会话允许命令[/]")
            else:
                cp.console.print(
                    f"[dim]任意 shell 命令："
                    f"{'开启' if cp.allow_arbitrary_shell else '关闭'}[/]")
        return _modal("shell", not bool(parts), _shell)
    if head == "/sandbox":
        def _sandbox(cp, _a=parts):
            arg = _a[0].lower() if _a else ""
            if arg in ("on", "enable"):
                cp.sandbox_terminal = True
                cp.console.print("[ok]✓ 沙箱终端：开启[/]")
            elif arg in ("off", "disable"):
                cp.sandbox_terminal = False
                cp.console.print("[dim]沙箱终端：关闭（命令将直接执行）[/]")
            else:
                cp.console.print(
                    f"[dim]沙箱终端："
                    f"{'开启' if cp.sandbox_terminal else '关闭'}[/]")
        return _modal("sandbox", not bool(parts), _sandbox)
    if head == "/computer":
        def _computer(cp, _a=parts):
            arg = _a[0].lower() if _a else ""
            policy = getattr(cp, "_computer_policy", None)
            if arg in ("on", "enable") and policy is not None:
                policy.enabled = True
                cp.console.print("[ok]✓ Computer use 已开启[/]")
            elif arg in ("off", "disable") and policy is not None:
                policy.enabled = False
                cp.console.print("[dim]Computer use 已关闭[/]")
            else:
                cur = bool(getattr(policy, "enabled", False)) \
                    if policy is not None else False
                cp.console.print(f"[dim]Computer use 当前："
                                 f"{'开启' if cur else '关闭'}[/]")
        return _modal("computer use", not bool(parts), _computer)

    # ── 工具 / 权限 ──────────────────────────────────────────
    if head == "/tools":
        sub = parts[0].lower() if parts else ""
        report = sub in ("", "list")
        def _tools(cp, _rest=rest0):
            if not _rest.strip():
                cp._tools_list()
            else:
                cp._cmd_tools_sub(_rest.strip())
        return _modal("tools", report, _tools)
    if head == "/allow":
        def _allow(cp):
            from ..ui.legacy import allow_table
            allow_table(cp.console)
        return _modal("allow", True, _allow)
    if head == "/plan":
        sub = rest.lower() if rest else ""
        mode = {"": "action", "on": "action", "start": "action",
                "off": "action", "exit": "action", "stop": "action",
                "show": "report"}.get(sub, "action")
        def _plan(cp, _a=sub):
            cp._cmd_plan(_a)
        return _modal("plan", mode == "report", _plan)

    # ── 报表 / 历史 ──────────────────────────────────────────
    if head == "/todos":
        return _modal("todos", True, lambda cp: cp._cmd_todos())
    if head == "/history":
        return _modal("history", True, lambda cp: cp._print_history())
    if head == "/diff":
        return _modal("diff", False, lambda cp: cp._do_diff(rest))
    if head == "/tag":
        return _modal("tag", False, lambda cp: cp._cmd_tag(rest))
    if head == "/untag":
        return _modal("untag", False, lambda cp: cp._cmd_untag(rest))
    if head == "/undo":
        def _undo(cp):
            cp._do_undo()
            cp._save_session()
        return _modal("undo", False, _undo)
    if head == "/rollback":
        def _rollback(cp):
            cp._do_rollback()
            cp._save_session()
        return _modal("rollback", False, _rollback)
    if head == "/snapshots":
        return _modal("snapshots", True, lambda cp: cp._print_snapshots())
    if head == "/replay":
        return _modal("replay", False, lambda cp: cp._do_replay(rest))
    if head == "/audit":
        return _modal("audit", not rest, lambda cp: cp._cmd_audit(rest))
    if head == "/cache":
        return _modal("cache", not rest,
                      lambda cp: cp._handle_cache_command(rest))
    if head == "/compact":
        keep = int(parts[0]) if parts and parts[0].isdigit() else None
        if parts and keep is None:
            return _notify("参数必须是数字：/compact [保留轮数]")
        def _compact(cp, _k=keep):
            cp._compact(keep_turns=_k)
        return _modal("compact", False, _compact)
    if head == "/config":
        return _modal("config", True, lambda cp: cp._print_config())
    if head == "/save-config":
        scope = rest.lower() or "global"
        return _modal("save config", False,
                      lambda cp: cp._save_config(scope))
    if head == "/profile":
        return _modal("profile", not rest, lambda cp: cp._cmd_profile(rest))
    if head == "/lang":
        return _lang(parts)

    # ── 后台进程 / 集成 ──────────────────────────────────────
    if head == "/jobs":
        return _modal("jobs", True, lambda cp: cp._cmd_jobs())
    if head in ("/log", "/kill"):
        if not parts:
            return _notify(f"用法：{head} <pid>（/jobs 查看）")
        if head == "/log":
            return _modal("log", True, lambda cp: cp._cmd_log(parts[0]))
        return _modal("kill", False, lambda cp: cp._cmd_kill(parts[0]))
    if head == "/amap-key":
        if not parts:
            def _amap(cp):
                from ..tools import amap_key_status
                cp.console.print(f"[dim]{amap_key_status()}[/]")
            return _modal("map key", True, _amap)
        def _amap_set(cp, _k=rest):
            from ..tools import _set_amap_key
            _set_amap_key(_k)
            cp.config.setdefault("amap", {})["api_key"] = _k
            cp._save_config("global")
            cp.console.print("[ok]✓ AMAP API Key 已设置[/]")
        return _modal("map key", False, _amap_set)
    if head == "/email-key":
        if len(parts) < 2:
            return _notify("用法：/email-key <account> <password>")
        def _email_key(cp, _a=parts):
            from ..tools import _reset_email_accounts, _set_email_password
            _set_email_password(_a[0], _a[1])
            _reset_email_accounts()
            cp.console.print(
                f"[ok]✓ 账号 '{_a[0]}' 密码已设置[/]")
        return _modal("email key", False, _email_key)
    if head == "/email":
        sub = parts[0].lower() if parts else ""
        if not sub:
            def _email(cp):
                from ..tools import email_config_status
                cp.console.print(email_config_status())
            return _modal("email", True, _email)
        def _email_reload(cp, _s=sub):
            from ..tools import _reset_email_accounts
            _reset_email_accounts()
            cp.console.print("[ok]✓ 邮箱配置已重新加载[/]")
        return _modal("email", False, _email_reload)
    if head == "/office-check":
        return _modal("office deps", True, _office_check)

    # ── 子 agent / 审查 ─────────────────────────────────────
    if head == "/agent":
        return _agent(rest0)
    if head == "/review":
        return _review(rest0)

    # ── 委托给内核 _handle_* 的参数型命令 ────────────────────
    if head == "/cron":
        sub = parts[0].lower() if parts else ""
        return _modal("cron", sub in ("", "list"),
                      lambda cp: cp._handle_cron_command(text))
    if head == "/dream":
        sub = parts[0].lower() if parts else ""
        return _modal("dream", sub in ("", "list", "show"),
                      lambda cp: cp._handle_dream_command(text))
    if head == "/asks":
        sub = parts[0].lower() if parts else ""
        return _modal("asks", not sub,
                      lambda cp: cp._handle_asks_command(text))
    if head == "/mem":
        sub = parts[0].lower() if parts else ""
        report = sub in ("", "list", "search")
        return _modal("memory", report,
                      lambda cp: _mem_fallback(cp, text))
    if head == "/pricing":
        sub = parts[0].lower() if parts else ""
        return _modal("pricing", sub in ("", "list", "show"),
                      lambda cp: cp._handle_pricing_command(text))
    if head == "/peak":
        sub = parts[0].lower() if parts else ""
        return _modal("peak", sub in ("", "status", "show"),
                      lambda cp: cp._handle_peak_command(text))
    if head == "/cost":
        sub = parts[0].lower() if parts else ""
        return _modal("cost", sub in ("", "list", "show"),
                      lambda cp: cp._handle_cost_command(text))
    if head == "/budget":
        sub = parts[0].lower() if parts else ""
        return _modal("budget", sub in ("", "list", "show"),
                      lambda cp: cp._handle_budget_command(text))
    if head == "/dog":
        sub = parts[0].lower() if parts else ""
        return _modal("dog", sub in ("", "list", "show"),
                      lambda cp: cp._handle_dog_command(text))

    return _notify(f"not implemented: {head}")


# ------------------------------------------------------------- 助手 #
def _think_levels() -> tuple:
    from ..config import THINK_LEVELS
    return THINK_LEVELS


def _lang(parts: list) -> dict:
    if not parts:
        def _lang_report(cp):
            from ..i18n import t
            cp.console.print(f"[dim]{t('lang.current')}[/]")
        return _modal("lang", True, _lang_report)

    def _lang_set(cp, _v=parts[0]):
        from ..i18n import set_lang, t
        if set_lang(_v):
            cp.config.setdefault("default", {})["language"] = _v
            cp._save_config("global")
            cp.console.print(f"[ok]✓[/] {t('lang.switched')}")
        else:
            cp.console.print(f"[err]✗ {t('lang.usage')}[/]")
    return _modal("lang", False, _lang_set)


def _office_check(cp) -> None:
    deps = [
        ("docx", "python-docx"),
        ("pptx", "python-pptx"),
        ("openpyxl", "openpyxl"),
        ("pypdf", "pypdf"),
        ("msoffcrypto", "msoffcrypto-tool"),
        ("pdf2image", "pdf2image"),
        ("pytesseract", "pytesseract"),
        ("win32com", "pywin32"),
    ]
    cp.console.print("[bold]办公文档依赖检查[/]")
    for mod_name, pip_name in deps:
        try:
            __import__(mod_name)
            cp.console.print(f"  [ok]✓[/] {pip_name}")
        except ImportError:
            cp.console.print(
                f"  [err]✗[/] {pip_name}  [dim](pip install {pip_name})[/]")


def _agent(rest0: str) -> dict:
    """CLI /agent 的解析与执行（core.py 同款，flags 在任务后）。"""
    tokens = rest0.split()
    mode, steps, timeout = "explore", 6, 300
    task_tokens = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--mode" and i + 1 < len(tokens):
            mode = tokens[i + 1].lower()
            i += 2
            continue
        if t == "--steps" and i + 1 < len(tokens):
            try:
                steps = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if t == "--timeout" and i + 1 < len(tokens):
            try:
                timeout = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        task_tokens.append(t)
        i += 1
    task = " ".join(task_tokens).strip()
    if not task:
        return _notify("用法：/agent <任务描述> [--mode explore|code|plan] "
                       "[--steps N] [--timeout S]")

    def _run(cp):
        fake_tc = {
            "id": "slash_agent",
            "function": {
                "name": "spawn_agent",
                "arguments": json.dumps({
                    "task": task, "mode": mode,
                    "max_steps": steps, "timeout": timeout,
                }, ensure_ascii=False),
            },
        }
        args = {"task": task, "mode": mode, "max_steps": steps,
                "timeout": timeout}
        cp._handle_spawn_agent(fake_tc, args)
        last = cp.messages[-1] if cp.messages else {}
        if last.get("role") == "tool":
            from rich.box import box
            from rich.panel import Panel
            from rich.text import Text
            cp.console.print()
            cp.console.print(Panel(
                Text(last.get("content", ""), style=""),
                title="[bold]子 agent 结果[/]",
                title_align="left", border_style="cyan",
                box=box.ROUNDED, padding=(0, 1), expand=False,
            ))
            cp.messages.pop()
    return _modal("agent", False, _run)


def _review(rest0: str) -> dict:
    parts = rest0.split(maxsplit=2)
    if not parts or not parts[0].strip():
        return _notify("用法：/review <path> "
                       "[--dim security,performance,readability]")
    path = parts[0].strip()
    dims = None
    if len(parts) >= 2 and "--dim" in parts[1]:
        dims = [d.strip() for d in
                parts[1].split("--dim", 1)[1].strip().split(",") if d.strip()]

    def _run(cp):
        cp._subagent_depth = 1
        try:
            from ..tools.multi_review import multi_review as _mr
            r = _mr(path=path, root=cp.root, dimensions=dims,
                    max_steps=5, timeout=180, parent=cp)
        finally:
            cp._subagent_depth = 0
        cp.console.print()
        cp.console.print(r.get("summary", ""))
    return _modal("review", False, _run)


def _mem_fallback(cp, text: str) -> None:
    """CLI /mem 分支的最小复刻（无交互子集：list/add/rm/search）。

    clear / batch 需要现场确认，dispatch 已把它们守住，不会进来。
    """
    parts = text.split(maxsplit=3)
    sub = parts[1].strip().lower() if len(parts) >= 2 else ""
    from .. import memory as _mem
    if sub in ("", "list"):
        items = _mem.list_all()
        if not items:
            cp.console.print("[dim]暂无记忆。用 /mem add <key> <value>[/]")
            return
        for it in items[:50]:
            cp.console.print(
                f"[dim][{it.get('category', 'other')}/][/]"
                f" [bold]{it.get('key', '')}[/] = "
                f"{str(it.get('value', ''))[:60]}")
        cp.console.print(f"[dim]{_mem.stats()}[/]")
        return
    if sub == "add" and len(parts) >= 4:
        _mem.add(parts[2].strip(), parts[3].strip())
        cp.console.print(
            f"[ok]✓ 已记住 {parts[2].strip()} = {parts[3].strip()}[/]")
        return
    if sub in ("rm", "remove", "forget") and len(parts) >= 3:
        if _mem.remove(parts[2].strip()):
            cp.console.print(f"[ok]✓ 已删除 '{parts[2].strip()}'[/]")
        else:
            cp.console.print(f"[err]✗ 未找到 '{parts[2].strip()}'[/]")
        return
    if sub == "search" and len(parts) >= 3:
        items = _mem.search(parts[2].strip())
        for it in items:
            cp.console.print(
                f"[{it.get('category')}] {it.get('key')} = "
                f"{str(it.get('value'))}")
        if not items:
            cp.console.print("[dim]无匹配[/]")
        return
    cp.console.print(
        "[dim]用法：/mem [list|add <k> <v>|rm <k>|search <q>][/]"
        "（clear / batch 需要 CLI）")


def upload_message(engine, rest0: str) -> dict:
    """/upload <路径...>：与 CLI 相同 —— 立即作为一条消息触发模型分析。"""
    paths = rest0.strip()
    if not paths:
        return _notify("用法：/upload <路径...>（支持 @ 行范围/目录/递归）")
    from ..at_ref import build_attachment
    cp = engine.copilot
    blocks = []
    warnings = []
    ok_paths = []
    for t in paths.split():
        block, warn = build_attachment(cp.root, t)
        if block:
            blocks.append(block)
            ok_paths.append(t)
        else:
            warnings.append(warn or f"{t}: 无法读取")
    if not blocks:
        return _notify("没有可上传的文件："
                       + ("; ".join(warnings) if warnings else ""))
    header = "[用户通过 /upload 上传的文件]\n\n" + "\n\n".join(blocks)
    return _send(header)


def expand_at(engine, text: str) -> tuple[str, list[str]]:
    """输入行里的 ``@path`` 引用展开（CLI REPL 同款），返回去引用后的提示词。

    展开后的段落直接进消息体；返回的第二项是给用户的行外提示。
    """
    if "@" not in text:
        return text, []
    from ..at_ref import expand_at_refs
    cp = engine.copilot
    expanded, warnings, ref_ok = expand_at_refs(cp.root, text)
    notes = list(warnings)
    if ref_ok:
        notes.append("· 已附加引用: " + "  ".join(f"@{p}" for p in ref_ok))
    return expanded, notes
