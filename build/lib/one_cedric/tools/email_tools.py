"""邮件工具：IMAP 收信 / POP3 收信 / SMTP 发信，支持附件。

凭证配置（三选一，优先级从高到低）：
  1. 环境变量（通过 password_env 指定变量名）
  2. ~/.one-cedric/email.toml
  3. 运行 /email-key <account> <password> 临时设置

email.toml 示例：
    default = "personal"

    [accounts.personal]
    email = "me@example.com"
    display_name = "Your Name"
    user = "me@example.com"
    password_env = "MY_EMAIL_PASSWORD"
    # 或 password = "xxxx"
    # 或 password_cmd = "pass show email/personal"

    imap_host = "imap.example.com"
    imap_port = 993
    imap_ssl = true

    smtp_host = "smtp.example.com"
    smtp_port = 465
    smtp_ssl = true

    pop3_host = "pop.example.com"
    pop3_port = 995
    pop3_ssl = true
"""
from __future__ import annotations

import base64
import email
import email.header
import email.message
import email.utils
import imaplib
import mimetypes
import os
import poplib
import re
import smtplib
import ssl
import subprocess
import time
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from .sandbox import _resolve_path


EMAIL_CONFIG_FILENAME = "email.toml"
IMAP_TIMEOUT = 30
SMTP_TIMEOUT = 30
POP3_TIMEOUT = 30
MAX_BODY_CHARS = 60_000
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


# ═══════════════════════════════════════════════════════════════════════ #
# 配置
# ═══════════════════════════════════════════════════════════════════════ #

_ACCOUNT_CACHE: dict | None = None
_RUNTIME_PASSWORDS: dict[str, str] = {}


def _email_config_path() -> Path:
    return Path.home() / ".one-cedric" / EMAIL_CONFIG_FILENAME


def _load_config_file() -> dict:
    p = _email_config_path()
    if not p.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_password(acc: dict, account_name: str) -> str:
    if account_name in _RUNTIME_PASSWORDS:
        return _RUNTIME_PASSWORDS[account_name]

    env_name = acc.get("password_env", "")
    if env_name:
        v = os.environ.get(env_name, "")
        if v:
            return v

    cmd = acc.get("password_cmd", "")
    if cmd:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip().splitlines()[0]
        except Exception:
            pass

    pwd = acc.get("password", "")
    if isinstance(pwd, str) and pwd:
        return pwd
    return ""


def load_accounts() -> dict:
    global _ACCOUNT_CACHE
    if _ACCOUNT_CACHE is not None:
        return _ACCOUNT_CACHE
    raw = _load_config_file()
    _ACCOUNT_CACHE = raw
    return raw


def reset_accounts_cache() -> None:
    global _ACCOUNT_CACHE
    _ACCOUNT_CACHE = None


def set_account_password(account: str, password: str) -> None:
    _RUNTIME_PASSWORDS[account] = password


def get_account(name: str = "") -> tuple[dict, str, str]:
    """返回 (account_cfg, account_name, error)。"""
    cfg = load_accounts()
    accounts = cfg.get("accounts") or {}
    if not accounts:
        return {}, "", (
            "ERROR: 未配置邮箱。请创建 ~/.one-cedric/email.toml，"
            "格式参考 tools/email_tools.py 顶部注释。"
        )
    if not name:
        name = cfg.get("default", "") or next(iter(accounts))
    if name not in accounts:
        avail = ", ".join(accounts.keys())
        return {}, "", f"ERROR: 账号 '{name}' 不存在。可用: {avail}"
    acc = dict(accounts[name])
    pwd = _resolve_password(acc, name)
    if not pwd:
        return acc, name, (
            f"ERROR: 账号 '{name}' 未配置密码。"
            f"在 email.toml 里设置 password / password_env / password_cmd，"
            f"或运行 /email-key {name} <password>。"
        )
    acc["_password"] = pwd
    return acc, name, ""


