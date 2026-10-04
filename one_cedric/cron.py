"""定时任务：让 agent 定期自动执行 prompt。

存储: ~/.one-cedric/cron.toml
日志: ~/.one-cedric/cron_log/<job_id>/<timestamp>.log
调度: CronDaemon 后台线程，每 30s 检查一次
"""
from __future__ import annotations

import datetime as _dt
import secrets
import threading
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None


CRON_DIR = Path.home() / ".one-cedric"
CRON_PATH = CRON_DIR / "cron.toml"
LOG_DIR = CRON_DIR / "cron_log"


def _path() -> Path:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    return CRON_PATH


def _esc(s: str) -> str:
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n"))


def _load() -> dict:
    p = _path()
    if not p.exists() or tomllib is None:
        return {"jobs": []}
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": []}
    jobs = raw.get("jobs")
    if not isinstance(jobs, list):
        return {"jobs": []}
    return {"jobs": jobs}


def _save(data: dict) -> bool:
    p = _path()
    jobs = data.get("jobs") or []
    lines = ["# One Cedric 定时任务", ""]
    for j in jobs:
        lines.append("[[jobs]]")
        for k in ("id", "name", "schedule", "prompt"):
            lines.append(f'{k} = "{_esc(j.get(k, ""))}"')
        lines.append(
            f"enabled = {'true' if j.get('enabled', True) else 'false'}")
        for k in ("created_at", "last_run", "next_run"):
            lines.append(f"{k} = {float(j.get(k, 0))}")
        lines.append(f'last_status = "{_esc(j.get("last_status", ""))}"')
        lines.append(f'last_error = "{_esc(j.get("last_error", ""))}"')
        lines.append("")
    try:
        p.write_text("\n".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


def _new_id() -> str:
    return "job_" + secrets.token_hex(4)


def _match_field(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        try:
            step = int(field[2:])
            return step > 0 and value % step == 0
        except ValueError:
            return False
    for token in field.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            try:
                a, b = token.split("-", 1)
                if int(a) <= value <= int(b):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(token) == value:
                    return True
            except ValueError:
                continue
    return False


def _validate_schedule(expr: str) -> str:
    parts = (expr or "").split()
    if len(parts) != 5:
        return "cron 表达式需要 5 段（分 时 日 月 周）"
    return ""


def next_run_time(expr: str, after: float | None = None) -> float:
    if _validate_schedule(expr):
        return 0
    parts = expr.split()
    now = _dt.datetime.fromtimestamp(after or time.time())
    candidate = now.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if (_match_field(parts[0], candidate.minute)
                and _match_field(parts[1], candidate.hour)
                and _match_field(parts[2], candidate.day)
                and _match_field(parts[3], candidate.month)
                and _match_field(parts[4], (candidate.weekday() + 1) % 7)):
            return candidate.timestamp()
        candidate += _dt.timedelta(minutes=1)
    return 0


def _find_index(jobs: list, token: str):
    t = (token or "").strip().lower()
    if not t:
        return None
    for i, j in enumerate(jobs):
        if t == j.get("id", "").lower():
            return i
    for i, j in enumerate(jobs):
        if t == j.get("name", "").lower():
            return i
    for i, j in enumerate(jobs):
        if t in j.get("name", "").lower():
            return i
    return None


def add_job(name: str, schedule: str, prompt: str,
            enabled: bool = True) -> tuple:
    name = (name or "").strip()
    prompt = (prompt or "").strip()
    if not name:
        return "", "name 不能为空"
    if not prompt:
        return "", "prompt 不能为空"
    err = _validate_schedule(schedule)
    if err:
        return "", err

    data = _load()
    jobs = data["jobs"]
    for j in jobs:
        if j.get("name", "").lower() == name.lower():
            return "", f"名字 '{name}' 已存在"

    jid = _new_id()
    now = time.time()
    jobs.append({
        "id": jid, "name": name, "schedule": schedule, "prompt": prompt,
        "enabled": enabled, "created_at": now,
        "last_run": 0, "last_status": "", "last_error": "",
        "next_run": next_run_time(schedule, now) if enabled else 0,
    })
    _save(data)
    return jid, ""


def remove_job(token: str) -> bool:
    data = _load()
    i = _find_index(data["jobs"], token)
    if i is None:
        return False
    data["jobs"].pop(i)
    return _save(data)


def get_job(token: str) -> dict | None:
    data = _load()
    i = _find_index(data["jobs"], token)
    return data["jobs"][i] if i is not None else None


def list_jobs() -> list:
    return _load()["jobs"]


def enable_job(token: str, enabled: bool) -> bool:
    data = _load()
    i = _find_index(data["jobs"], token)
    if i is None:
        return False
    j = data["jobs"][i]
    j["enabled"] = enabled
    j["next_run"] = next_run_time(j.get("schedule", "")) if enabled else 0
    return _save(data)


def update_job_run(job_id: str, status: str, error: str = "") -> None:
    data = _load()
    for j in data["jobs"]:
        if j.get("id") == job_id:
            j["last_run"] = time.time()
            j["last_status"] = status
            j["last_error"] = error[:300]
            if j.get("enabled"):
                j["next_run"] = next_run_time(j.get("schedule", ""))
            break
    _save(data)


def log_path(job_id: str) -> Path:
    d = LOG_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_log(job_id: str, content: str) -> Path:
    d = log_path(job_id)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    f = d / f"{ts}.log"
    try:
        f.write_text(content, encoding="utf-8")
    except OSError:
        pass
    return f


def list_logs(job_id: str, limit: int = 20) -> list:
    d = log_path(job_id)
    try:
        return sorted(d.glob("*.log"), reverse=True)[:limit]
    except OSError:
        return []


def format_job(j: dict) -> str:
    icon = {"ok": "✓", "error": "✗", "running": "⟳", "":
            "·"}.get(j.get("last_status", ""), "·")
    last = j.get("last_run", 0)
    last_str = (_dt.datetime.fromtimestamp(last).strftime("%m-%d %H:%M")
                if last else "从未")
    nxt = j.get("next_run", 0)
    nxt_str = (_dt.datetime.fromtimestamp(nxt).strftime("%m-%d %H:%M")
               if nxt and j.get("enabled", True) else "—")
    enabled = "on " if j.get("enabled", True) else "off"
    return (f"[{enabled}] {icon} {j.get('name', '')}\n"
            f"       {j.get('schedule', '')}   下次 {nxt_str}   "
            f"上次 {last_str}\n"
            f"       id: {j.get('id', '')}\n"
            f"       prompt: {j.get('prompt', '')[:70]}")


class CronDaemon:
    CHECK_INTERVAL = 30

    def __init__(self, copilot):
        self.copilot = copilot
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running: set = set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="cedric-cron")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            try:
                self._thread.join(timeout=2)
            except Exception:
                pass
        self._thread = None

    def _loop(self) -> None:
        self._recalc()
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                try:
                    print(f"[cron] tick: {exc}")
                except Exception:
                    pass
            if self._stop.wait(self.CHECK_INTERVAL):
                return

    def _recalc(self) -> None:
        data = _load()
        now = time.time()
        changed = False
        for j in data["jobs"]:
            if not j.get("enabled", True):
                continue
            if not j.get("next_run") or j["next_run"] < now - 60:
                j["next_run"] = next_run_time(j.get("schedule", ""), now)
                changed = True
        if changed:
            _save(data)

    def _tick(self) -> None:
        data = _load()
        now = time.time()
        for j in data["jobs"]:
            if not j.get("enabled", True):
                continue
            nxt = j.get("next_run", 0)
            if not nxt:
                j["next_run"] = next_run_time(j.get("schedule", ""), now)
                _save(data)
                continue
            if nxt > now:
                continue
            jid = j.get("id", "")
            with self._lock:
                if jid in self._running:
                    continue
                self._running.add(jid)
            threading.Thread(target=self._run_job, args=(jid,),
                             daemon=True, name=f"cron-{jid}").start()

    def _run_job(self, job_id: str) -> None:
        try:
            j = get_job(job_id)
            if not j:
                return
            prompt = j.get("prompt", "")
            if not prompt:
                return
            update_job_run(job_id, "running")
            started = time.time()

            is_dream = prompt.startswith("__DREAM__")
            try:
                if is_dream:
                    from . import dream as _dream
                    rest = prompt[len("__DREAM__"):].strip()
                    days = 3
                    focus = rest
                    for tok in rest.split():
                        if tok.startswith("--days="):
                            try:
                                days = int(tok.split("=", 1)[1])
                                focus = focus.replace(tok, "").strip()
                            except ValueError:
                                pass
                    r = _dream.run_dream(self.copilot, days=days,
                                         focus=focus)
                    answer = r.get("answer", "") if r.get("ok") else ""
                    tool_calls = []
                    status = "ok" if r.get("ok") else "error"
                    error = "" if r.get("ok") else r.get("error", "")
                else:
                    r = self.copilot.ask_no_ui(prompt, auto_approve=False)
                    answer = r.get("answer", "")
                    tool_calls = r.get("tool_calls", [])
                    status, error = "ok", ""
            except Exception as exc:
                answer, tool_calls = "", []
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.time() - started
            log = [
                f"# Job: {j.get('name')} ({job_id})",
                f"# Time: {_dt.datetime.now().isoformat()}",
                f"# Duration: {elapsed:.2f}s",
                f"# Prompt: {prompt}",
                "",
            ]
            if status == "error":
                log.append("## ERROR")
                log.append(error)
            else:
                if tool_calls:
                    log.append(f"## Tool Calls ({len(tool_calls)})")
                    for tc in tool_calls:
                        log.append(
                            f"  · {tc.get('name')}  {tc.get('target', '')}"
                            f"  [{tc.get('status', 'ok')}]")
                    log.append("")
                log.append("## Answer")
                log.append(answer or "(空)")
            write_log(job_id, "\n".join(log))
            update_job_run(job_id, status, error)
        finally:
            with self._lock:
                self._running.discard(job_id)

    def run_now(self, token: str) -> str:
        j = get_job(token)
        if not j:
            return f"ERROR: 未找到 '{token}'"
        jid = j["id"]
        with self._lock:
            if jid in self._running:
                return f"'{j.get('name')}' 正在运行"
            self._running.add(jid)
        threading.Thread(target=self._run_job, args=(jid,),
                         daemon=True).start()
        return f"已触发 '{j.get('name')}'"