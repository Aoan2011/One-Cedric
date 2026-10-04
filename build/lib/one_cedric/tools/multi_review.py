"""多 agent 代码审查：并行派 3 个 sub-agent 分维度审查代码。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .sandbox import _resolve_path


DEFAULT_DIMENSIONS = [
    {
        "key": "security",
        "name": "安全",
        "focus": (
            "认证/授权绕过、SQL/命令注入、密钥泄露、XSS/CSRF、"
            "路径穿越、越权、整数溢出、竞态、不安全反序列化、"
            "依赖风险、日志泄露敏感信息"
        ),
    },
    {
        "key": "performance",
        "name": "性能",
        "focus": (
            "N+1 查询、循环内 IO、无界循环、内存泄漏、"
            "不必要的拷贝、重复计算、同步阻塞、缺失超时/重试、"
            "低效数据结构、缓存缺失、并发利用不当"
        ),
    },
    {
        "key": "readability",
        "name": "可读性",
        "focus": (
            "命名是否达意、函数/类复杂度、魔法数字、"
            "注释缺失或过时、死代码、重复逻辑、"
            "类型标注、异常处理清晰度、模块耦合"
        ),
    },
]


def multi_review(path: str, root: Path,
                 dimensions: list | None = None,
                 max_steps: int = 5,
                 timeout: int = 180,
                 parent=None) -> dict:
    """多 agent 审查。返回 dict:
        {
          "ok": bool,
          "path": str,
          "results": {key: {"name","ok","answer","error","duration"}},
          "summary": str,
          "duration": float,
        }
    """
    if parent is None:
        return {"ok": False, "path": path,
                "results": {}, "summary": "",
                "error": "需要 parent copilot 实例"}

    p, err = _resolve_path(root, path)
    if err:
        return {"ok": False, "path": path, "results": {},
                "summary": "", "error": err}
    if not p.exists() or not p.is_file():
        return {"ok": False, "path": path, "results": {},
                "summary": "", "error": f"文件不存在: {path}"}

    try:
        raw = p.read_bytes()
    except OSError as exc:
        return {"ok": False, "path": path, "results": {},
                "summary": "", "error": str(exc)}

    # 二进制检测
    head = raw[:4096]
    if b"\x00" in head:
        return {"ok": False, "path": path, "results": {},
                "summary": "", "error": "二进制文件无法审查"}

    text = raw.decode("utf-8", errors="replace")
    MAX_CHARS = 40000
    truncated = False
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n\n... (截断，原文件 {len(text)} 字符)"
        truncated = True

    dims = dimensions or DEFAULT_DIMENSIONS
    # 只支持 keys 过滤
    if isinstance(dims, list) and dims and isinstance(dims[0], str):
        keys = set(dims)
        dims = [d for d in DEFAULT_DIMENSIONS if d["key"] in keys]
        if not dims:
            dims = DEFAULT_DIMENSIONS

    from .subagent import run_subagent
    import time as _time

    # 临时屏蔽 stream hook，避免并行推送乱序
    old_hook = getattr(parent, "_stream_hook", None)
    try:
        parent._stream_hook = None
    except Exception:
        pass

    results: dict = {}
    t0 = _time.time()

    def _run_one(dim):
        task = (
            f"审查以下代码的「{dim['name']}」方面：\n"
            f"{dim['focus']}\n\n"
            f"文件: {path}\n"
            f"请按以下格式输出：\n"
            f"## 概要\n（一句话）\n\n"
            f"## 问题清单\n"
            f"- [严重程度] 行号: 问题描述 → 建议\n"
            f"  （严重程度：严重 / 中 / 低）\n\n"
            f"## 亮点\n（可选，做得好的地方）\n\n"
            f"代码：\n```\n{text}\n```\n"
        )
        dim_t0 = _time.time()
        try:
            r = run_subagent(parent, task=task, mode="code",
                             max_steps=max_steps, timeout=timeout)
        except Exception as exc:
            r = {"ok": False, "answer": "", "error":
                 f"{type(exc).__name__}: {exc}",
                 "duration": round(_time.time() - dim_t0, 2)}
        r["name"] = dim["name"]
        r["duration"] = r.get("duration") or round(_time.time() - dim_t0, 2)
        return dim["key"], r

    try:
        with ThreadPoolExecutor(max_workers=len(dims)) as pool:
            futures = [pool.submit(_run_one, d) for d in dims]
            for fut in as_completed(futures):
                try:
                    key, r = fut.result()
                    results[key] = r
                except Exception as exc:
                    results["_err_" + str(len(results))] = {
                        "name": "?", "ok": False,
                        "answer": "", "error": str(exc), "duration": 0,
                    }
    finally:
        try:
            parent._stream_hook = old_hook
        except Exception:
            pass

    total = round(_time.time() - t0, 2)

    # 汇总
    summary_lines = [
        f"多 agent 审查：{path}",
        f"耗时: {total}s" + ("（文件已截断）" if truncated else ""),
        "",
    ]
    for dim in dims:
        r = results.get(dim["key"], {})
        icon = "✓" if r.get("ok") else "✗"
        dur = r.get("duration", 0)
        summary_lines.append(
            f"【{icon} {dim['name']}】 {dur}s")
        if r.get("answer"):
            summary_lines.append(r["answer"])
        elif r.get("error"):
            summary_lines.append(f"  错误: {r['error']}")
        summary_lines.append("")

    ok = any(r.get("ok") for r in results.values())

    return {
        "ok": ok,
        "path": path,
        "results": results,
        "summary": "\n".join(summary_lines),
        "duration": total,
        "truncated": truncated,
    }