def _mask(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 6:
        return "***"
    return s[:3] + "***" + s[-3:]


def email_config_status() -> str:
    cfg = load_accounts()
    accounts = cfg.get("accounts") or {}
    if not accounts:
        return ("未配置任何邮箱账号。\n"
                f"配置文件: {_email_config_path()}\n"
                "格式参考 tools/email_tools.py 顶部注释。")

    lines = [f"配置: {_email_config_path()}",
             f"默认账号: {cfg.get('default', '(未设置)')}", ""]
    for name, acc in accounts.items():
        lines.append(f"[{name}]")
        lines.append(f"  邮箱: {acc.get('email', '(未设置)')}")
        lines.append(f"  用户: {acc.get('user', acc.get('email', ''))}")
        lines.append(f"  IMAP: {acc.get('imap_host', '(未设置)')}:{acc.get('imap_port', 993)}"
                     f"  ssl={acc.get('imap_ssl', True)}")
        lines.append(f"  SMTP: {acc.get('smtp_host', '(未设置)')}:{acc.get('smtp_port', 465)}"
                     f"  ssl={acc.get('smtp_ssl', True)}")
        if acc.get("pop3_host"):
            lines.append(f"  POP3: {acc.get('pop3_host')}:{acc.get('pop3_port', 995)}"
                         f"  ssl={acc.get('pop3_ssl', True)}")
        has_pwd = bool(_resolve_password(acc, name))
        lines.append(f"  密码: {'已设置' if has_pwd else '未设置'}")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════ #
# 通用：解码 / 解析 / 连接
# ═══════════════════════════════════════════════════════════════════════ #

def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = email.header.decode_header(value)
    except Exception:
        return str(value)
    out = []
    for raw, charset in parts:
        if isinstance(raw, bytes):
            try:
                out.append(raw.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(raw.decode("utf-8", errors="replace"))
        else:
            out.append(str(raw))
    return "".join(out)


def _imap_utf7_decode(s: str) -> str:
    """IMAP 修改版 UTF-7 解码（用于文件夹名）。"""
    if not isinstance(s, str):
        return s
    res = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "&":
            j = s.find("-", i)
            if j == -1:
                res.append(c)
                i += 1
                continue
            if j == i + 1:
                res.append("&")
            else:
                b64 = s[i + 1:j].replace(",", "/")
                pad = (-len(b64)) % 4
                b64 += "=" * pad
                try:
                    res.append(base64.b64decode(b64).decode("utf-16-be"))
                except Exception:
                    res.append(s[i:j + 1])
            i = j + 1
        else:
            res.append(c)
            i += 1
    return "".join(res)


def _fmt_addr(value: str) -> str:
    if not value:
        return ""
    pairs = email.utils.getaddresses([value])
    out = []
    for name, addr in pairs:
        name = _decode_header(name) if name else ""
        if name:
            out.append(f"{name} <{addr}>")
        else:
            out.append(addr)
    return ", ".join(out)


def _msg_summary(msg: email.message.Message) -> dict:
    return {
        "from": _fmt_addr(msg.get("From", "")),
        "to": _fmt_addr(msg.get("To", "")),
        "subject": _decode_header(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
        "message_id": (msg.get("Message-ID") or "").strip("<>"),
    }


def _extract_body(msg: email.message.Message) -> tuple[str, str]:
    """返回 (plain_text, html)。"""
    plain, html = "", ""

    def _decode_part(part):
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, TypeError):
            return payload.decode("utf-8", errors="replace")

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and not plain:
                plain = _decode_part(part)
            elif ctype == "text/html" and not html:
                html = _decode_part(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            html = _decode_part(msg)
        else:
            plain = _decode_part(msg)

    return plain, html


def _html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|h[1-6]|li|tr|section)>", "\n", html,
                  flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    import html as _h
    html = _h.unescape(html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _list_attachments(msg: email.message.Message) -> list[dict]:
    out = []
    if not msg.is_multipart():
        return out
    for i, part in enumerate(msg.walk()):
        if part.get_content_maintype() == "multipart":
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        fname = part.get_filename()
        is_att = "attachment" in disp or (fname and "inline" not in disp)
        if not is_att:
            continue
        if not fname:
            ctype = part.get_content_type()
            ext = mimetypes.guess_extension(ctype) or ".bin"
            fname = f"attachment_{i}{ext}"
        fname = _decode_header(fname)
        payload = part.get_payload(decode=True)
        size = len(payload) if payload else 0
        out.append({
            "index": i,
            "filename": fname,
            "content_type": part.get_content_type(),
            "size": size,
            "part": part,
        })
    return out


def _safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r'[<>:"|?*]', "_", name)
    if not name or name in (".", ".."):
        name = "attachment"
    return name[:200]


def _connect_imap(acc: dict, name: str):
    host = acc.get("imap_host")
    if not host:
        return None, f"ERROR: 账号 '{name}' 未配置 imap_host"
    port = int(acc.get("imap_port", 993))
    use_ssl = bool(acc.get("imap_ssl", True))
    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            M = imaplib.IMAP4_SSL(host, port, timeout=IMAP_TIMEOUT,
                                  ssl_context=ctx)
        else:
            M = imaplib.IMAP4(host, port, timeout=IMAP_TIMEOUT)
    except (OSError, ssl.SSLError, imaplib.IMAP4.error) as exc:
        return None, f"ERROR: IMAP 连接 {host}:{port} 失败: {exc}"
    try:
        user = acc.get("user") or acc.get("email", "")
        M.login(user, acc["_password"])
    except imaplib.IMAP4.error as exc:
        try:
            M.logout()
        except Exception:
            pass
        return None, f"ERROR: IMAP 登录失败: {exc}"
    return M, ""


def _connect_pop3(acc: dict, name: str):
    host = acc.get("pop3_host")
    if not host:
        return None, f"ERROR: 账号 '{name}' 未配置 pop3_host"
    port = int(acc.get("pop3_port", 995))
    use_ssl = bool(acc.get("pop3_ssl", True))
    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            M = poplib.POP3_SSL(host, port, timeout=POP3_TIMEOUT, context=ctx)
        else:
            M = poplib.POP3(host, port, timeout=POP3_TIMEOUT)
    except (OSError, ssl.SSLError, poplib.error_proto) as exc:
        return None, f"ERROR: POP3 连接 {host}:{port} 失败: {exc}"
    try:
        user = acc.get("user") or acc.get("email", "")
        M.user(user)
        M.pass_(acc["_password"])
    except poplib.error_proto as exc:
        try:
            M.quit()
        except Exception:
            pass
        return None, f"ERROR: POP3 登录失败: {exc}"
    return M, ""


def _connect_smtp(acc: dict, name: str):
    host = acc.get("smtp_host")
    if not host:
        return None, f"ERROR: 账号 '{name}' 未配置 smtp_host"
    port = int(acc.get("smtp_port", 465))
    use_ssl = bool(acc.get("smtp_ssl", True))
    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            M = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=ctx)
        else:
            M = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
            M.ehlo()
            try:
                M.starttls(context=ssl.create_default_context())
                M.ehlo()
            except smtplib.SMTPException:
                pass
    except (OSError, ssl.SSLError, smtplib.SMTPException) as exc:
        return None, f"ERROR: SMTP 连接 {host}:{port} 失败: {exc}"
    try:
        user = acc.get("user") or acc.get("email", "")
        M.login(user, acc["_password"])
    except smtplib.SMTPException as exc:
        try:
            M.quit()
        except Exception:
            pass
        return None, f"ERROR: SMTP 登录失败: {exc}"
    return M, ""


# ═══════════════════════════════════════════════════════════════════════ #
# 只读操作
# ═══════════════════════════════════════════════════════════════════════ #

def email_accounts() -> str:
    return email_config_status()


def imap_list_folders(account: str = "") -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, data = M.list()
        if status != "OK":
            return f"ERROR: LIST 失败: {status}"
        lines = [f"账号: {name} <{acc.get('email', '')}>", f"文件夹（{len(data)}）：", ""]
        for raw in data:
            s = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            m = re.match(r'\((?P<flags>[^)]*)\)\s+"(?P<delim>[^"]*)"\s+(?P<name>.+)', s)
            if not m:
                continue
            flags = m.group("flags")
            raw_name = m.group("name").strip().strip('"')
            pretty = _imap_utf7_decode(raw_name)
            marks = []
            if "\\Noselect" in flags:
                marks.append("不可选")
            if "\\Sent" in flags:
                marks.append("已发送")
            if "\\Drafts" in flags:
                marks.append("草稿")
            if "\\Trash" in flags:
                marks.append("废件箱")
            if "\\Junk" in flags:
                marks.append("垃圾")
            suffix = f"  [{'/'.join(marks)}]" if marks else ""
            lines.append(f"  {pretty}{suffix}")
            if pretty != raw_name:
                lines.append(f"    （原始名: {raw_name}）")
        return "\n".join(lines)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_list_messages(account: str = "", folder: str = "INBOX",
                       count: int = 20, unread_only: bool = False,
                       since: str = "") -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    try:
        n = max(1, min(int(count), 100))
    except (TypeError, ValueError):
        n = 20

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder, readonly=True)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败（检查名称是否正确）"

        criteria = "UNSEEN" if unread_only else "ALL"
        if since:
            criteria = f'(SINCE "{since}")'
            if unread_only:
                criteria = f'(UNSEEN SINCE "{since}")'

        status, data = M.uid("SEARCH", None, criteria)
        if status != "OK":
            return f"ERROR: SEARCH 失败: {status}"
        uids = (data[0] or b"").split()
        if not uids:
            return f"文件夹 '{folder}' 无匹配邮件。"

        recent = uids[-n:][::-1]

        lines = [f"账号: {name} · 文件夹: {folder}",
                 f"匹配 {len(uids)} 封，显示最近 {len(recent)} 封：", ""]

        for uid in recent:
            status, msg_data = M.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)])"
            )
            if status != "OK" or not msg_data:
                continue
            raw = b""
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                continue
            s = _msg_summary(msg)
            date = s["date"][:31] if s["date"] else ""
            lines.append(f"UID {uid.decode() if isinstance(uid, bytes) else uid}")
            lines.append(f"  日期: {date}")
            lines.append(f"  发件: {s['from']}")
            lines.append(f"  主题: {s['subject']}")
            lines.append("")

        return "\n".join(lines)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_search(account: str = "", folder: str = "INBOX",
                from_: str = "", to: str = "", subject: str = "",
                body: str = "", since: str = "", before: str = "",
                unseen_only: bool = False, count: int = 30) -> str:
    acc, name, err = get_account(account)
    if err:
        return err

    parts: list[str] = []
    if from_:
        parts.append(f'FROM "{from_}"')
    if to:
        parts.append(f'TO "{to}"')
    if subject:
        parts.append(f'SUBJECT "{subject}"')
    if body:
        parts.append(f'BODY "{body}"')
    if since:
        parts.append(f'SINCE "{since}"')
    if before:
        parts.append(f'BEFORE "{before}"')
    if unseen_only:
        parts.append("UNSEEN")
    if not parts:
        return "ERROR: 至少需要一个搜索条件（from_/to/subject/body/since/before/unseen_only）"

    criteria = "(" + " ".join(parts) + ")"

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder, readonly=True)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败"

        status, data = M.uid("SEARCH", None, criteria)
        if status != "OK":
            return f"ERROR: SEARCH 失败: {status}"
        uids = (data[0] or b"").split()
        if not uids:
            return f"未找到匹配邮件。\n条件: {criteria}"

        try:
            n = max(1, min(int(count), 100))
        except (TypeError, ValueError):
            n = 30
        recent = uids[-n:][::-1]

        lines = [f"账号: {name} · 文件夹: {folder}",
                 f"条件: {criteria}",
                 f"匹配 {len(uids)} 封，显示最近 {len(recent)} 封：", ""]

        for uid in recent:
            status, msg_data = M.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date)])"
            )
            if status != "OK" or not msg_data:
                continue
            raw = b""
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                continue
            s = _msg_summary(msg)
            uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
            lines.append(f"UID {uid_s}  ·  {s['date'][:31]}")
            lines.append(f"  {s['from']}")
            lines.append(f"  {s['subject']}")
            lines.append("")
        return "\n".join(lines)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_read(account: str = "", folder: str = "INBOX",
              uid: str = "", mark_seen: bool = False,
              include_html: bool = False) -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    if not uid:
        return "ERROR: 需要 uid（先从 email_list_messages 拿）"

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder, readonly=not mark_seen)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败"

        fetch_spec = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
        status, data = M.uid("FETCH", str(uid), fetch_spec)
        if status != "OK" or not data:
            return f"ERROR: FETCH 失败: {status}"
        raw = b""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        if not raw:
            return f"ERROR: 邮件 UID {uid} 内容为空"

        try:
            msg = email.message_from_bytes(raw)
        except Exception as exc:
            return f"ERROR: 解析邮件失败: {exc}"

        s = _msg_summary(msg)
        plain, html = _extract_body(msg)
        atts = _list_attachments(msg)

        body = plain
        if not body and html:
            body = _html_to_text(html)

        truncated = False
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS]
            truncated = True

        lines = [
            f"账号: {name}  ·  UID: {uid}  ·  文件夹: {folder}",
            "",
            f"发件: {s['from']}",
            f"收件: {s['to']}",
            f"主题: {s['subject']}",
            f"日期: {s['date']}",
            f"Message-ID: {s['message_id']}",
        ]
        cc = _fmt_addr(msg.get("Cc", ""))
        if cc:
            lines.append(f"抄送: {cc}")
        reply_to = _fmt_addr(msg.get("Reply-To", ""))
        if reply_to:
            lines.append(f"回复到: {reply_to}")

        lines.append("")
        if atts:
            lines.append(f"附件（{len(atts)}）：")
            for a in atts:
                lines.append(f"  [{a['index']}] {a['filename']}  "
                             f"{a['content_type']}  {a['size']} bytes")
            lines.append("")

        lines.append("--- 正文 ---")
        lines.append(body or "(无正文)")
        if truncated:
            lines.append(f"\n... (正文截断，原始 {len(body)} 字符)")

        if include_html and html:
            lines.append("")
            lines.append("--- HTML 原文 ---")
            lines.append(html[:20_000])

        return "\n".join(lines)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_list_attachments(account: str = "", folder: str = "INBOX",
                          uid: str = "") -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    if not uid:
        return "ERROR: 需要 uid"

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        M.select(folder, readonly=True)
        status, data = M.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data:
            return f"ERROR: FETCH 失败"
        raw = b""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        msg = email.message_from_bytes(raw)
        atts = _list_attachments(msg)
        if not atts:
            return f"UID {uid} 无附件"

        lines = [f"UID {uid} 的附件（{len(atts)}）：", ""]
        for a in atts:
            lines.append(f"  index={a['index']}  {a['filename']}")
            lines.append(f"    {a['content_type']}  {a['size']} bytes")
        lines.append("")
        lines.append("使用 email_download_attachment 下载指定 index 的附件。")
        return "\n".join(lines)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_download_attachment(account: str = "", folder: str = "INBOX",
                             uid: str = "", index: int = -1,
                             save_to: str = "",
                             root: Path | None = None) -> tuple[bytes | None, str, str]:
    """返回 (data, filename, error)。数据由 core 层负责落盘确认。"""
    acc, name, err = get_account(account)
    if err:
        return None, "", err
    if not uid:
        return None, "", "ERROR: 需要 uid"
    if root is None:
        return None, "", "ERROR: 需要 root"

    M, err = _connect_imap(acc, name)
    if err:
        return None, "", err
    try:
        M.select(folder, readonly=True)
        status, data = M.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data:
            return None, "", "ERROR: FETCH 失败"
        raw = b""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        msg = email.message_from_bytes(raw)
        atts = _list_attachments(msg)
        if not atts:
            return None, "", f"ERROR: UID {uid} 无附件"

        target = None
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = -1

        if idx < 0:
            target = atts[0]
        else:
            for a in atts:
                if a["index"] == idx:
                    target = a
                    break
            if target is None:
                avail = ", ".join(str(a["index"]) for a in atts)
                return None, "", f"ERROR: 找不到 index={idx}。可用: {avail}"

        payload = target["part"].get_payload(decode=True)
        if not payload:
            return None, "", "ERROR: 附件内容为空"
        if len(payload) > MAX_ATTACHMENT_BYTES:
            return None, "", f"ERROR: 附件超过 {MAX_ATTACHMENT_BYTES // 1024 // 1024}MB 上限"

        fname = _safe_filename(save_to or target["filename"])
        return payload, fname, ""
    finally:
        try:
            M.logout()
        except Exception:
            pass


