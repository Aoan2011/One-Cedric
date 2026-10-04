"""LSP 客户端：JSON-RPC over stdio。"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


LANG_ID = {
    ".py": "python", ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescriptreact",
    ".js": "javascript", ".jsx": "javascriptreact",
    ".mjs": "javascript", ".cjs": "javascript",
    ".go": "go", ".rs": "rust",
    ".java": "java", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp", ".rb": "ruby", ".php": "php",
    ".sh": "shellscript", ".bash": "shellscript",
    ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".sql": "sql", ".xml": "xml", ".toml": "toml",
}


def uri_from_path(p: Path) -> str:
    return p.resolve().as_uri()


def path_from_uri(uri: str) -> Path | None:
    try:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return Path(path)
    except Exception:
        return None


class LSPClient:
    def __init__(self, name: str, command: str, args: list[str],
                 project_root: Path,
                 init_timeout: int = 30,
                 request_timeout: int = 15):
        self.name = name
        self.command = command
        self.args = list(args)
        self.project_root = project_root
        self.init_timeout = init_timeout
        self.request_timeout = request_timeout

        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._pending: dict[int, Future] = {}
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._opened: dict[str, int] = {}
        self._diagnostics: dict[str, list] = {}
        self._diag_lock = threading.Lock()
        self._initialized = False
        self._stderr_buf: list[str] = []

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure_started(self) -> None:
        with self._start_lock:
            if self._initialized and self.is_alive():
                return
            self._start_process()
            try:
                self._do_initialize()
                self._initialized = True
            except Exception:
                self.shutdown()
                raise

    def _start_process(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root),
                bufsize=0,
            )
        except FileNotFoundError:
            raise RuntimeError(f"找不到 LSP 命令: {self.command}")
        except OSError as exc:
            raise RuntimeError(f"启动 LSP 失败: {exc}")

        self._reader = threading.Thread(
            target=self._read_loop, name=f"lsp-{self.name}", daemon=True,
        )
        self._reader.start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def shutdown(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._initialized = False
        try:
            if proc.poll() is None:
                try:
                    self._notify("exit", None)
                except Exception:
                    pass
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        finally:
            self._proc = None
            with self._pending_lock:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError("LSP 已关闭"))
                self._pending.clear()

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        stream = proc.stdout
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = stream.readline()
                    if not line:
                        return
                    line = line.rstrip(b"\r\n")
                    if not line:
                        break
                    try:
                        key, _, val = line.partition(b":")
                        headers[key.strip().lower().decode("ascii", "ignore")] = \
                            val.strip().decode("ascii", "ignore")
                    except Exception:
                        continue
                try:
                    length = int(headers.get("content-length", "0"))
                except ValueError:
                    continue
                if length <= 0:
                    continue
                body = stream.read(length)
                if not body:
                    return
                try:
                    msg = json.loads(body.decode("utf-8", "replace"))
                except Exception:
                    continue
                self._handle_message(msg)
        except Exception:
            return
        finally:
            with self._pending_lock:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError("LSP 连接断开"))
                self._pending.clear()

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self._stderr_buf.append(line)
                    if len(self._stderr_buf) > 200:
                        self._stderr_buf = self._stderr_buf[-200:]
        except Exception:
            pass

    def _handle_message(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            rid = msg["id"]
            with self._pending_lock:
                fut = self._pending.pop(rid, None)
            if fut is None:
                return
            if "error" in msg:
                err = msg["error"]
                msg_text = err.get("message") if isinstance(err, dict) else str(err)
                fut.set_exception(RuntimeError(f"LSP 错误: {msg_text}"))
            else:
                fut.set_result(msg.get("result"))
            return

        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params") or {}
            uri = params.get("uri")
            diags = params.get("diagnostics", [])
            if uri:
                with self._diag_lock:
                    self._diagnostics[uri] = diags

    def _send(self, msg: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("LSP 未启动")
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._write_lock:
            proc.stdin.write(header + data)
            proc.stdin.flush()

    def _request(self, method: str, params: Any, timeout: int | None = None) -> Any:
        self.ensure_started()
        rid = self._next_id
        self._next_id += 1
        fut: Future = Future()
        with self._pending_lock:
            self._pending[rid] = fut
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": method, "params": params,
        })
        try:
            return fut.result(timeout=timeout or self.request_timeout)
        except FutureTimeout:
            with self._pending_lock:
                self._pending.pop(rid, None)
            raise TimeoutError(f"LSP {method} 超时 ({timeout or self.request_timeout}s)")

    def _notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _do_initialize(self) -> None:
        root_uri = uri_from_path(self.project_root)
        init_params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": str(self.project_root),
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": False},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    "publishDiagnostics": {"relatedInformation": False},
                },
                "workspace": {"workspaceFolders": True, "symbol": {}},
            },
            "workspaceFolders": [
                {"uri": root_uri, "name": self.project_root.name}
            ],
        }
        self._request("initialize", init_params, timeout=self.init_timeout)
        self._notify("initialized", {})

    def open_document(self, path: Path) -> str:
        uri = uri_from_path(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"读取文件失败: {exc}")
        lang = LANG_ID.get(path.suffix.lower(), "plaintext")
        version = self._opened.get(uri, 0) + 1
        self._opened[uri] = version
        self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": lang,
                "version": version,
                "text": text,
            },
        })
        return uri

    def close_document(self, path: Path) -> None:
        uri = uri_from_path(path)
        if uri in self._opened:
            try:
                self._notify("textDocument/didClose", {
                    "textDocument": {"uri": uri},
                })
            except Exception:
                pass
            self._opened.pop(uri, None)

    def hover(self, path: Path, line: int, col: int) -> Any:
        uri = self.open_document(path)
        return self._request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": max(0, line - 1), "character": max(0, col - 1)},
        })

    def definition(self, path: Path, line: int, col: int) -> Any:
        uri = self.open_document(path)
        return self._request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": max(0, line - 1), "character": max(0, col - 1)},
        })

    def references(self, path: Path, line: int, col: int,
                   include_decl: bool = True) -> Any:
        uri = self.open_document(path)
        return self._request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": max(0, line - 1), "character": max(0, col - 1)},
            "context": {"includeDeclaration": bool(include_decl)},
        })

    def document_symbols(self, path: Path) -> Any:
        uri = self.open_document(path)
        return self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })

    def diagnostics(self, path: Path, wait: float = 2.0) -> list:
        uri = self.open_document(path)
        deadline = time.time() + max(0.2, wait)
        while time.time() < deadline:
            with self._diag_lock:
                diags = self._diagnostics.get(uri)
            if diags is not None:
                return diags
            time.sleep(0.1)
        with self._diag_lock:
            return self._diagnostics.get(uri, [])

    def stderr_tail(self, n: int = 10) -> list[str]:
        return self._stderr_buf[-n:]