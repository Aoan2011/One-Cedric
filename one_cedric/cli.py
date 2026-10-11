"""命令行入口。"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .config import (
    ACCESS_MODE_ALIASES,
    ACCESS_MODES,
    DEFAULT_ACCESS_MODE,
    DEFAULT_API_KEY,
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_THINK_LEVEL,
    PROJECT_AUTHOR,
    PROJECT_LICENSE,
    PROJECT_LICENSE_NOTICE,
    PROJECT_NAME,
    PROJECT_REPO,
    PROJECT_VERSION,
    RELEASE_NAME,
    THINK_LEVELS,
)
from .core import OneCedric
from .storage import (
    apply_profile,
    compose_config,
    default_config_path,
    find_session_by_id_or_title,
    list_session_files,
    load_profile,
    profile_preset_tag,
    project_config_path,
)
from .tools.shell import merge_bash_prefixes


def _ensure_utf8_stdio() -> None:
    """把标准输出/错误切到 UTF-8，避免中文 Windows（GBK 代码页）下
    框线字符、破折号、emoji 触发 UnicodeEncodeError 或变成乱码。

    真正连在控制台上时 Python 已经是 UTF-8，这里主要覆盖重定向到文件 /
    管道的场景；``errors="replace"`` 保证无论如何都不会因为一个字符崩掉。
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc.replace("-", "").replace("_", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> None:
    from .winvt import enable_vt_terminal
    _ensure_utf8_stdio()
    enable_vt_terminal()

    parser = argparse.ArgumentParser(
        description="One Cedric - An AI agent for beginners",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("-m", "--model", default=DEFAULT_MODEL)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("-r", "--root", default=".")
    parser.add_argument("-p", "--prompt")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("-t", "--temperature", type=float, default=0.2)
    parser.add_argument("-y", "--yes", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--profile", metavar="NAME")
    parser.add_argument("--resume", metavar="ID")
    parser.add_argument("--list-sessions", action="store_true")

    parser.add_argument("--mode", default=None,
                        help="访问模式: allow | ask | assisted")

    preset = parser.add_mutually_exclusive_group()
    preset.add_argument("--safe", action="store_true",
                        help="等同 --mode ask")
    preset.add_argument("--yolo", action="store_true",
                        help="等同 --mode allow")

    parser.add_argument("--no-reasoning", action="store_true")
    parser.add_argument("--show-reasoning", action="store_true")
    parser.add_argument("--think", default=None, choices=list(THINK_LEVELS))
    parser.add_argument("--enable-computer-use", action="store_true")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--shell-any", action="store_true")
    parser.add_argument("--save-config", action="store_true")

    parser.add_argument("--no-menu", action="store_true")
    parser.add_argument("--chat", action="store_true")

    sandbox_grp = parser.add_mutually_exclusive_group()
    sandbox_grp.add_argument("--sandbox-terminal", dest="sandbox_terminal",
                             action="store_true", default=None,
                             help="shell 工具在沙箱终端中运行（默认开）")
    sandbox_grp.add_argument("--no-sandbox-terminal",
                             dest="sandbox_terminal", action="store_false",
                             help="关闭 shell 工具沙箱终端")

    parser.add_argument("--license", action="store_true",
                        help="显示许可证信息")
    parser.add_argument("--version", action="store_true",
                        help="显示版本与项目信息")

    parser.add_argument("--cron-daemon", action="store_true",
                        help="启动时自动运行 cron 调度器")

    gw_grp = parser.add_argument_group("gateway")
    gw_grp.add_argument("--gateway", "--gw", dest="gateway",
                        action="store_true",
                        help="启动 WebUI 网关并保持运行（Ctrl+C 停止）")
    gw_grp.add_argument("--bind", default=None, metavar="ADDR",
                        help="网关绑定地址（默认取配置，通常 127.0.0.1）")
    gw_grp.add_argument("--port", type=int, default=None, metavar="PORT",
                        help="网关端口（默认取配置，通常 2043）")
    gw_grp.add_argument("--token", default=None, metavar="SECRET",
                        help="网关 Bearer token（不设则不鉴权）")

    args = parser.parse_args()

    if args.license:
        print(PROJECT_LICENSE_NOTICE)
        return

    if args.version:
        print(f"{PROJECT_NAME} {PROJECT_VERSION} ({RELEASE_NAME})")
        print(f"An AI agent for beginners — built by {PROJECT_AUTHOR}.")
        print(f"Repository: {PROJECT_REPO}")
        print(f"License: {PROJECT_LICENSE}")
        return

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"工作目录不存在或不是目录: {root}")

    if args.list_sessions:
        sessions = list_session_files(root=root)
        if not sessions:
            print(f"（{root} 下没有已保存的会话）")
            return
        for data in sessions[:30]:
            ts = time.strftime("%Y-%m-%d %H:%M",
                               time.localtime(data.get("updated_at", 0)))
            n = len(data.get("messages", []))
            title = data.get("title") or ""
            print(f"{data['id']}  {ts}  {data.get('model', '?'):<20}  "
                  f"{n:>3} msgs  {title}")
        return

    session_data = None
    if args.resume:
        session_data = find_session_by_id_or_title(args.resume)
        if not session_data:
            raise SystemExit(f"找不到会话: {args.resume}")
        stored_root = session_data.get("root")
        if stored_root:
            stored = Path(stored_root).resolve()
            if not stored.is_dir():
                raise SystemExit(f"会话的工作目录不存在: {stored}")
            if stored != root:
                print(f"（使用会话记录的工作目录: {stored}）")
                root = stored

    try:
        from .lsp.config import make_default_if_missing as _lsp_make_default
        _lsp_make_default()
    except Exception:
        pass

    global_cfg_path = (
        Path(args.config).expanduser().resolve() if args.config
        else default_config_path()
    )
    proj_cfg_path = project_config_path(root)
    cfg = compose_config(global_cfg_path, proj_cfg_path)

    profile_raw = None
    if args.profile:
        profile_raw = load_profile(args.profile)
        if profile_raw is None:
            raise SystemExit(f"找不到画像: {args.profile}")
        apply_profile(cfg, profile_raw)

    merge_bash_prefixes(cfg.get("bash", {}).get("extra_prefixes", []))

    def pick(cli_val, default_val, cfg_val):
        if cli_val != default_val:
            return cli_val
        return cfg_val if cfg_val is not None else cli_val

    model = pick(args.model, DEFAULT_MODEL, cfg["default"].get("model"))
    host = pick(args.host, DEFAULT_HOST, cfg["default"].get("host"))
    api_key = args.api_key or cfg["default"].get("api_key", "")
    temperature = pick(args.temperature, 0.2,
                       cfg["default"].get("temperature"))
    max_steps = pick(args.max_steps, 8, cfg["default"].get("max_steps"))
    auto_yes = args.yes or bool(cfg["default"].get("auto_yes", False))
    # 安全：`--prompt` 不再隐式打开自动确认。
    # 过去一次性任务模式会把所有写操作与 shell 命令变成零确认执行，
    # 模型只要输出 `python -c "..."` 就能直接拿到本机代码执行。
    # 需要无人值守时请显式传 -y / --yes。

    show_reasoning = bool(cfg["default"].get("show_reasoning", True))
    if args.no_reasoning:
        show_reasoning = False
    if args.show_reasoning:
        show_reasoning = True

    think_level = args.think or cfg["default"].get("think_level",
                                                     DEFAULT_THINK_LEVEL)

    allow_arbitrary = args.shell_any or bool(
        cfg["default"].get("allow_arbitrary_shell", False)
    )
    enable_cu = args.enable_computer_use or bool(
        cfg["default"].get("enable_computer_use", False)
    )
    enable_vision = args.vision or bool(
        cfg["default"].get("enable_vision", False)
    )

    sandbox_terminal = (
        args.sandbox_terminal
        if args.sandbox_terminal is not None
        else bool(cfg["default"].get("sandbox_terminal", True))
    )

    if args.safe:
        access_mode = "ask"
    elif args.yolo:
        access_mode = "allow"
    elif args.mode:
        m = ACCESS_MODE_ALIASES.get(args.mode.lower(), args.mode.lower())
        if m not in ACCESS_MODES:
            raise SystemExit(
                f"未知访问模式: {args.mode}。可选: {', '.join(ACCESS_MODES)}"
            )
        access_mode = m
    else:
        access_mode = cfg["default"].get("mode", DEFAULT_ACCESS_MODE)
        access_mode = ACCESS_MODE_ALIASES.get(access_mode, access_mode)
        if access_mode not in ACCESS_MODES:
            access_mode = DEFAULT_ACCESS_MODE

    from .i18n import set_lang
    set_lang(cfg["default"].get("language", "zh"))

    copilot = OneCedric(
        model=model, host=host, root=root,
        max_steps=max_steps, temperature=temperature,
        auto_yes=auto_yes, session_data=session_data,
        config=cfg, config_path=global_cfg_path,
        project_config_path=proj_cfg_path,
        profile_name=(args.profile or ""),
        api_key=api_key,
        show_reasoning=show_reasoning,
        enable_computer_use=enable_cu,
        enable_vision=enable_vision,
        think_level=think_level,
        access_mode=access_mode,
        sandbox_terminal=sandbox_terminal,
    )
    if profile_raw:
        copilot.preset_tag = profile_preset_tag(profile_raw)
    if args.safe:
        copilot.auto_yes = False
        copilot.snapshot_granularity = "write"
        copilot.preset_tag = "SAFE"
    elif args.yolo:
        copilot.auto_yes = True
        copilot.snapshot_granularity = "write"
        copilot.preset_tag = "YOLO"

    copilot.allow_arbitrary_shell = allow_arbitrary

    if args.save_config:
        copilot._save_config("global")

    if args.gateway:
        return _run_gateway(copilot, bind=args.bind, port=args.port,
                            token=args.token)

    if args.prompt:
        copilot.ask_once(args.prompt)
        return

    if args.cron_daemon:
        copilot._ensure_cron_daemon()

    if args.no_menu or args.chat:
        copilot.run(in_menu=False)
        return

    _run_with_menu(copilot)


def _run_gateway(copilot, bind: str | None = None, port: int | None = None,
                 token: str | None = None) -> int:
    """启动 WebUI 网关并阻塞运行，直到 Ctrl+C。

    这是 README 中 `python -m one_cedric --gateway` 的实现入口。
    绑定地址默认取配置里的 ``gateway.host``（通常 127.0.0.1）；
    传 ``--bind 0.0.0.0`` 才允许局域网访问，此时应同时设置 ``--token``。
    """
    from .gateway import get_gateway

    console = copilot.console
    gw_cfg = (copilot.config or {}).get("gateway", {}) or {}

    host = bind or str(gw_cfg.get("host", "127.0.0.1") or "127.0.0.1")
    port = int(port if port is not None else gw_cfg.get("port", 2043) or 2043)
    token = token if token is not None else str(gw_cfg.get("token", "") or "")

    try:
        gw = get_gateway(copilot)
    except Exception as exc:
        console.print(f"[err]✗ 网关初始化失败: {exc}[/]")
        return 1

    ok, msg = gw.start(host=host, port=port, token=token)
    if not ok:
        console.print(f"[err]✗ 网关启动失败: {msg}[/]")
        return 1

    console.print(f"[ok]✓ One Cedric WebUI 已启动：[/][accent]{msg}[/]")
    if not token and host not in ("127.0.0.1", "localhost"):
        console.print(
            f"[warn]⚠ 绑定在 {host} 且未设置 token："
            f"同一网络内的任何人都能访问。建议加 --token <密钥>。[/]"
        )
    console.print("[dim]按 Ctrl+C 停止网关。[/]")

    try:
        while gw.is_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print()
    finally:
        ok, msg = gw.stop()
    console.print(f"[dim]{msg}[/]")
    return 0


def _run_with_menu(copilot) -> None:
    from .ui.screens.main import run_main_menu
    from .ui.screens.placeholder import run_placeholder

    console = copilot.console

    while True:
        choice = run_main_menu(console, copilot)

        if choice in (None, "quit"):
            try:
                from .gateway import reset_gateway
                reset_gateway()
            except Exception:
                pass
            console.clear()
            console.print("[dim]再见！[/]")
            return

        if choice == "cli-chat":
            from .ui.screens.chat import (
                configure_new_session,
                run_cli_chat_menu,
            )
            chat_choice = run_cli_chat_menu(console, copilot)

            if chat_choice == "new-session":
                if configure_new_session(console, copilot):
                    copilot.run(in_menu=True)
            elif chat_choice == "my-sessions":
                from .ui.screens.sessions import run_sessions_screen
                run_sessions_screen(console, copilot)
                copilot.run(in_menu=True)
            elif chat_choice == "settings":
                from .ui.screens.settings import run_settings_screen
                run_settings_screen(console, copilot)
            continue

        if choice == "gateway":
            try:
                from .ui.screens.gateway import run_gateway_screen
                run_gateway_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "网关")
            continue

        if choice == "tools":
            try:
                from .ui.screens.tools import run_tools_screen
                run_tools_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "工具")
            continue

        if choice == "mcp":
            from .ui.screens.integrations import run_mcp_screen
            run_mcp_screen(console, copilot)
            continue

        if choice == "hooks":
            from .ui.screens.integrations import run_hooks_screen
            run_hooks_screen(console, copilot)
            continue

        if choice == "models":
            try:
                from .ui.screens.models import run_models_screen
                run_models_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "模型")
            continue

        if choice == "settings":
            try:
                from .ui.screens.settings import run_settings_screen
                run_settings_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "设置")
            continue

        if choice == "about":
            try:
                from .ui.screens.about import run_about_screen
                run_about_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "关于")
            continue

        if choice == "diagnose":
            try:
                from .ui.screens.diagnose import run_diagnose_screen
                run_diagnose_screen(console, copilot)
            except ImportError:
                run_placeholder(console, copilot, "诊断")
            continue

        continue


def _toggle_language(console, copilot) -> None:
    from .i18n import get_lang, set_lang, t
    from .storage import save_config_file

    new = "en" if get_lang() == "zh" else "zh"
    set_lang(new)
    copilot.config.setdefault("default", {})["language"] = new
    save_config_file(copilot.config_path, copilot.config)
    console.clear()
    console.print(f"[ok]✓[/] {t('lang.switched')}")
    time.sleep(0.4)


if __name__ == "__main__":
    main()