def pop3_list(account: str = "", count: int = 20) -> str:
    acc, name, err = get_account(account)
    if err:
        return err

    M, err = _connect_pop3(acc, name)
    if err:
        return err
    try:
        try:
            n_msgs, total_size = M.stat()
        except poplib.error_proto as exc:
            return f"ERROR: STAT 失败: {exc}"

        try:
            n = max(1, min(int(count), n_msgs, 100))
        except (TypeError, ValueError):
            n = min(20, n_msgs)

        lines = [f"账号: {name}",
                 f"共 {n_msgs} 封，总计 {total_size} bytes",
                 f"显示最近 {n} 封：", ""]

        start = max(1, n_msgs - n + 1)
        for i in range(n_msgs, start - 1, -1):
            try:
                resp, lines_raw, _ = M.top(i, 0)
            except poplib.error_proto:
                continue
            raw = b"\r\n".join(lines_raw)
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                continue
            s = _msg_summary(msg)
            lines.append(f"#{i}  ·  {s['date'][:31]}")
            lines.append(f"  {s['from']}")
            lines.append(f"  {s['subject']}")
            lines.append("")

        return "\n".join(lines)
    finally:
        try:
            M.quit()
        except Exception:
            pass


def pop3_read(account: str = "", index: int = 0,
              delete_after: bool = False) -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return "ERROR: index 必须是整数"

    M, err = _connect_pop3(acc, name)
    if err:
        return err
    try:
        try:
            n_msgs, _ = M.stat()
        except poplib.error_proto as exc:
            return f"ERROR: STAT 失败: {exc}"
        if idx < 1 or idx > n_msgs:
            return f"ERROR: index={idx} 超出范围（1-{n_msgs}）"

        try:
            resp, raw_lines, _ = M.retr(idx)
        except poplib.error_proto as exc:
            return f"ERROR: RETR 失败: {exc}"

        raw = b"\r\n".join(raw_lines)
        msg = email.message_from_bytes(raw)
        s = _msg_summary(msg)
        plain, html = _extract_body(msg)
        atts = _list_attachments(msg)

        body = plain or _html_to_text(html)
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "\n... (截断)"

        lines = [
            f"账号: {name}  ·  POP3 #{idx}/{n_msgs}",
            "",
            f"发件: {s['from']}",
            f"收件: {s['to']}",
            f"主题: {s['subject']}",
            f"日期: {s['date']}",
        ]
        if atts:
            lines.append("")
            lines.append(f"附件（{len(atts)}，仅元数据）：")
            for a in atts:
                lines.append(f"  {a['filename']}  {a['content_type']}  {a['size']} bytes")
        lines.append("")
        lines.append("--- 正文 ---")
        lines.append(body or "(无正文)")
        lines.append("")
        lines.append("（POP3 不支持下载附件，请改用 IMAP 账号）")

        if delete_after:
            try:
                M.dele(idx)
                lines.append("")
                lines.append(f"⚠ 已标记 #{idx} 为删除（QUIT 后生效）")
            except poplib.error_proto as exc:
                lines.append(f"\nERROR: DELE 失败: {exc}")

        return "\n".join(lines)
    finally:
        try:
            M.quit()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════ #
