"""网络探测：ping / 端口扫描 / traceroute / 测速 / 下载。"""
from __future__ import annotations

import platform
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from .sandbox import _resolve_path


def ping_host(host: str, count: int = 4, timeout: int = 10) -> str:
    if not host:
        return "ERROR: host 不能为空"
    try:
        n = max(1, min(int(count), 20))
    except (TypeError, ValueError):
        n = 4

    sys_name = platform.system()
    if sys_name == "Windows":
        cmd = ["ping", "-n", str(n), host]
    else:
        cmd = ["ping", "-c", str(n), host]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=max(5, n * 3))
    except FileNotFoundError:
        return "ERROR: 找不到 ping 命令"
    except subprocess.TimeoutExpired:
        return f"ERROR: ping 超时（{host}）"

    out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    return f"$ {' '.join(cmd)}\n\n{out.strip()}"


_PORT_SERVICES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    587: "SMTP-sub", 993: "IMAPS", 995: "POP3S",
    1433: "MSSQL", 1521: "Oracle", 2049: "NFS",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    5900: "VNC", 6379: "Redis", 8080: "HTTP-alt",
    8443: "HTTPS-alt", 9200: "Elasticsearch",
    11211: "Memcached", 27017: "MongoDB",
}


def _probe_port(host: str, port: int, timeout: float) -> tuple:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return port, True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return port, False


def port_scan(host: str, ports: str = "common",
              timeout: float = 1.0, workers: int = 100) -> str:
    if not host:
        return "ERROR: host 不能为空"

    if ports in ("", "common", None):
        port_list = list(_PORT_SERVICES.keys())
    elif ports == "1-1024":
        port_list = list(range(1, 1025))
    elif ports == "1-65535":
        port_list = list(range(1, 65536))
    else:
        port_list = []
        for part in str(ports).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    port_list.extend(range(int(a), int(b) + 1))
                except ValueError:
                    continue
            else:
                try:
                    port_list.append(int(part))
                except ValueError:
                    continue

    if not port_list:
        return "ERROR: ports 无效"
    if len(port_list) > 20000:
        return f"ERROR: 端口太多（{len(port_list)}），上限 20000"

    try:
        t = max(0.1, min(float(timeout), 5.0))
    except (TypeError, ValueError):
        t = 1.0
    try:
        w = max(1, min(int(workers), 500))
    except (TypeError, ValueError):
        w = 100

    t0 = time.time()
    open_ports = []
    with ThreadPoolExecutor(max_workers=w) as ex:
        futures = {ex.submit(_probe_port, host, p, t): p
                   for p in port_list}
        for fut in as_completed(futures):
            port, ok = fut.result()
            if ok:
                open_ports.append(port)

    open_ports.sort()
    elapsed = time.time() - t0

    lines = [f"目标: {host}",
             f"扫描 {len(port_list)} 个端口 · {elapsed:.2f}s",
             f"开放: {len(open_ports)}", ""]
    for p in open_ports:
        svc = _PORT_SERVICES.get(p, "")
        lines.append(f"  ✓ {p:<6} {svc}")
    if not open_ports:
        lines.append("  （无开放端口）")
    return "\n".join(lines)


def traceroute(host: str, max_hops: int = 20) -> str:
    if not host:
        return "ERROR: host 不能为空"
    try:
        hops = max(1, min(int(max_hops), 64))
    except (TypeError, ValueError):
        hops = 20

    if platform.system() == "Windows":
        cmd = ["tracert", "-h", str(hops), "-w", "2000", host]
    else:
        cmd = ["traceroute", "-m", str(hops), "-w", "2", host]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=hops * 5)
    except FileNotFoundError:
        return "ERROR: 找不到 traceroute/tracert 命令"
    except subprocess.TimeoutExpired:
        return f"ERROR: 超时"

    return (r.stdout or "").strip() or "(无输出)"


def download(url: str, out: str = "", timeout: int = 60,
             max_mb: int = 500,
             root=None) -> tuple:
    """单线程下载（旧接口，保留兼容）。

    新代码请用 downloader.download()。
    返回 (preview, is_write, error)。
    """
    if not url:
        return "", False, "ERROR: url 不能为空"
    if root is None:
        return "", False, "ERROR: 需要 root"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "", False, f"ERROR: 不支持的协议: {parsed.scheme}"

    if not out:
        name = parsed.path.split("/")[-1] or "download.bin"
        out = name

    out_p, err = _resolve_path(root, out)
    if err:
        return "", False, err

    return (f"下载: {url}\n"
            f"保存到: {out_p.relative_to(root)}\n"
            f"超时: {timeout}s  上限: {max_mb} MB"), True, ""


def download_apply(url: str, out: str, timeout: int, max_mb: int,
                   root) -> str:
    """单线程下载实现（旧接口，保留兼容）。"""
    import requests

    parsed = urlparse(url)
    if not out:
        out = parsed.path.split("/")[-1] or "download.bin"
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    try:
        t = max(5, min(int(timeout), 600))
    except (TypeError, ValueError):
        t = 60
    try:
        limit = max(1, min(int(max_mb), 5000)) * 1024 * 1024
    except (TypeError, ValueError):
        limit = 500 * 1024 * 1024

    t0 = time.time()
    try:
        with requests.get(url, stream=True, timeout=t,
                          headers={"User-Agent": "OneCedric/1.0"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            if total and total > limit:
                return f"ERROR: 文件大小 {total} 超过上限 {limit}"

            downloaded = 0
            with open(out_p, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > limit:
                        out_p.unlink(missing_ok=True)
                        return f"ERROR: 超过上限（{limit}）"
    except Exception as exc:
        return f"ERROR: 下载失败: {exc}"

    elapsed = time.time() - t0
    speed = downloaded / elapsed if elapsed > 0 else 0
    return (f"已下载 → {out_p.relative_to(root)}\n"
            f"{downloaded} bytes · {elapsed:.2f}s · "
            f"{speed / 1024:.1f} KB/s")


def get_public_ip() -> str:
    """查询公网出口 IP。"""
    try:
        import requests
    except ImportError:
        return "ERROR: 需要 requests"

    services = [
        ("https://api.ipify.org?format=json", "json", "ip"),
        ("https://ifconfig.me/ip", "text", None),
        ("https://icanhazip.com", "text", None),
    ]
    errors = []
    for url, kind, key in services:
        try:
            r = requests.get(url, timeout=8,
                             headers={"User-Agent": "curl/8.0.0"})
            if r.status_code == 200:
                if kind == "json":
                    data = r.json()
                    return f"公网 IP: {data.get(key, '?')}"
                return f"公网 IP: {r.text.strip()}"
        except Exception as exc:
            errors.append(str(exc))
    return f"ERROR: 所有服务都失败\n" + "\n".join(errors)