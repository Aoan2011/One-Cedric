"""Git 快照：改文件前自动 stash，支持回滚。"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path


def _run_git(root: Path, args: list, timeout: int = 15) -> tuple:
    try:
        r = subprocess.run(
            ["git"] + args, cwd=str(root),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


def _git_available(root: Path) -> bool:
    """检查是否是 git 仓库。"""
    code, out, _ = _run_git(root, ["rev-parse", "--git-dir"])
    return code == 0


def git_make_snapshot(root: Path) -> dict | None:
    """创建快照。

    策略：
      1. 记录 HEAD
      2. git stash push --include-untracked（保留当前工作状态）
      3. 立即 git stash pop（恢复工作区，但保留了 stash）
      4. 记录未跟踪文件清单

    返回快照信息或 None。
    """
    if not _git_available(root):
        return None

    snap: dict = {
        "ts": time.time(),
        "head_sha": "",
        "stash_sha": "",
        "untracked": [],
    }

    # HEAD
    code, out, _ = _run_git(root, ["rev-parse", "HEAD"])
    if code == 0:
        snap["head_sha"] = out.strip()

    # 未跟踪文件清单（用于回滚时删除新建）
    code, out, _ = _run_git(root, ["ls-files", "--others",
                                     "--exclude-standard"])
    if code == 0:
        snap["untracked"] = [l for l in out.splitlines() if l.strip()]

    # 尝试创建 stash（有改动才创建）
    code, out, _ = _run_git(root, ["status", "--porcelain"])
    if code != 0 or not out.strip():
        # 没有改动，只记录 HEAD
        return snap if snap["head_sha"] else None

    code, out, err = _run_git(
        root,
        ["stash", "push", "--include-untracked", "-m",
         f"one-cedric snapshot {int(snap['ts'])}"],
        timeout=30,
    )
    if code != 0:
        return snap if snap["head_sha"] else None

    # 拿 stash sha
    code, out, _ = _run_git(root, ["rev-parse", "stash@{0}"])
    if code == 0:
        snap["stash_sha"] = out.strip()

    # 立即 pop 回工作区
    _run_git(root, ["stash", "pop"], timeout=30)

    return snap


def git_rollback(root: Path, snap: dict) -> tuple:
    """回滚到快照。

    返回 (ok, msg, affected_files)
    """
    if not _git_available(root):
        return False, "当前工作目录不是 git 仓库", []

    affected = []

    # 1. 恢复被追踪文件的改动（checkout HEAD 或 stash）
    head_sha = snap.get("head_sha", "")
    if head_sha:
        # 拿到当前 HEAD
        code, cur_head, _ = _run_git(root, ["rev-parse", "HEAD"])
        cur_head = cur_head.strip() if code == 0 else ""

        if cur_head and cur_head != head_sha:
            # HEAD 变了（说明有 commit）
            code, out, err = _run_git(
                root, ["reset", "--soft", head_sha], timeout=15)
            if code != 0:
                return False, f"reset 失败: {err}", []

    # 尝试恢复 stash
    stash_sha = snap.get("stash_sha", "")
    if stash_sha:
        # 找到对应的 stash index
        code, out, _ = _run_git(root, ["stash", "list"])
        target_idx = -1
        for i, line in enumerate(out.splitlines()):
            if stash_sha in line:
                target_idx = i
                break

        if target_idx >= 0:
            ref = f"stash@{{{target_idx}}}"
            # 先尝试 checkout stash 里的内容
            code, out, err = _run_git(
                root,
                ["checkout", ref, "--", "."],
                timeout=30,
            )
            if code != 0:
                # 用 apply 更安全（保留 stash）
                code, out, err = _run_git(
                    root,
                    ["stash", "apply", ref],
                    timeout=30,
                )
                if code != 0:
                    return False, f"stash 恢复失败: {err}", []

            # 检查是否有内容变化
            code, out, _ = _run_git(root, ["diff", "--name-only"])
            if code == 0:
                affected.extend([l for l in out.splitlines() if l.strip()])

            # 删除 stash
            _run_git(root, ["stash", "drop", ref], timeout=10)

    # 2. 删除比快照时新增的未跟踪文件
    prev_untracked = set(snap.get("untracked", []))
    code, out, _ = _run_git(root, ["ls-files", "--others",
                                     "--exclude-standard"])
    if code == 0:
        now_untracked = set(l for l in out.splitlines() if l.strip())
        new_files = now_untracked - prev_untracked
        for f in new_files:
            try:
                fp = root / f
                if fp.is_file():
                    fp.unlink()
                    affected.append(f)
            except OSError:
                pass

    return True, "已回滚", affected