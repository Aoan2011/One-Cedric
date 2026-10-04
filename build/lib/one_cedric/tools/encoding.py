"""编码/哈希/加密相关工具。"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
from pathlib import Path

from .sandbox import _resolve_path


def base64_codec(action: str, data: str = "", file: str = "",
                 root: Path | None = None) -> str:
    action = (action or "").lower()
    if action not in ("encode", "decode"):
        return "ERROR: action 必须是 encode 或 decode"
    raw: bytes = b""
    source = ""
    if file:
        if root is None:
            return "ERROR: file 参数需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return err
        if not p.exists() or not p.is_file():
            return f"ERROR: 文件不存在: {file}"
        try:
            raw = p.read_bytes()
            source = f"file: {file}"
        except OSError as exc:
            return f"ERROR: 读取失败: {exc}"
    elif data:
        raw = data.encode("utf-8")
        source = f"text: {len(data)} chars"
    else:
        return "ERROR: 需要 data 或 file"
    try:
        if action == "encode":
            out = base64.b64encode(raw).decode("ascii")
        else:
            out = base64.b64decode(raw, validate=True).decode(
                "utf-8", errors="replace")
    except Exception as exc:
        return f"ERROR: {action} 失败: {exc}"
    return f"{source}\naction: {action}\n---\n{out}"


def hash_text(text: str, algorithm: str = "sha256") -> str:
    if text is None:
        return "ERROR: text 不能为空"
    algo = (algorithm or "sha256").lower()
    if algo not in ("md5", "sha1", "sha256", "sha512", "blake2b"):
        return f"ERROR: 不支持的算法: {algo}"
    h = hashlib.new(algo, text.encode("utf-8"))
    return (f"算法: {algo}\n字节数: {len(text.encode('utf-8'))}\n"
            f"哈希: {h.hexdigest()}")


def url_codec(action: str, text: str) -> str:
    from urllib.parse import quote, unquote
    action = (action or "").lower()
    if action == "encode":
        return quote(text or "", safe="")
    if action == "decode":
        return unquote(text or "")
    return "ERROR: action 必须是 encode 或 decode"


def password_gen(length: int = 20, count: int = 1,
                 charset: str = "mixed", symbols: bool = True) -> str:
    try:
        n = max(4, min(int(length), 256))
        c = max(1, min(int(count), 50))
    except (TypeError, ValueError):
        return "ERROR: length/count 必须是整数"
    cs = (charset or "mixed").lower()
    if cs == "letters":
        pool = string.ascii_letters
    elif cs == "digits":
        pool = string.digits
    elif cs == "alnum":
        pool = string.ascii_letters + string.digits
    elif cs == "mixed":
        pool = string.ascii_letters + string.digits
    else:
        pool = cs
    if symbols and cs == "mixed":
        pool += "!@#$%^&*()-_=+[]{};:,.<>?"
    if not pool:
        return "ERROR: 字符集为空"
    lines = []
    for _ in range(c):
        pw = "".join(secrets.choice(pool) for _ in range(n))
        lines.append(pw)
    return f"生成 {c} 个密码（长度 {n}）：\n" + "\n".join(lines)


def jwt_decode(token: str) -> str:
    if not token or token.count(".") != 2:
        return "ERROR: 不是有效的 JWT（需要 3 段）"
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")

        def _decode(s):
            pad = "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s + pad).decode(
                "utf-8", errors="replace")

        header = json.loads(_decode(header_b64))
        payload = json.loads(_decode(payload_b64))
    except Exception as exc:
        return f"ERROR: 解码失败: {exc}"
    return "\n".join([
        "JWT 内容（未验证签名）：", "",
        "Header:",
        json.dumps(header, ensure_ascii=False, indent=2), "",
        "Payload:",
        json.dumps(payload, ensure_ascii=False, indent=2), "",
        f"Signature: {sig_b64[:32]}...",
    ])