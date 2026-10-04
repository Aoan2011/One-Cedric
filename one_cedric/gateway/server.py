"""Gateway FastAPI 服务实现。"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from ..config import BRAND, ACCENT, OK_C, ERR_C, WARN_C, DIM_C


_BaseModel = None


def _get_basemodel():
    global _BaseModel
    if _BaseModel is None:
        try:
            from pydantic import BaseModel
            _BaseModel = BaseModel
        except ImportError:
            class _FakeBase:
                def __init__(self, **kw):
                    for k, v in kw.items():
                        setattr(self, k, v)
            _BaseModel = _FakeBase
    return _BaseModel


_GATEWAY_LOCK = threading.Lock()
_GATEWAY_INSTANCE: "Gateway | None" = None


def get_gateway(copilot) -> "Gateway":
    global _GATEWAY_INSTANCE
    with _GATEWAY_LOCK:
        if _GATEWAY_INSTANCE is None:
            _GATEWAY_INSTANCE = Gateway(copilot)
        return _GATEWAY_INSTANCE


def reset_gateway() -> None:
    global _GATEWAY_INSTANCE
    with _GATEWAY_LOCK:
        if _GATEWAY_INSTANCE is not None:
            try:
                _GATEWAY_INSTANCE.stop()
            except Exception:
                pass
        _GATEWAY_INSTANCE = None


class Gateway:
    ASK_GRACE_SECONDS = 60

    def __init__(self, copilot):
        self.copilot = copilot
        self.host = "127.0.0.1"
        self.port = 2043
        self.token = ""

        self._server = None
        self._thread = None
        self._running = False
        self._chat_lock = threading.Lock()

        self._stats = {
            "requests": 0,
            "errors": 0,
            "started_at": 0.0,
            "last_request_at": 0.0,
        }

        self._recent_logs: list = []
        self._logs_lock = threading.Lock()

        # ask_user 状态
        self._ask_details: dict = {}
        self._ask_orphaned: dict = {}
        self._ask_lock = threading.Lock()
        self._ask_gc_thread = None
        self._ask_gc_stop = threading.Event()

        # 反向引用，供 core 里的 ask_user 使用
        copilot._gateway_ref = self

        self.app = self._build_app()

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    def is_running(self) -> bool:
        return self._running and self._server is not None

    def start(self, host: str = "", port: int = 0,
              token: str = "") -> tuple:
        if self._running:
            return False, "网关已在运行"

        try:
            import uvicorn
        except ImportError:
            return False, ("需要 fastapi + uvicorn："
                           "pip install fastapi uvicorn")

        self.host = host or self.host or "127.0.0.1"
        self.port = int(port) if port else self.port or 2043
        self.token = token if token is not None else self.token

        try:
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False,
            )
            self._server = uvicorn.Server(config)
            self._server.install_signal_handlers = lambda: None
        except Exception as exc:
            return False, f"配置失败: {exc}"

        self._stats["started_at"] = time.time()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._server.serve())
            except Exception:
                pass
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        self._thread = threading.Thread(
            target=_run, daemon=True, name="cedric-gateway")
        self._thread.start()

        time.sleep(0.6)
        if self._thread.is_alive():
            self._running = True
            self._ensure_gc_thread()
            return True, f"http://{self.host}:{self.port}"
        return False, "服务器启动失败（可能端口被占用）"

    def stop(self) -> tuple:
        if not self._running or self._server is None:
            return False, "网关未运行"
        try:
            self._ask_gc_stop.set()
        except Exception:
            pass
        try:
            self.cancel_all_asks("（网关已停止）")
        except Exception:
            pass
        try:
            self._server.should_exit = True
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._running = False
        self._server = None
        self._thread = None
        return True, "已停止"

    def status(self) -> dict:
        uptime = (time.time() - self._stats["started_at"]
                  if self._running else 0)
        return {
            "running": self.is_running(),
            "host": self.host,
            "port": self.port,
            "url": (f"http://{self.host}:{self.port}"
                    if self._running else ""),
            "token_set": bool(self.token),
            "requests": self._stats["requests"],
            "errors": self._stats["errors"],
            "uptime": round(uptime, 1),
        }

    def recent_logs(self, n: int = 20) -> list:
        with self._logs_lock:
            return list(self._recent_logs[-n:])

    def _log_request(self, method: str, path: str, status: int,
                     duration: float, note: str = "") -> None:
        entry = {
            "ts": time.time(),
            "method": method,
            "path": path,
            "status": status,
            "duration": round(duration, 3),
            "note": note,
        }
        with self._logs_lock:
            self._recent_logs.append(entry)
            if len(self._recent_logs) > 200:
                self._recent_logs = self._recent_logs[-200:]

    # ------------------------------------------------------------------ #
    # ask_user 断线宽限
    # ------------------------------------------------------------------ #

    def register_ask(self, ask_id: str, details: dict) -> None:
        with self._ask_lock:
            self._ask_details[ask_id] = {
                **details,
                "created_at": time.time(),
            }
            self._ask_orphaned.pop(ask_id, None)
        self._ensure_gc_thread()

    def unregister_ask(self, ask_id: str) -> None:
        with self._ask_lock:
            self._ask_details.pop(ask_id, None)
            self._ask_orphaned.pop(ask_id, None)

    def mark_orphaned_all(self) -> int:
        now = time.time()
        n = 0
        with self._ask_lock:
            for aid in list(self._ask_details.keys()):
                if aid not in self._ask_orphaned:
                    self._ask_orphaned[aid] = now
                    n += 1
        return n

    def get_pending_asks(self) -> list:
        now = time.time()
        out = []
        with self._ask_lock:
            for aid, d in list(self._ask_details.items()):
                age = now - d.get("created_at", now)
                out.append({
                    "id": aid,
                    "header": d.get("header", ""),
                    "timeout": d.get("timeout", 0),
                    "questions": d.get("questions", []),
                    "created_at": d.get("created_at", now),
                    "elapsed": round(age, 1),
                    "orphaned": aid in self._ask_orphaned,
                })
        out.sort(key=lambda x: x["created_at"])
        return out

    def _ensure_gc_thread(self) -> None:
        if self._ask_gc_thread and self._ask_gc_thread.is_alive():
            return
        self._ask_gc_stop.clear()
        t = threading.Thread(target=self._ask_gc_loop, daemon=True,
                             name="cedric-ask-gc")
        self._ask_gc_thread = t
        t.start()

    def _ask_gc_loop(self) -> None:
        while not self._ask_gc_stop.is_set():
            if self._ask_gc_stop.wait(timeout=10):
                return
            now = time.time()
            to_cancel: list = []
            with self._ask_lock:
                for aid, orphaned_at in list(
                        self._ask_orphaned.items()):
                    if now - orphaned_at > self.ASK_GRACE_SECONDS:
                        to_cancel.append(aid)
            for aid in to_cancel:
                try:
                    self.copilot.answer_ask(
                        aid, "（用户长时间未响应）")
                except Exception:
                    pass
                with self._ask_lock:
                    self._ask_details.pop(aid, None)
                    self._ask_orphaned.pop(aid, None)

    def cancel_all_asks(self, reason: str = "（连接已断开）") -> int:
        with self._ask_lock:
            ids = list(self._ask_details.keys())
            self._ask_details.clear()
            self._ask_orphaned.clear()
        n = 0
        for aid in ids:
            try:
                if self.copilot.answer_ask(aid, reason):
                    n += 1
            except Exception:
                pass
        return n

    # ------------------------------------------------------------------ #
    # FastAPI 应用
    # ------------------------------------------------------------------ #

    def _build_app(self):
        try:
            from fastapi import FastAPI, HTTPException, Request, Depends
            from fastapi.responses import (
                StreamingResponse, JSONResponse, HTMLResponse,
                FileResponse,
            )
        except ImportError:
            class _NoApp:
                pass
            return _NoApp()

        BaseModel = _get_basemodel()
        gw = self

        app = FastAPI(title="One Cedric Gateway", version="0.17.0")

        class ChatRequest(BaseModel):
            message: str = ""
            auto_approve: bool = False
            stream: bool = False

        class ToolCallRequest(BaseModel):
            arguments: dict = {}

        class AskAnswerRequest(BaseModel):
            id: str = ""
            answer: str = ""
            answers: dict = {}

        class UIConfigRequest(BaseModel):
            theme: str = ""
            acrylic: str = ""
            think_level: str = ""
            particle_hue1: int = -1
            particle_hue2: int = -1

        def _auth(request: Request):
            token = gw.token
            if not token:
                return True
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(
                    401, "缺少 Authorization: Bearer <token>")
            if auth[7:].strip() != token:
                raise HTTPException(401, "token 无效")
            return True

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            t0 = time.time()
            gw._stats["requests"] += 1
            gw._stats["last_request_at"] = t0
            try:
                resp = await call_next(request)
            except Exception as exc:
                gw._stats["errors"] += 1
                gw._log_request(request.method, request.url.path,
                                500, time.time() - t0, str(exc)[:80])
                raise
            gw._log_request(request.method, request.url.path,
                            resp.status_code, time.time() - t0)
            return resp

        # ---- 静态（WebUI） ----
        webui_dir = Path(__file__).parent / "webui"

        @app.get("/", response_class=HTMLResponse)
        async def index():
            f = webui_dir / "index.html"
            if not f.exists():
                return HTMLResponse(
                    "<h1>One Cedric Gateway</h1>"
                    "<p>WebUI 未找到。"
                    "请检查 gateway/webui/index.html 是否存在。</p>"
                )
            return HTMLResponse(f.read_text(encoding="utf-8"))

        @app.get("/static/{name}")
        async def static_file(name: str):
            if "/" in name or "\\" in name or ".." in name:
                raise HTTPException(400, "invalid filename")
            f = webui_dir / name
            if not f.exists() or not f.is_file():
                raise HTTPException(404, "not found")
            media = {
                ".js": "application/javascript",
                ".css": "text/css",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }.get(f.suffix.lower(), "application/octet-stream")
            return FileResponse(str(f), media_type=media)

        # ---- 端点 ----

        @app.get("/health")
        async def health():
            return {
                "status": "ok",
                "model": gw.copilot.model,
                "root": str(gw.copilot.root),
            }

        @app.get("/api/status")
        async def api_status(request: Request):
            _auth(request)
            return gw.status()

        @app.get("/api/models")
        async def api_models(request: Request):
            _auth(request)
            try:
                import requests
                base = gw.copilot.host.rstrip("/")
                url = (f"{base}/models" if base.endswith("/v1")
                       else f"{base}/v1/models")
                headers = {}
                if gw.copilot.api_key:
                    headers["Authorization"] = (
                        f"Bearer {gw.copilot.api_key}")
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code >= 400:
                    return {"error": f"HTTP {r.status_code}",
                            "models": []}
                data = r.json()
                models = [m.get("id", "?") for m in data.get("data", [])]
                return {"models": models}
            except Exception as exc:
                return {"error": str(exc), "models": []}

        @app.get("/api/tools")
        async def api_tools(request: Request):
            _auth(request)
            try:
                from ..tools.schema import TOOLS
                from ..integrations import external_tool_schemas
                tools = []
                disabled = getattr(gw.copilot, "disabled_tools", set())
                all_tools = [*TOOLS, *external_tool_schemas()]
                for t in all_tools:
                    fn = t["function"]
                    name = fn["name"]
                    tools.append({
                        "name": name,
                        "description": (fn.get("description") or "")[:200],
                        "enabled": name not in disabled,
                    })
                return {"tools": tools}
            except Exception as exc:
                return {"error": str(exc), "tools": []}

        @app.post("/api/tools/{name}/toggle")
        async def api_tools_toggle(name: str, request: Request):
            _auth(request)
            try:
                from ..storage import save_tools_config
                disabled = set(getattr(
                    gw.copilot, "disabled_tools", set()) or set())
                if name in disabled:
                    disabled.discard(name)
                else:
                    disabled.add(name)
                gw.copilot.disabled_tools = disabled
                save_tools_config(disabled)
                try:
                    gw.copilot.reload_tools_config()
                except Exception:
                    pass
                return {"name": name, "enabled": name not in disabled}
            except Exception as exc:
                return {"error": str(exc)}

        @app.post("/api/chat")
        async def api_chat(req: ChatRequest, request: Request):
            _auth(request)
            if not req.message.strip():
                raise HTTPException(400, "message 不能为空")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, gw._do_chat_locked,
                req.message, req.auto_approve)
            return result

        @app.post("/api/chat/stream")
        async def api_chat_stream(req: ChatRequest, request: Request):
            _auth(request)
            if not req.message.strip():
                raise HTTPException(400, "message 不能为空")

            async def event_gen():
                loop = asyncio.get_running_loop()
                queue: asyncio.Queue = asyncio.Queue()

                def _produce():
                    try:
                        for evt in gw.copilot.ask_no_ui_stream(
                                req.message,
                                auto_approve=req.auto_approve):
                            fut = asyncio.run_coroutine_threadsafe(
                                queue.put(evt), loop)
                            try:
                                fut.result(timeout=30)
                            except Exception:
                                break
                    except Exception as exc:
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"type": "error",
                                        "message": str(exc)}),
                            loop)
                    finally:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(None), loop)

                acquired = gw._chat_lock.acquire(blocking=False)
                if not acquired:
                    err = {"type": "error",
                           "message": "另一个请求正在进行，请稍后"}
                    yield (f"data: "
                           f"{json.dumps(err, ensure_ascii=False)}\n\n")
                    yield "data: [DONE]\n\n"
                    return

                try:
                    threading.Thread(target=_produce, daemon=True).start()
                    while True:
                        evt = await queue.get()
                        if evt is None:
                            break
                        yield (f"data: "
                               f"{json.dumps(evt, ensure_ascii=False)}"
                               f"\n\n")
                    yield "data: [DONE]\n\n"
                finally:
                    try:
                        n_orphaned = gw.mark_orphaned_all()
                        if n_orphaned:
                            gw._log_request(
                                "SSE", "/api/chat/stream", 200, 0,
                                f"{n_orphaned} 个 ask 进入宽限期")
                    except Exception:
                        pass
                    try:
                        gw._chat_lock.release()
                    except Exception:
                        pass

            return StreamingResponse(
                event_gen(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        @app.post("/api/tools/{name}/call")
        async def api_call_tool(name: str, req: ToolCallRequest,
                                 request: Request):
            _auth(request)
            try:
                from ..tools import dispatch_tool
                result = dispatch_tool(
                    name, req.arguments or {}, gw.copilot.root)
                return {"result": result}
            except Exception as exc:
                return {"error": str(exc), "result": ""}

        @app.get("/api/sessions")
        async def api_sessions(request: Request):
            _auth(request)
            try:
                from ..storage import list_session_files
                sessions = list_session_files()
                out = []
                for s in sessions[:50]:
                    out.append({
                        "id": s["id"],
                        "title": s.get("title", ""),
                        "model": s.get("model", ""),
                        "root": s.get("root", ""),
                        "updated_at": s.get("updated_at", 0),
                        "messages": len(s.get("messages", [])),
                    })
                return {"sessions": out}
            except Exception as exc:
                return {"error": str(exc), "sessions": []}

        @app.get("/api/logs")
        async def api_logs(request: Request, n: int = 20):
            _auth(request)
            return {"logs": gw.recent_logs(n)}

        # ---- ask_user ----

        @app.get("/api/ask/pending")
        async def api_ask_pending(request: Request):
            _auth(request)
            return {"pending": gw.get_pending_asks()}

        @app.post("/api/ask/answer")
        async def api_ask_answer(req: AskAnswerRequest,
                                  request: Request):
            _auth(request)
            if not req.id:
                raise HTTPException(400, "id 不能为空")
            payload = req.answers if req.answers else req.answer
            ok = gw.copilot.answer_ask(req.id, payload)
            if not ok:
                return {"ok": False,
                        "error": "提问不存在或已超时"}
            return {"ok": True}

        # ---- UI 配置 ----

        @app.get("/api/config")
        async def api_config_get(request: Request):
            _auth(request)
            ui_cfg = gw.copilot.config.setdefault("ui", {})
            defaults = {
                "theme": "dark",
                "acrylic": "medium",
                "think_level": gw.copilot.think_level or "medium",
                "particle_hue1": 220,
                "particle_hue2": 270,
            }
            for k, v in defaults.items():
                ui_cfg.setdefault(k, v)
            return {
                "ui": ui_cfg,
                "model": gw.copilot.model,
                "host": gw.copilot.host,
            }

        @app.post("/api/config")
        async def api_config_set(req: UIConfigRequest,
                                  request: Request):
            _auth(request)
            ui_cfg = gw.copilot.config.setdefault("ui", {})
            changed: list = []

            if req.theme and req.theme in ("dark", "light"):
                ui_cfg["theme"] = req.theme
                changed.append("theme")
            if req.acrylic and req.acrylic in (
                    "off", "low", "medium", "high"):
                ui_cfg["acrylic"] = req.acrylic
                changed.append("acrylic")
            if req.think_level in ("minimal", "low", "medium", "max",
                                    "xhigh", "ultra"):
                ui_cfg["think_level"] = req.think_level
                changed.append("think_level")
            if 0 <= req.particle_hue1 <= 360:
                ui_cfg["particle_hue1"] = req.particle_hue1
                changed.append("particle_hue1")
            if 0 <= req.particle_hue2 <= 360:
                ui_cfg["particle_hue2"] = req.particle_hue2
                changed.append("particle_hue2")

            if not changed:
                return {"ok": False, "error": "无可更新字段"}

            try:
                from ..storage import save_config_file
                save_config_file(gw.copilot.config_path,
                                 gw.copilot.config)
            except Exception as exc:
                return {"ok": False, "error": f"保存失败: {exc}",
                        "changed": changed}

            return {"ok": True, "changed": changed, "ui": ui_cfg}

        # ---- 文件列表（补全用） ----

        @app.get("/api/files")
        async def api_files(request: Request, q: str = "",
                            limit: int = 30):
            _auth(request)
            root = gw.copilot.root
            q_lower = (q or "").lower().strip()
            try:
                n = max(1, min(int(limit), 100))
            except (TypeError, ValueError):
                n = 30

            EXCLUDE_DIRS = {
                ".git", ".svn", ".hg", ".venv", "venv", "env",
                "node_modules", "__pycache__", ".pytest_cache",
                ".mypy_cache", ".ruff_cache", "dist", "build",
                ".next", ".nuxt", ".cache", ".cedric_artifacts",
                ".idea", ".vscode",
            }

            results: list = []
            try:
                for f in root.rglob("*"):
                    try:
                        if not f.is_file():
                            continue
                    except OSError:
                        continue
                    parts = set(f.parts)
                    if parts & EXCLUDE_DIRS:
                        continue
                    try:
                        rel = str(f.relative_to(root))
                    except ValueError:
                        continue
                    if q_lower and q_lower not in rel.lower():
                        continue
                    results.append(rel)
                    if len(results) >= n * 5:
                        break
            except Exception:
                pass

            def _score(p: str) -> tuple:
                idx = p.lower().find(q_lower) if q_lower else 0
                depth = p.count("/")
                return (idx if idx >= 0 else 999, depth, len(p), p)

            results.sort(key=_score)
            return {"files": results[:n], "root": str(root)}

        # ---- 文件预览 ----

        @app.get("/api/file-preview")
        async def api_file_preview(request: Request,
                                    path: str = "",
                                    lines: int = 20):
            _auth(request)
            try:
                from ..tools.sandbox import _resolve_path
            except ImportError:
                raise HTTPException(500, "内部错误: sandbox 未加载")

            if not path:
                raise HTTPException(400, "缺少 path 参数")
            try:
                n = max(1, min(int(lines), 60))
            except (TypeError, ValueError):
                n = 20

            p, err = _resolve_path(gw.copilot.root, path)
            if err:
                return {"ok": False, "error": err}
            if not p.exists() or not p.is_file():
                return {"ok": False, "error": "文件不存在"}

            try:
                raw = p.read_bytes()
            except OSError as exc:
                return {"ok": False, "error": str(exc)}

            size = len(raw)
            head = raw[:8192]
            is_binary = b"\x00" in head
            if not is_binary:
                try:
                    head.decode("utf-8")
                except UnicodeDecodeError:
                    is_binary = True

            if is_binary:
                kind = "二进制文件"
                try:
                    from ..tools.readonly import _guess_binary_kind
                    kind = _guess_binary_kind(p, head)
                except Exception:
                    pass
                return {
                    "ok": True,
                    "path": path,
                    "size": size,
                    "binary": True,
                    "kind": kind,
                    "lines": [],
                }

            text = raw[:50000].decode("utf-8", errors="replace")
            all_lines = text.splitlines()
            preview = all_lines[:n]
            return {
                "ok": True,
                "path": path,
                "size": size,
                "binary": False,
                "total_lines": len(all_lines),
                "lines": preview,
                "truncated": len(all_lines) > n,
            }

        # ---- 上传 ----

        @app.post("/api/upload")
        async def api_upload(request: Request, name: str = ""):
            _auth(request)
            if not name:
                raise HTTPException(400, "缺少 name 参数")
            import re as _re

            safe = _re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
            safe = safe.replace("\\", "/").split("/")[-1][:180]
            if not safe or safe in (".", ".."):
                raise HTTPException(400, "非法文件名")

            body = await request.body()
            if not body:
                raise HTTPException(400, "空文件")
            MAX = 25 * 1024 * 1024
            if len(body) > MAX:
                raise HTTPException(
                    413, f"文件过大（>{MAX // 1024 // 1024}MB）")

            try:
                up_dir = gw.copilot.root / ".cedric_uploads"
                up_dir.mkdir(parents=True, exist_ok=True)
                target = up_dir / safe
                if target.exists():
                    stem = target.stem
                    suf = target.suffix
                    for i in range(1, 1000):
                        cand = up_dir / f"{stem}_{i}{suf}"
                        if not cand.exists():
                            target = cand
                            break
                target.write_bytes(body)
                rel = str(target.relative_to(gw.copilot.root))
            except OSError as exc:
                raise HTTPException(500, f"保存失败: {exc}")

            return {
                "ok": True,
                "path": rel,
                "size": len(body),
            }

        return app

    # ------------------------------------------------------------------ #
    # 对话执行
    # ------------------------------------------------------------------ #

    def _do_chat_locked(self, message: str,
                         auto_approve: bool) -> dict:
        with self._chat_lock:
            return self._do_chat(message, auto_approve)

    def _do_chat(self, message: str, auto_approve: bool) -> dict:
        t0 = time.time()
        try:
            result = self.copilot.ask_no_ui(
                message, auto_approve=auto_approve)
        except Exception as exc:
            self._stats["errors"] += 1
            return {
                "error": str(exc),
                "answer": "",
                "tool_calls": [],
                "duration": round(time.time() - t0, 2),
            }
        result["duration"] = round(time.time() - t0, 2)
        return result