"""多服务器生命周期管理。"""
from __future__ import annotations

import threading
from pathlib import Path

from .client import LSPClient
from .config import load_lsp_config


_MANAGER_LOCK = threading.Lock()
_MANAGER_INSTANCE: "LSPManager | None" = None


def get_manager(root: Path) -> "LSPManager":
    global _MANAGER_INSTANCE
    with _MANAGER_LOCK:
        if _MANAGER_INSTANCE is None:
            _MANAGER_INSTANCE = LSPManager(root)
        elif _MANAGER_INSTANCE.root != root.resolve():
            _MANAGER_INSTANCE.shutdown_all()
            _MANAGER_INSTANCE = LSPManager(root)
        return _MANAGER_INSTANCE


def reset_manager() -> None:
    global _MANAGER_INSTANCE
    with _MANAGER_LOCK:
        if _MANAGER_INSTANCE is not None:
            _MANAGER_INSTANCE.shutdown_all()
        _MANAGER_INSTANCE = None


class LSPManager:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = load_lsp_config()
        self._clients: dict[str, LSPClient] = {}
        self._lock = threading.Lock()
        self._last_error: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("settings", {}).get("enabled", True))

    def list_servers(self) -> list[str]:
        return list(self.config.get("servers", {}).keys())

    def servers_for(self, path: Path) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        ext = path.suffix.lower()
        for name, srv in self.config.get("servers", {}).items():
            if not srv.get("enabled", True):
                continue
            exts = [e.lower() for e in srv.get("extensions", [])]
            if ext in exts:
                out.append((name, srv))
        return out

    def get_client(self, server_name: str) -> LSPClient:
        with self._lock:
            cli = self._clients.get(server_name)
            if cli is not None and cli.is_alive():
                return cli

            srv = self.config.get("servers", {}).get(server_name)
            if srv is None:
                raise RuntimeError(f"未定义的 LSP 服务器: {server_name}")

            cmd = srv.get("command", "")
            if not cmd:
                raise RuntimeError(f"服务器 {server_name} 未配置 command")

            cli = LSPClient(
                name=server_name,
                command=cmd,
                args=list(srv.get("args", [])),
                project_root=self.root,
                init_timeout=int(srv.get("init_timeout", 30)),
                request_timeout=int(srv.get("request_timeout", 15)),
            )
            try:
                cli.ensure_started()
            except Exception as exc:
                self._last_error[server_name] = str(exc)
                raise
            self._clients[server_name] = cli
            return cli

    def pick_client(self, path: Path) -> tuple[str, LSPClient]:
        candidates = self.servers_for(path)
        if not candidates:
            ext = path.suffix or "(无扩展名)"
            raise RuntimeError(
                f"没有为 {ext} 配置 LSP 服务器。"
                f"在 ~/.one-cedric/lsp.toml 里添加 [servers.<name>] 段。"
            )
        errors: list[str] = []
        for name, _srv in candidates:
            try:
                return name, self.get_client(name)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                continue
        raise RuntimeError("所有候选服务器都启动失败：\n  " + "\n  ".join(errors))

    def diagnostics_wait(self) -> float:
        try:
            return float(self.config.get("settings", {}).get("diagnostics_wait", 2.0))
        except (TypeError, ValueError):
            return 2.0

    def shutdown_all(self) -> None:
        with self._lock:
            for cli in self._clients.values():
                try:
                    cli.shutdown()
                except Exception:
                    pass
            self._clients.clear()

    def status(self) -> list[dict]:
        out: list[dict] = []
        for name, srv in self.config.get("servers", {}).items():
            cli = self._clients.get(name)
            out.append({
                "name": name,
                "enabled": bool(srv.get("enabled", True)),
                "command": srv.get("command", ""),
                "args": list(srv.get("args", [])),
                "extensions": list(srv.get("extensions", [])),
                "running": cli is not None and cli.is_alive(),
                "initialized": cli is not None and cli._initialized,
                "last_error": self._last_error.get(name, ""),
            })
        return out