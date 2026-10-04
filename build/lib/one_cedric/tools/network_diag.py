"""网络诊断工具（只读）。"""
from __future__ import annotations

import datetime as _dt
import socket
import ssl
from urllib.parse import urlparse

import requests


def dns_lookup(host: str, record_type: str = "A") -> str:
    if not host:
        return "ERROR: host 不能为空"
    rt = (record_type or "A").upper()

    try:
        if rt == "A":
            infos = socket.getaddrinfo(host, None, socket.AF_INET)
            ips = sorted({i[4][0] for i in infos})
            return f"{host} A 记录:\n" + "\n".join(f"  {ip}" for ip in ips)
        if rt == "AAAA":
            infos = socket.getaddrinfo(host, None, socket.AF_INET6)
            ips = sorted({i[4][0] for i in infos})
            return f"{host} AAAA 记录:\n" + "\n".join(f"  {ip}" for ip in ips)
        if rt in ("MX", "TXT", "NS", "CNAME"):
            try:
                import dns.resolver
            except ImportError:
                return f"ERROR: {rt} 记录查询需要 dnspython（pip install dnspython）"
            try:
                ans = dns.resolver.resolve(host, rt)
                return f"{host} {rt} 记录:\n" + "\n".join(f"  {r}" for r in ans)
            except Exception as exc:
                return f"ERROR: 查询失败: {exc}"
        return f"ERROR: 不支持的记录类型: {rt}（支持 A/AAAA/MX/TXT/NS/CNAME）"
    except socket.gaierror as exc:
        return f"ERROR: DNS 解析失败: {exc}"


def ssl_check(url: str, port: int = 0) -> str:
    if not url:
        return "ERROR: url 不能为空"
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return "ERROR: 无法解析主机名"
    if not port:
        port = parsed.port or 443

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                proto = ssock.version()
                cipher = ssock.cipher()
    except socket.gaierror as exc:
        return f"ERROR: DNS 失败: {exc}"
    except socket.timeout:
        return f"ERROR: 连接 {host}:{port} 超时"
    except ssl.SSLError as exc:
        return f"ERROR: SSL 错误: {exc}"
    except OSError as exc:
        return f"ERROR: 连接失败: {exc}"

    lines = [
        f"主机: {host}:{port}",
        f"协议: {proto}",
        f"加密算法: {cipher[0]}  ({cipher[1]} bits)",
    ]

    if cert:
        lines.append("")
        lines.append("证书:")
        lines.append(f"  主题: {dict(x[0] for x in cert.get('subject', []))}")
        lines.append(f"  颁发者: {dict(x[0] for x in cert.get('issuer', []))}")
        lines.append(f"  有效期从: {cert.get('notBefore', '?')}")
        lines.append(f"  有效期至: {cert.get('notAfter', '?')}")

        try:
            expire = _dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
            days_left = (expire - _dt.datetime.utcnow()).days
            lines.append(f"  剩余: {days_left} 天")
        except Exception:
            pass

        sans = cert.get("subjectAltName", [])
        if sans:
            lines.append(f"  SAN ({len(sans)}):")
            for typ, val in sans[:10]:
                lines.append(f"    {typ}: {val}")
            if len(sans) > 10:
                lines.append(f"    ... 还有 {len(sans) - 10} 个")

    return "\n".join(lines)


def http_head(url: str, timeout: int = 10) -> str:
    if not url:
        return "ERROR: url 不能为空"
    if "://" not in url:
        url = "http://" + url

    try:
        t = max(1, min(int(timeout), 60))
    except (TypeError, ValueError):
        t = 10

    try:
        r = requests.head(url, timeout=t, allow_redirects=True,
                          headers={"User-Agent": "OneCedric/1.0"})
    except requests.exceptions.RequestException as exc:
        return f"ERROR: 请求失败: {exc}"

    lines = [
        f"URL: {url}",
        f"状态: {r.status_code} {r.reason}",
        f"耗时: {r.elapsed.total_seconds() * 1000:.0f} ms",
        f"最终 URL: {r.url}",
        "",
        "响应头:",
    ]
    for k, v in r.headers.items():
        lines.append(f"  {k}: {v}")

    return "\n".join(lines)