# 写操作：发信 / 移动 / 标记 / 删除（需 core 层确认）
# ═══════════════════════════════════════════════════════════════════════ #

def _build_message(acc: dict, to: str, subject: str, body: str,
                   cc: str = "", bcc: str = "", html: bool = False,
                   attachments: list[tuple[str, bytes, str]] | None = None,
                   in_reply_to: str = "", references: str = ""
                   ) -> email.message.Message:
    from_addr = acc.get("email") or acc.get("user", "")
    display = acc.get("display_name", "")
    if display:
        msg = MIMEMultipart()
        msg["From"] = email.utils.formataddr((display, from_addr))
    else:
        msg = MIMEMultipart()
        msg["From"] = from_addr

    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=from_addr.split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to

    if html:
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    for fname, data, ctype in (attachments or []):
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(data)
        import email.encoders
        email.encoders.encode_base64(part)
        safe = _safe_filename(fname)
        try:
            fname_ascii = safe.encode("ascii").decode("ascii")
            part.add_header("Content-Disposition", "attachment",
                            filename=fname_ascii)
        except UnicodeEncodeError:
            part.add_header("Content-Disposition", "attachment",
                            filename=("utf-8", "", safe))
        msg.attach(part)

    return msg


def email_send_preview(account: str, to: str, subject: str, body: str,
                       cc: str = "", bcc: str = "",
                       attachments: list[str] | None = None,
                       root: Path | None = None
                       ) -> tuple[str, bool, str, dict]:
    """返回 (preview_text, is_write, error, payload)。

    payload 只做预检，不在 preview 阶段真发信。
    """
    acc, name, err = get_account(account)
    if err:
        return "", False, err, {}
    if not to:
        return "", False, "ERROR: 需要 to", {}
    if not subject:
        subject = "(无主题)"

    att_data: list[tuple[str, bytes, str]] = []
    att_names: list[str] = []
    if attachments and root is not None:
        for rel in attachments:
            p, perr = _resolve_path(root, rel)
            if perr:
                return "", False, perr, {}
            if not p.exists() or not p.is_file():
                return "", False, f"ERROR: 附件不存在: {rel}", {}
            try:
                data = p.read_bytes()
            except OSError as exc:
                return "", False, f"ERROR: 读取附件失败 {rel}: {exc}", {}
            if len(data) > MAX_ATTACHMENT_BYTES:
                return "", False, (
                    f"ERROR: 附件 {rel} 超过 {MAX_ATTACHMENT_BYTES // 1024 // 1024}MB"
                ), {}
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            att_data.append((p.name, data, ctype))
            att_names.append(f"{p.name} ({ctype}, {len(data)} bytes)")

    preview_lines = [
        f"账号: {name} <{acc.get('email', '')}>",
        f"收件人: {to}",
    ]
    if cc:
        preview_lines.append(f"抄送: {cc}")
    if bcc:
        preview_lines.append(f"密送: {bcc}")
    preview_lines.append(f"主题: {subject}")
    if att_names:
        preview_lines.append(f"附件（{len(att_names)}）：")
        for a in att_names:
            preview_lines.append(f"  · {a}")

    body_preview = body[:500] + ("\n..." if len(body) > 500 else "")
    preview_lines.append("")
    preview_lines.append("--- 正文 ---")
    preview_lines.append(body_preview)

    return "\n".join(preview_lines), True, "", {
        "account_name": name,
        "account": acc,
        "to": to, "cc": cc, "bcc": bcc, "subject": subject, "body": body,
        "attachments": att_data,
    }


