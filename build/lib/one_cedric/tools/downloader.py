"""多线程智能下载：断点续传 + 分块并行 + 进度回调。

特性：
  - HTTP Range 分块下载
  - 断点续传（.cedric_parts/ 目录存分片）
  - 大小未知时自动降级单线程
  - 服务端不支持 Range 时降级单线程
  - 进度回调 callable(pct, done, total, speed, eta)
"""
from __future__ import annotations

import json as _json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .sandbox import _resolve_path


CHUNK_SIZE = 512 * 1024
DEFAULT_THREADS = 4
MAX_THREADS = 16
USER_AGENT = "OneCedric/1.0 (Mozilla/5.0 compatible)"


class _Progress:
    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.lock = threading.Lock()
        self.start = time.time()

    def add(self, n: int) -> None:
        with self.lock:
            self.done += n

    def pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.done / self.total * 100

    def speed(self) -> float:
        elapsed = time.time() - self.start
        return self.done / elapsed if elapsed > 0 else 0

    def eta(self) -> float:
        sp = self.speed()
        if sp <= 0 or self.total <= 0:
            return 0.0
        return max(0, (self.total - self.done) / sp)


def _head(url: str, timeout: int = 15) -> dict:
    try:
        r = requests.head(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": USER_AGENT})
        return {
            "ok": r.status_code < 400,
            "status": r.status_code,
            "content_length": int(r.headers.get("Content-Length") or 0),
            "accept_ranges": r.headers.get("Accept-Ranges", "").lower()
                             == "bytes",
            "content_type": r.headers.get("Content-Type", ""),
            "final_url": r.url,
            "filename": _filename_from_headers(r, url),
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False, "status": 0, "content_length": 0,
            "accept_ranges": False, "content_type": "",
            "final_url": url, "filename": "", "error": str(exc),
        }


def _filename_from_headers(r, url: str) -> str:
    cd = r.headers.get("Content-Disposition", "")
    if cd:
        m = re.search(
            r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
        if m:
            return unquote(m.group(1).strip())
    path = urlparse(r.url).path
    name = path.split("/")[-1] or "download.bin"
    return unquote(name)


def _single_thread(url: str, out: Path, headers: dict,
                   progress: _Progress, timeout: int = 60,
                   progress_cb=None) -> str:
    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers=headers) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    progress.add(len(chunk))
                    if progress_cb:
                        try:
                            progress_cb(progress.pct(), progress.done,
                                        progress.total, progress.speed(),
                                        progress.eta())
                        except Exception:
                            pass
    except Exception as exc:
        return f"ERROR: {exc}"
    return ""


def _download_range(url: str, start: int, end: int, part_path: Path,
                    headers: dict, progress: _Progress,
                    timeout: int = 60,
                    retries: int = 3,
                    progress_cb=None) -> str:
    h = dict(headers)
    h["Range"] = f"bytes={start}-{end}"

    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=timeout,
                              headers=h) as r:
                if r.status_code not in (200, 206):
                    return f"ERROR: HTTP {r.status_code}"
                with open(part_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        progress.add(len(chunk))
                        if progress_cb:
                            try:
                                progress_cb(progress.pct(),
                                            progress.done,
                                            progress.total,
                                            progress.speed(),
                                            progress.eta())
                            except Exception:
                                pass
                return ""
        except Exception as exc:
            if attempt == retries - 1:
                return f"ERROR: {exc}"
            time.sleep(1.5 ** attempt)
    return "ERROR: 重试耗尽"


def download(url: str, out: str = "", threads: int = 0,
             timeout: int = 60, resume: bool = True,
             progress_cb=None,
             root: Path | None = None) -> dict:
    """智能下载。

    threads: 0 = 自动（根据文件大小）
    resume: 是否启用断点续传
    progress_cb: callable(pct, done, total, speed, eta)

    返回：
        {
          "ok": bool, "path": str, "size": int, "duration": float,
          "threads": int, "resumed": bool, "error": str, "url": str,
        }
    """
    t0 = time.time()
    if not url:
        return {"ok": False, "path": "", "size": 0, "duration": 0,
                "threads": 0, "resumed": False, "error": "需要 url",
                "url": url}

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "path": "", "size": 0, "duration": 0,
                "threads": 0, "resumed": False,
                "error": f"不支持的协议: {parsed.scheme}", "url": url}

    if root is None:
        return {"ok": False, "path": "", "size": 0, "duration": 0,
                "threads": 0, "resumed": False,
                "error": "需要 root", "url": url}

    info = _head(url, timeout=15)
    if not info["ok"] and not info["content_length"]:
        if not info["error"]:
            return {"ok": False, "path": "", "size": 0, "duration": 0,
                    "threads": 0, "resumed": False,
                    "error": f"HEAD 失败: HTTP {info['status']}",
                    "url": url}

    total_size = info["content_length"]
    accept_ranges = info["accept_ranges"]
    final_url = info["final_url"] or url

    if not out:
        out = info["filename"] or "download.bin"
    out_p, perr = _resolve_path(root, out)
    if perr:
        return {"ok": False, "path": "", "size": 0, "duration": 0,
                "threads": 0, "resumed": False, "error": perr, "url": url}

    out_p.parent.mkdir(parents=True, exist_ok=True)

    n_threads = int(threads or 0)
    if n_threads <= 0:
        if total_size and total_size > 20 * 1024 * 1024:
            n_threads = 8
        elif total_size and total_size > 5 * 1024 * 1024:
            n_threads = 4
        elif total_size and total_size > 1 * 1024 * 1024:
            n_threads = 2
        else:
            n_threads = 1
    n_threads = max(1, min(n_threads, MAX_THREADS))

    if not accept_ranges or total_size == 0 or n_threads == 1:
        progress = _Progress(total_size)
        headers = {"User-Agent": USER_AGENT}
        err = _single_thread(final_url, out_p, headers, progress,
                             timeout, progress_cb=progress_cb)
        if err:
            return {"ok": False, "path": "", "size": 0,
                    "duration": round(time.time() - t0, 2),
                    "threads": 1, "resumed": False,
                    "error": err, "url": url}
        return {
            "ok": True, "path": str(out_p),
            "size": progress.done,
            "duration": round(time.time() - t0, 2),
            "threads": 1, "resumed": False,
            "error": "", "url": url,
        }

    part_dir = out_p.parent / f".{out_p.name}.cedric_parts"
    resume_file = part_dir / "resume.json"

    resumed = False
    if resume and part_dir.exists() and resume_file.exists():
        try:
            meta = _json.loads(resume_file.read_text(encoding="utf-8"))
            if (meta.get("url") == url
                    and meta.get("total") == total_size
                    and meta.get("threads") == n_threads):
                resumed = True
        except Exception:
            resumed = False

    if not resumed:
        if part_dir.exists():
            shutil.rmtree(part_dir, ignore_errors=True)
        part_dir.mkdir(parents=True, exist_ok=True)
        resume_file.write_text(_json.dumps({
            "url": url,
            "total": total_size,
            "threads": n_threads,
            "created": time.time(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    chunk = total_size // n_threads
    ranges = []
    for i in range(n_threads):
        start = i * chunk
        end = (start + chunk - 1) if i < n_threads - 1 \
            else (total_size - 1)
        ranges.append((i, start, end))

    completed_parts: list = []
    for i, start, end in ranges:
        part_file = part_dir / f"part_{i:04d}"
        if part_file.exists() and \
                part_file.stat().st_size == (end - start + 1):
            completed_parts.append(i)

    progress = _Progress(total_size)
    for i in completed_parts:
        part_file = part_dir / f"part_{i:04d}"
        progress.add(part_file.stat().st_size)

    headers = {"User-Agent": USER_AGENT}

    def _dl(idx: int, start: int, end: int) -> tuple:
        if idx in completed_parts:
            return idx, ""
        part_file = part_dir / f"part_{idx:04d}"
        err = _download_range(final_url, start, end, part_file,
                              headers, progress, timeout,
                              progress_cb=progress_cb)
        return idx, err

    errors: list = []
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = {
            pool.submit(_dl, i, s, e): (i, s, e)
            for i, s, e in ranges
        }
        for fut in as_completed(futures):
            idx, err = fut.result()
            if err:
                errors.append((idx, err))

    if errors:
        return {
            "ok": False, "path": "",
            "size": progress.done,
            "duration": round(time.time() - t0, 2),
            "threads": n_threads, "resumed": resumed,
            "error": f"{len(errors)} 个分片失败: {errors[0][1]}",
            "url": url,
        }

    try:
        with open(out_p, "wb") as out_f:
            for i, _, _ in ranges:
                part_file = part_dir / f"part_{i:04d}"
                with open(part_file, "rb") as pf:
                    shutil.copyfileobj(pf, out_f, length=1024 * 1024)
    except OSError as exc:
        return {"ok": False, "path": "", "size": progress.done,
                "duration": round(time.time() - t0, 2),
                "threads": n_threads, "resumed": resumed,
                "error": f"合并失败: {exc}", "url": url}

    shutil.rmtree(part_dir, ignore_errors=True)

    return {
        "ok": True,
        "path": str(out_p),
        "size": out_p.stat().st_size,
        "duration": round(time.time() - t0, 2),
        "threads": n_threads,
        "resumed": resumed,
        "error": "",
        "url": url,
    }


def download_preview(url: str, out: str = "", threads: int = 0,
                     root: Path | None = None) -> tuple:
    """下载预览。返回 (preview, is_write, error, meta)。"""
    if root is None:
        return "", False, "ERROR: 需要 root", {}
    if not url:
        return "", False, "ERROR: 需要 url", {}

    info = _head(url, timeout=10)
    if not info["ok"]:
        err_msg = (info.get("error")
                   or f"HTTP {info['status']}")
        return ("", False,
                f"ERROR: 无法访问 {url}（{err_msg}）", {})

    size = info["content_length"]
    size_str = _human_size(size) if size else "（未知）"
    accept = "支持" if info["accept_ranges"] else "不支持"

    auto_threads = int(threads or 0)
    if auto_threads <= 0:
        if size > 20 * 1024 * 1024:
            auto_threads = 8
        elif size > 5 * 1024 * 1024:
            auto_threads = 4
        elif size > 1024 * 1024:
            auto_threads = 2
        else:
            auto_threads = 1
    if not info["accept_ranges"]:
        auto_threads = 1

    filename = out or info["filename"] or "download.bin"

    preview = [
        f"URL: {url}",
        f"文件名: {filename}",
        f"大小: {size_str}",
        f"类型: {info['content_type'] or '未知'}",
        f"Range: {accept}",
        f"计划线程: {auto_threads}",
        f"断点续传: 是",
    ]
    meta = {
        "url": url,
        "final_url": info["final_url"],
        "filename": filename,
        "size": size,
        "threads": auto_threads,
        "accept_ranges": info["accept_ranges"],
    }
    return "\n".join(preview), True, "", meta


def _human_size(n: int) -> str:
    if n <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"