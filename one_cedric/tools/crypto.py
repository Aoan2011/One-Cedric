"""加密解密：哈希 / 对称加密 / RSA / 随机数。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

from .sandbox import _resolve_path


def hash_data(data: str = "", file: str = "", algorithm: str = "sha256",
              hmac_key: str = "", root: Path | None = None) -> str:
    algo = (algorithm or "sha256").lower()
    if algo not in ("md5", "sha1", "sha256", "sha512", "blake2b", "blake2s"):
        return f"ERROR: 不支持的算法: {algo}"
    source = ""
    if file:
        if root is None:
            return "ERROR: file 需要 root"
        p, err = _resolve_path(root, file)
        if err:
            return err
        if not p.exists():
            return f"ERROR: 文件不存在: {file}"
        try:
            raw = p.read_bytes()
            source = f"file: {file} ({len(raw)} bytes)"
        except OSError as exc:
            return f"ERROR: {exc}"
    elif data:
        raw = data.encode("utf-8")
        source = f"text: {len(data)} chars"
    else:
        return "ERROR: 需要 data 或 file"
    if hmac_key:
        key = hmac_key.encode("utf-8")
        h = hmac.new(key, raw, algo).hexdigest()
        return f"{source}\n算法: HMAC-{algo}\n结果: {h}"
    h = hashlib.new(algo, raw).hexdigest()
    return f"{source}\n算法: {algo}\n结果: {h}"


def random_bytes(length: int = 32, fmt: str = "hex") -> str:
    try:
        n = max(1, min(int(length), 4096))
    except (TypeError, ValueError):
        n = 32
    fmt = (fmt or "hex").lower()
    data = secrets.token_bytes(n)
    if fmt == "hex":
        return data.hex()
    if fmt == "base64":
        return base64.b64encode(data).decode()
    if fmt == "url":
        return base64.urlsafe_b64encode(data).decode().rstrip("=")
    if fmt == "uuid":
        import uuid
        return str(uuid.UUID(bytes=data[:16]))
    return f"ERROR: 不支持的格式: {fmt}"


def _crypto():
    try:
        from cryptography.fernet import Fernet  # noqa
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        return {"ok": True, "AESGCM": AESGCM, "hashes": hashes,
                "serialization": serialization, "rsa": rsa,
                "padding": padding, "PBKDF2HMAC": PBKDF2HMAC}
    except ImportError:
        return {"ok": False,
                "err": "需要 cryptography（pip install cryptography）"}


def symmetric_encrypt(plaintext: str = "", file: str = "",
                      key: str = "", password: str = "",
                      out: str = "", root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    c = _crypto()
    if not c["ok"]:
        return "", False, f"ERROR: {c['err']}"
    source = ""
    if file:
        p, err = _resolve_path(root, file)
        if err:
            return "", False, err
        if not p.exists():
            return "", False, f"ERROR: 文件不存在: {file}"
        try:
            raw = p.read_bytes()
            source = f"file: {file}"
        except OSError as exc:
            return "", False, f"ERROR: {exc}"
        if not out:
            out = f"{p.name}.enc"
    elif plaintext:
        raw = plaintext.encode("utf-8")
        source = f"text: {len(plaintext)} chars"
        if not out:
            out = "encrypted.bin"
    else:
        return "", False, "ERROR: 需要 plaintext 或 file"
    out_p, err = _resolve_path(root, out)
    if err:
        return "", False, err
    return (f"加密源: {source}\n输出: {out_p.relative_to(root)}\n"
            f"算法: AES-256-GCM\n"
            f"密钥来源: "
            f"{'password（PBKDF2）' if password else 'key' if key else '随机'}\n"
            f"原始大小: {len(raw)} bytes"), True, ""


def symmetric_encrypt_apply(plaintext: str, file: str, key: str,
                            password: str, out: str, root: Path) -> str:
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if file:
        p, _ = _resolve_path(root, file)
        raw = p.read_bytes()
    else:
        raw = plaintext.encode("utf-8")
    key_b64 = ""
    if password:
        salt = os.urandom(16)
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=200_000)
        key_bytes = kdf.derive(password.encode("utf-8"))
        prefix = b"SALT" + salt
    elif key:
        try:
            kb = base64.b64decode(key)
            if len(kb) != 32:
                raise ValueError
        except Exception:
            import hashlib as _h
            kb = _h.sha256(key.encode("utf-8")).digest()
        key_bytes = kb
        prefix = b"KEY0"
    else:
        key_bytes = os.urandom(32)
        prefix = b"KEY0"
        key_b64 = base64.b64encode(key_bytes).decode()
    nonce = os.urandom(12)
    aes = AESGCM(key_bytes)
    ct = aes.encrypt(nonce, raw, None)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    payload = prefix + nonce + ct
    out_p.write_bytes(payload)
    extra = ""
    if not password and not key:
        extra = f"\n⚠ 随机生成的密钥（请保存）：\n{key_b64}"
    return (f"已加密 → {out_p.relative_to(root)}\n"
            f"原始 {len(raw)} → 密文 {len(payload)} bytes{extra}")


def symmetric_decrypt(file: str, key: str = "", password: str = "",
                      out: str = "", root: Path | None = None):
    if root is None:
        return "", False, "ERROR: 需要 root"
    c = _crypto()
    if not c["ok"]:
        return "", False, f"ERROR: {c['err']}"
    if not file:
        return "", False, "ERROR: 需要 file"
    p, err = _resolve_path(root, file)
    if err:
        return "", False, err
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {file}"
    if not out:
        out = p.stem if p.suffix == ".enc" else f"{p.name}.dec"
    return (f"解密源: {file}\n输出: {out}\n"
            f"密钥来源: {'password' if password else 'key'}\n"
            f"文件大小: {p.stat().st_size} bytes"), True, ""


def symmetric_decrypt_apply(file: str, key: str, password: str,
                            out: str, root: Path) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    p, _ = _resolve_path(root, file)
    payload = p.read_bytes()
    if len(payload) < 4 + 12 + 16:
        return "ERROR: 文件太短或不是本工具生成的密文"
    prefix = payload[:4]
    if prefix == b"SALT":
        salt = payload[4:20]
        nonce = payload[20:32]
        ct = payload[32:]
        if not password:
            return "ERROR: 该密文用 password 加密，需要提供 password"
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=200_000)
        key_bytes = kdf.derive(password.encode("utf-8"))
    elif prefix == b"KEY0":
        nonce = payload[4:16]
        ct = payload[16:]
        if not key:
            return "ERROR: 需要 key"
        try:
            kb = base64.b64decode(key)
            if len(kb) != 32:
                raise ValueError
        except Exception:
            import hashlib as _h
            kb = _h.sha256(key.encode("utf-8")).digest()
        key_bytes = kb
    else:
        return "ERROR: 未识别的密文格式"
    try:
        aes = AESGCM(key_bytes)
        raw = aes.decrypt(nonce, ct, None)
    except Exception as exc:
        return f"ERROR: 解密失败（密钥错误？）: {exc}"
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(raw)
    return f"已解密 → {out_p.relative_to(root)}（{len(raw)} bytes）"


def rsa_generate_keypair(bits: int = 2048, out_dir: str = ".",
                         name: str = "rsa_key",
                         password: str = "",
                         root: Path | None = None) -> tuple:
    if root is None:
        return "", False, "ERROR: 需要 root"
    c = _crypto()
    if not c["ok"]:
        return "", False, f"ERROR: {c['err']}"
    try:
        n = int(bits)
    except (TypeError, ValueError):
        n = 2048
    if n not in (2048, 3072, 4096):
        return "", False, "ERROR: bits 必须是 2048 / 3072 / 4096"
    pub_path = f"{out_dir}/{name}.pub.pem"
    priv_path = f"{out_dir}/{name}.priv.pem"
    p1, e1 = _resolve_path(root, pub_path)
    if e1:
        return "", False, e1
    return (f"将生成 RSA-{n} 密钥对：\n"
            f"  私钥: {priv_path}\n公钥: {pub_path}\n"
            f"私钥保护: {'password' if password else '无密码（不推荐）'}"), True, ""


def rsa_generate_keypair_apply(bits, out_dir, name, password, root) -> str:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import os
    key = rsa.generate_private_key(public_exponent=65537,
                                    key_size=int(bits))
    if password:
        enc = serialization.BestAvailableEncryption(
            password.encode("utf-8"))
    else:
        enc = serialization.NoEncryption()
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=enc)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    priv_path = f"{out_dir}/{name}.priv.pem"
    pub_path = f"{out_dir}/{name}.pub.pem"
    p1, _ = _resolve_path(root, priv_path)
    p2, _ = _resolve_path(root, pub_path)
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_bytes(priv_pem)
    p2.write_bytes(pub_pem)
    try:
        if os.name != "nt":
            os.chmod(p1, 0o600)
    except Exception:
        pass
    return (f"已生成密钥对（RSA-{bits}）：\n"
            f"  私钥: {priv_path}\n  公钥: {pub_path}")


def rsa_encrypt(plaintext: str = "", file: str = "",
                pubkey: str = "", out: str = "",
                root: Path | None = None) -> tuple:
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not pubkey:
        return "", False, "ERROR: 需要 pubkey（公钥文件路径）"
    p, err = _resolve_path(root, pubkey)
    if err:
        return "", False, err
    if not p.exists():
        return "", False, f"ERROR: 公钥文件不存在: {pubkey}"
    if not out:
        out = "encrypted.bin"
    return (f"将用公钥 {pubkey} 加密\n输出: {out}\n"
            f"算法: RSA-OAEP-SHA256"), True, ""


def rsa_encrypt_apply(plaintext, file, pubkey, out, root) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub_p, _ = _resolve_path(root, pubkey)
    pub = serialization.load_pem_public_key(pub_p.read_bytes())
    if file:
        p, _ = _resolve_path(root, file)
        raw = p.read_bytes()
    else:
        raw = plaintext.encode("utf-8")
    max_len = pub.key_size // 8 - 2 * 32 - 2
    if len(raw) > max_len:
        return (f"ERROR: 明文 {len(raw)} bytes 超过 RSA "
                f"单次上限 {max_len} bytes。\n"
                f"大文件请先用 symmetric_encrypt 加对称密钥。")
    ct = pub.encrypt(raw, padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(ct)
    return f"已加密 → {out_p.relative_to(root)}（{len(raw)} → {len(ct)} bytes）"


def rsa_decrypt(file: str = "", privkey: str = "",
                password: str = "", out: str = "",
                root: Path | None = None) -> tuple:
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not file or not privkey:
        return "", False, "ERROR: 需要 file 和 privkey"
    if not out:
        out = "decrypted.bin"
    return f"将用私钥 {privkey} 解密 {file}\n输出: {out}", True, ""


def rsa_decrypt_apply(file, privkey, password, out, root) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    priv_p, _ = _resolve_path(root, privkey)
    try:
        key = serialization.load_pem_private_key(
            priv_p.read_bytes(),
            password=password.encode("utf-8") if password else None)
    except Exception as exc:
        return f"ERROR: 加载私钥失败（密码错误？）: {exc}"
    f_p, _ = _resolve_path(root, file)
    ct = f_p.read_bytes()
    try:
        raw = key.decrypt(ct, padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(), label=None))
    except Exception as exc:
        return f"ERROR: 解密失败: {exc}"
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(raw)
    return f"已解密 → {out_p.relative_to(root)}（{len(raw)} bytes）"