def email_send_apply(payload: dict, html: bool = False) -> str:
    acc = payload["account"]
    name = payload["account_name"]

    msg = _build_message(
        acc, payload["to"], payload["subject"], payload["body"],
        cc=payload.get("cc", ""), bcc=payload.get("bcc", ""),
        html=html, attachments=payload.get("attachments"),
    )

    M, err = _connect_smtp(acc, name)
    if err:
        return err
    try:
        recipients = [a.strip() for a in payload["to"].split(",") if a.strip()]
        if payload.get("cc"):
            recipients += [a.strip() for a in payload["cc"].split(",") if a.strip()]
        if payload.get("bcc"):
            recipients += [a.strip() for a in payload["bcc"].split(",") if a.strip()]
        try:
            M.send_message(msg, from_addr=acc.get("email"), to_addrs=recipients)
        except smtplib.SMTPException as exc:
            return f"ERROR: 发送失败: {exc}"
        return f"已发送: {payload['subject']} → {payload['to']}"
    finally:
        try:
            M.quit()
        except Exception:
            pass


def email_reply_preview(account: str, folder: str, uid: str,
                        body: str, reply_all: bool = False,
                        attachments: list[str] | None = None,
                        root: Path | None = None
                        ) -> tuple[str, bool, str, dict]:
    acc, name, err = get_account(account)
    if err:
        return "", False, err, {}
    if not uid:
        return "", False, "ERROR: 需要 uid（原邮件的 UID）", {}

    M, err = _connect_imap(acc, name)
    if err:
        return "", False, err, {}
    try:
        M.select(folder, readonly=True)
        status, data = M.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data:
            return "", False, f"ERROR: FETCH 失败", {}
        raw = b""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        orig = email.message_from_bytes(raw)
    finally:
        try:
            M.logout()
        except Exception:
            pass

    orig_from = _fmt_addr(orig.get("From", ""))
    orig_subject = _decode_header(orig.get("Subject", ""))
    orig_msgid = (orig.get("Message-ID") or "").strip()
    orig_refs = orig.get("References", "") or ""
    orig_to = _fmt_addr(orig.get("To", ""))
    orig_cc = _fmt_addr(orig.get("Cc", ""))

    _, from_addr = email.utils.getaddresses([orig.get("From", "")])[0]
    if not from_addr:
        return "", False, "ERROR: 原邮件缺少 From", {}

    reply_to = [from_addr]
    if reply_all:
        my_email = acc.get("email", "").lower()
        for _, addr in email.utils.getaddresses([orig.get("To", ""), orig.get("Cc", "")]):
            if addr and addr.lower() != my_email and addr not in reply_to:
                reply_to.append(addr)

    subj = orig_subject
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj

    references = (orig_refs + " " + orig_msgid).strip() if orig_msgid else orig_refs

    att_data: list[tuple[str, bytes, str]] = []
    att_names: list[str] = []
    if attachments and root is not None:
        for rel in attachments:
            p, perr = _resolve_path(root, rel)
            if perr:
                return "", False, perr, {}
            if not p.exists():
                return "", False, f"ERROR: 附件不存在: {rel}", {}
            try:
                d = p.read_bytes()
            except OSError as exc:
                return "", False, f"ERROR: {exc}", {}
            if len(d) > MAX_ATTACHMENT_BYTES:
                return "", False, "ERROR: 附件过大", {}
            ct = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            att_data.append((p.name, d, ct))
            att_names.append(f"{p.name} ({ct})")

    quoted = ""
    plain, _ = _extract_body(orig)
    if plain:
        quoted = "\n".join("> " + ln for ln in plain.splitlines()[:50])
        if len(plain.splitlines()) > 50:
            quoted += "\n> ... (截断)"

    full_body = body
    if quoted:
        full_body += f"\n\n--- 原邮件 ---\n发件人: {orig_from}\n日期: {orig.get('Date', '')}\n主题: {orig_subject}\n\n{quoted}"

    preview_lines = [
        f"账号: {name} <{acc.get('email', '')}>",
        f"回复给: {', '.join(reply_to)}",
        f"主题: {subj}",
    ]
    if att_names:
        preview_lines.append(f"附件（{len(att_names)}）：")
        for a in att_names:
            preview_lines.append(f"  · {a}")
    preview_lines.append("")
    preview_lines.append("--- 正文 ---")
    preview_lines.append(body[:500] + ("\n..." if len(body) > 500 else ""))
    preview_lines.append("")
    preview_lines.append("--- 引用的原邮件 ---")
    preview_lines.append(f"发件人: {orig_from}")
    preview_lines.append(f"主题: {orig_subject}")
    preview_lines.append(f"引用 {len(plain.splitlines()) if plain else 0} 行")

    return "\n".join(preview_lines), True, "", {
        "account_name": name,
        "account": acc,
        "to": ", ".join(reply_to),
        "cc": "",
        "bcc": "",
        "subject": subj,
        "body": full_body,
        "attachments": att_data,
        "in_reply_to": orig_msgid,
        "references": references,
    }


