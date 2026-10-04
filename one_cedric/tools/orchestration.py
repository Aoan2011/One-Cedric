"""容器编排：Docker Compose + Kubernetes。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def _compose_cmd() -> tuple[list[str] | None, str]:
    """优先 docker compose（v2），其次 docker-compose（v1）。"""
    if shutil.which("docker"):
        try:
            r = subprocess.run(["docker", "compose", "version"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return ["docker", "compose"], ""
        except Exception:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"], ""
    return None, "ERROR: 需要 docker compose 或 docker-compose 命令"


def _kubectl() -> str:
    return shutil.which("kubectl") or ""


def _run(cmd: list[str], cwd: str = "", timeout: int = 120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, cwd=cwd or None)
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return 127, "", f"命令不存在: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"超时（{timeout}s）"
    except OSError as exc:
        return 1, "", str(exc)


# ═══════════════════════════════════════════════════════════════════════ #
# Docker Compose
# ═══════════════════════════════════════════════════════════════════════ #

def compose_status(file: str = "docker-compose.yml", root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return err

    p, perr = _resolve_path(root, file)
    if perr:
        return perr

    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + ["ps"]

    rc, out, errout = _run(args, cwd=work_dir, timeout=30)
    if rc != 0:
        return f"ERROR: {errout[:400] or out[:400]}"
    return out.strip() or "（无容器）"


def compose_logs(file: str = "docker-compose.yml", service: str = "",
                 tail: int = 100, root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return err

    p, perr = _resolve_path(root, file)
    if perr:
        return perr

    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + \
           ["logs", "--no-color", "--tail", str(_as_int(tail, 100))]
    if service:
        args.append(service)

    rc, out, errout = _run(args, cwd=work_dir, timeout=60)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out[-20000:].strip() or "（无日志）"


def compose_config(file: str = "docker-compose.yml",
                   root: Path | None = None) -> str:
    if root is None:
        return "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return err
    p, perr = _resolve_path(root, file)
    if perr:
        return perr
    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + ["config"]
    rc, out, errout = _run(args, cwd=work_dir, timeout=30)
    if rc != 0:
        return f"ERROR: {errout[:500]}"
    return out[:15000]


def compose_up(file: str = "docker-compose.yml", detach: bool = True,
               service: str = "", build: bool = False,
               root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return "", False, err
    p, perr = _resolve_path(root, file)
    if perr:
        return "", False, perr

    preview = [f"工作目录: {p.parent if p.is_file() else p}",
               f"配置: {file}"]
    if service:
        preview.append(f"服务: {service}")
    else:
        preview.append("服务: 全部")
    preview.append(f"模式: {'后台' if detach else '前台'}")
    if build:
        preview.append("构建: 是")
    return "\n".join(preview), True, ""


def compose_up_apply(file, detach, service, build, root) -> str:
    cmd, _ = _compose_cmd()
    p, _ = _resolve_path(root, file)
    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + ["up"]
    if detach:
        args.append("-d")
    if build:
        args.append("--build")
    if service:
        args.append(service)

    rc, out, errout = _run(args, cwd=work_dir, timeout=600)
    if rc != 0:
        return f"ERROR: {errout[-500:]}"
    return f"已启动\n{out[-2000:]}"


def compose_down(file: str = "docker-compose.yml", volumes: bool = False,
                 remove_images: str = "",
                 root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return "", False, err
    p, perr = _resolve_path(root, file)
    if perr:
        return "", False, perr

    preview = [f"工作目录: {p.parent if p.is_file() else p}",
               f"配置: {file}",
               "将停止并删除所有容器"]
    if volumes:
        preview.append("⚠ 同时删除卷")
    if remove_images:
        preview.append(f"⚠ 删除镜像: {remove_images}")
    return "\n".join(preview), True, ""


def compose_down_apply(file, volumes, remove_images, root) -> str:
    cmd, _ = _compose_cmd()
    p, _ = _resolve_path(root, file)
    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + ["down"]
    if volumes:
        args.append("-v")
    if remove_images:
        args += ["--rmi", remove_images]

    rc, out, errout = _run(args, cwd=work_dir, timeout=300)
    if rc != 0:
        return f"ERROR: {errout[-400:]}"
    return f"已停止\n{out[-1000:]}"


def compose_restart(file: str = "docker-compose.yml", service: str = "",
                    root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    cmd, err = _compose_cmd()
    if err:
        return "", False, err
    p, perr = _resolve_path(root, file)
    if perr:
        return "", False, perr
    preview = f"将重启 {service or '全部服务'}（{file}）"
    return preview, True, ""


def compose_restart_apply(file, service, root) -> str:
    cmd, _ = _compose_cmd()
    p, _ = _resolve_path(root, file)
    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + ["restart"]
    if service:
        args.append(service)
    rc, out, errout = _run(args, cwd=work_dir, timeout=180)
    if rc != 0:
        return f"ERROR: {errout[-400:]}"
    return f"已重启\n{out[-1000:]}"


def compose_exec(file: str = "docker-compose.yml", service: str = "",
                 command: str = "", root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not service or not command:
        return "", False, "ERROR: 需要 service 和 command"
    cmd, err = _compose_cmd()
    if err:
        return "", False, err
    p, perr = _resolve_path(root, file)
    if perr:
        return "", False, perr
    return (f"将在 {service} 里执行:\n  {command}\n"
            f"（{file}）"), True, ""


def compose_exec_apply(file, service, command, root) -> str:
    cmd, _ = _compose_cmd()
    p, _ = _resolve_path(root, file)
    work_dir = str(p.parent if p.is_file() else p)
    args = cmd + (["-f", p.name] if p.is_file() else []) + \
           ["exec", "-T", service, "sh", "-c", command]
    rc, out, errout = _run(args, cwd=work_dir, timeout=120)
    if rc != 0:
        return f"ERROR(rc={rc}):\n{out[-1000:]}\n{errout[-500:]}"
    return out[-5000:].strip() or "(无输出)"


# ═══════════════════════════════════════════════════════════════════════ #
# Kubernetes
# ═══════════════════════════════════════════════════════════════════════ #

def k8s_get(resource: str = "pods", namespace: str = "",
            all_namespaces: bool = False, output: str = "") -> str:
    if not _kubectl():
        return "ERROR: 需要 kubectl"
    args = ["kubectl", "get", resource]
    if all_namespaces:
        args.append("-A")
    elif namespace:
        args += ["-n", namespace]
    if output:
        args += ["-o", output]
    rc, out, errout = _run(args, timeout=30)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out


def k8s_describe(resource: str, name: str = "", namespace: str = "") -> str:
    if not _kubectl():
        return "ERROR: 需要 kubectl"
    if not resource:
        return "ERROR: 需要 resource（如 pod / deployment）"
    args = ["kubectl", "describe", resource]
    if name:
        args.append(name)
    if namespace:
        args += ["-n", namespace]
    rc, out, errout = _run(args, timeout=30)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out[:15000]


def k8s_logs(pod: str, namespace: str = "", container: str = "",
             tail: int = 100, previous: bool = False) -> str:
    if not _kubectl():
        return "ERROR: 需要 kubectl"
    if not pod:
        return "ERROR: 需要 pod"
    args = ["kubectl", "logs", pod,
            "--tail", str(_as_int(tail, 100))]
    if namespace:
        args += ["-n", namespace]
    if container:
        args += ["-c", container]
    if previous:
        args.append("--previous")
    rc, out, errout = _run(args, timeout=30)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out[-20000:]


def k8s_contexts() -> str:
    if not _kubectl():
        return "ERROR: 需要 kubectl"
    rc, out, errout = _run(["kubectl", "config", "get-contexts"], timeout=15)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out


def k8s_apply(file: str = "", manifest: str = "",
              namespace: str = "", root: Path | None = None):
    if not _kubectl():
        return "", False, "ERROR: 需要 kubectl"

    if file and root is None:
        return "", False, "ERROR: file 需要 root"
    if not file and not manifest:
        return "", False, "ERROR: 需要 file 或 manifest"

    preview = []
    if file:
        p, perr = _resolve_path(root, file)
        if perr:
            return "", False, perr
        if not p.exists():
            return "", False, f"ERROR: 文件不存在: {file}"
        preview.append(f"文件: {file}")
    else:
        preview.append(f"内联 manifest（{len(manifest)} 字符）")
    if namespace:
        preview.append(f"命名空间: {namespace}")
    preview.append("⚠ 将创建/更新集群资源")
    return "\n".join(preview), True, ""


def k8s_apply_apply(file, manifest, namespace, root) -> str:
    import tempfile
    args = ["kubectl", "apply"]
    if namespace:
        args += ["-n", namespace]

    if file:
        p, _ = _resolve_path(root, file)
        args += ["-f", str(p)]
        rc, out, errout = _run(args, timeout=120)
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml",
                                         delete=False, encoding="utf-8") as tf:
            tf.write(manifest)
            tmp = tf.name
        try:
            args += ["-f", tmp]
            rc, out, errout = _run(args, timeout=120)
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass

    if rc != 0:
        return f"ERROR: {errout[:500]}"
    return f"已应用\n{out[-2000:]}"


def k8s_delete(resource: str, name: str = "", namespace: str = "",
               file: str = "", root: Path | None = None):
    if not _kubectl():
        return "", False, "ERROR: 需要 kubectl"
    if not resource and not file:
        return "", False, "ERROR: 需要 resource 或 file"

    preview = []
    if file:
        if root is None:
            return "", False, "ERROR: file 需要 root"
        p, perr = _resolve_path(root, file)
        if perr:
            return "", False, perr
        preview.append(f"从文件删除: {file}")
    else:
        preview.append(f"删除 {resource}/{name or '*'}")
    if namespace:
        preview.append(f"命名空间: {namespace}")
    preview.append("⚠ 不可撤销")
    return "\n".join(preview), True, ""


def k8s_delete_apply(resource, name, namespace, file, root) -> str:
    args = ["kubectl", "delete"]
    if file:
        p, _ = _resolve_path(root, file)
        args += ["-f", str(p)]
    else:
        args.append(resource)
        if name:
            args.append(name)
    if namespace:
        args += ["-n", namespace]

    rc, out, errout = _run(args, timeout=120)
    if rc != 0:
        return f"ERROR: {errout[:500]}"
    return f"已删除\n{out[-1000:]}"


def k8s_scale(resource: str = "deployment", name: str = "",
              replicas: int = 1, namespace: str = ""):
    if not _kubectl():
        return "", False, "ERROR: 需要 kubectl"
    if not name:
        return "", False, "ERROR: 需要 name"
    return (f"将把 {resource}/{name} 扩展到 {replicas} 副本"
            + (f"（ns={namespace}）" if namespace else "")), True, ""


def k8s_scale_apply(resource, name, replicas, namespace) -> str:
    args = ["kubectl", "scale", f"{resource}/{name}",
            f"--replicas={_as_int(replicas, 1)}"]
    if namespace:
        args += ["-n", namespace]
    rc, out, errout = _run(args, timeout=60)
    if rc != 0:
        return f"ERROR: {errout[:400]}"
    return out.strip() or "已调整"


def k8s_exec(pod: str, command: str, namespace: str = "",
             container: str = ""):
    if not _kubectl():
        return "", False, "ERROR: 需要 kubectl"
    if not pod or not command:
        return "", False, "ERROR: 需要 pod 和 command"
    return (f"将在 pod/{pod} 执行:\n  {command}"
            + (f"  容器={container}" if container else "")
            + (f"  ns={namespace}" if namespace else "")), True, ""


def k8s_exec_apply(pod, command, namespace, container) -> str:
    args = ["kubectl", "exec", pod]
    if namespace:
        args += ["-n", namespace]
    if container:
        args += ["-c", container]
    args += ["--", "sh", "-c", command]
    rc, out, errout = _run(args, timeout=120)
    if rc != 0:
        return f"ERROR(rc={rc}):\n{out[-1000:]}\n{errout[-400:]}"
    return out[-5000:].strip() or "(无输出)"


def k8s_top(kind: str = "pods", namespace: str = "",
            all_namespaces: bool = False) -> str:
    if not _kubectl():
        return "ERROR: 需要 kubectl"
    args = ["kubectl", "top", kind]
    if all_namespaces:
        args.append("-A")
    elif namespace:
        args += ["-n", namespace]
    rc, out, errout = _run(args, timeout=20)
    if rc != 0:
        return f"ERROR: {errout[:400]}（metrics-server 可能未安装）"
    return out