def email_reply_apply(payload: dict) -> str:
    acc = payload["account"]
    name = payload["account_name"]

    msg = _build_message(
        acc, payload["to"], payload["subject"], payload["body"],
        attachments=payload.get("attachments"),
        in_reply_to=payload.get("in_reply_to", ""),
        references=payload.get("references", ""),
    )

    M, err = _connect_smtp(acc, name)
    if err:
        return err
    try:
        recipients = [a.strip() for a in payload["to"].split(",") if a.strip()]
        try:
            M.send_message(msg, from_addr=acc.get("email"), to_addrs=recipients)
        except smtplib.SMTPException as exc:
            return f"ERROR: 回复失败: {exc}"
        return f"已回复: {payload['subject']} → {payload['to']}"
    finally:
        try:
            M.quit()
        except Exception:
            pass


def imap_mark_preview(account: str, folder: str, uid: str,
                      action: str) -> tuple[str, bool, str]:
    """action: seen | unseen | flagged | unflagged | answered"""
    valid = {"seen", "unseen", "flagged", "unflagged", "answered"}
    a = (action or "").lower()
    if a not in valid:
        return "", False, f"ERROR: action 必须是 {', '.join(valid)}"

    acc, name, err = get_account(account)
    if err:
        return "", False, err
    if not uid:
        return "", False, "ERROR: 需要 uid"

    labels = {
        "seen": "已读", "unseen": "未读",
        "flagged": "加星", "unflagged": "取消星",
        "answered": "已回复标记",
    }
    return (f"账号: {name} · 文件夹: {folder} · UID: {uid}\n"
            f"操作: {labels[a]}"), True, ""


def imap_mark_apply(account: str, folder: str, uid: str, action: str) -> str:
    acc, name, err = get_account(account)
    if err:
        return err
    a = action.lower()

    flags_map = {
        "seen": ("+FLAGS", "(\\Seen)"),
        "unseen": ("-FLAGS", "(\\Seen)"),
        "flagged": ("+FLAGS", "(\\Flagged)"),
        "unflagged": ("-FLAGS", "(\\Flagged)"),
        "answered": ("+FLAGS", "(\\Answered)"),
    }
    op, flag = flags_map[a]

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败"
        try:
            status, resp = M.uid("STORE", str(uid), op, flag)
        except imaplib.IMAP4.error as exc:
            return f"ERROR: STORE 失败: {exc}"
        if status != "OK":
            return f"ERROR: STORE 失败: {status}"
        return f"已对 UID {uid} 执行 {a}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_move_preview(account: str, folder: str, uid: str,
                      dest: str) -> tuple[str, bool, str]:
    acc, name, err = get_account(account)
    if err:
        return "", False, err
    if not uid or not dest:
        return "", False, "ERROR: 需要 uid 和 dest"
    return (f"账号: {name}\n"
            f"将 UID {uid} 从 '{folder}' 移动到 '{dest}'"), True, ""


def imap_move_apply(account: str, folder: str, uid: str, dest: str) -> str:
    acc, name, err = get_account(account)
    if err:
        return err

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败"

        try:
            status, _ = M.uid("COPY", str(uid), dest)
        except imaplib.IMAP4.error as exc:
            return f"ERROR: COPY 失败: {exc}"
        if status != "OK":
            return f"ERROR: 目标文件夹 '{dest}' 可能不存在"

        try:
            M.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
            M.expunge()
        except imaplib.IMAP4.error as exc:
            return f"ERROR: 原邮件删除失败: {exc}"

        return f"已移动 UID {uid}: {folder} → {dest}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_delete_preview(account: str, folder: str,
                        uid: str) -> tuple[str, bool, str]:
    acc, name, err = get_account(account)
    if err:
        return "", False, err
    if not uid:
        return "", False, "ERROR: 需要 uid"
    return (f"账号: {name}\n"
            f"将删除 '{folder}' 中的 UID {uid}\n"
            f"⚠ 不可撤销"), True, ""


def imap_delete_apply(account: str, folder: str, uid: str) -> str:
    acc, name, err = get_account(account)
    if err:
        return err

    M, err = _connect_imap(acc, name)
    if err:
        return err
    try:
        status, _ = M.select(folder)
        if status != "OK":
            return f"ERROR: 打开文件夹 '{folder}' 失败"
        try:
            M.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
            M.expunge()
        except imaplib.IMAP4.error as exc:
            return f"ERROR: 删除失败: {exc}"
        return f"已删除 UID {uid}（{folder}）"
    finally:
        try:
            M.logout()
        except Exception:
            pass