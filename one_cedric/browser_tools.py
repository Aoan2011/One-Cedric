"""浏览器模拟操作工具（playwright + 系统 Edge/Chrome）。

提供 browser_* 系列工具：打开网页、点击、输入、提取文本、截图、
前进后退、关闭等。浏览器实例模块级单例，全程可复用；
优先用系统 Edge（channel="msedge"，Windows 11 自带，零下载），
不可用时回退 chromium。
"""
from __future__ import annotations

import time
from pathlib import Path

_PW = None
_BROWSER = None
_CONTEXT = None
_LAUNCH_ERR = ""


def _launch(headless: bool = True) -> str:
    """启动浏览器（惰性）。返回错误信息，空串表示成功。"""
    global _PW, _BROWSER, _CONTEXT, _LAUNCH_ERR
    if _BROWSER is not None:
        return ""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _LAUNCH_ERR = f"未安装 playwright: {exc}"
        return _LAUNCH_ERR
    try:
        _PW = sync_playwright().start()
        for channel in ("msedge", "chrome", None):
            try:
                _BROWSER = _PW.chromium.launch(
                    channel=channel, headless=headless)
                break
            except Exception:
                continue
        if _BROWSER is None:
            _LAUNCH_ERR = "找不到可用的浏览器（已尝试 Edge/Chrome/Chromium）"
            return _LAUNCH_ERR
        _CONTEXT = _BROWSER.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
            ),
        )
    except Exception as exc:
        _LAUNCH_ERR = f"浏览器启动失败: {exc}"
        return _LAUNCH_ERR
    return ""


def _page():
    _launch()
    if _BROWSER is None:
        raise RuntimeError(_LAUNCH_ERR or "浏览器未就绪")
    if _CONTEXT.pages:
        return _CONTEXT.pages[-1]
    return _CONTEXT.new_page()


def _safe_text(page, limit: int) -> str:
    try:
        text = page.inner_text("body")
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:limit]


def browser_open(root, args: dict) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return "ERROR: 需要 url"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    timeout = int(args.get("timeout") or 30000)
    page = _page()
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    except Exception as exc:
        return f"ERROR: 打开失败: {exc}"
    time.sleep(0.3)
    title = ""
    try:
        title = page.title()
    except Exception:
        pass
    return (f"已打开: {page.url}\n标题: {title}\n"
            f"页面文本: {_safe_text(page, int(args.get('limit') or 800))}")


def browser_click(root, args: dict) -> str:
    sel = str(args.get("selector") or "").strip()
    if not sel:
        return "ERROR: 需要 selector（CSS 选择器）"
    page = _page()
    try:
        if int(args.get("index") or 0) > 0:
            page.locator(sel).nth(int(args["index"])).click(
                timeout=15000)
        else:
            page.locator(sel).first.click(timeout=15000)
    except Exception as exc:
        return f"ERROR: 点击失败: {exc}"
    time.sleep(0.3)
    return f"已点击 {sel}。当前 URL: {page.url}"


def browser_type(root, args: dict) -> str:
    sel = str(args.get("selector") or "").strip()
    text = str(args.get("text") or "")
    if not sel:
        return "ERROR: 需要 selector"
    page = _page()
    try:
        el = page.locator(sel).first
        el.click(timeout=15000)
        if args.get("clear") is not False:
            el.fill("")
        if text:
            el.type(text, delay=int(args.get("delay") or 10))
        if args.get("submit"):
            el.press("Enter")
    except Exception as exc:
        return f"ERROR: 输入失败: {exc}"
    return f"已输入到 {sel}（{len(text)} 字符）"


def browser_extract(root, args: dict) -> str:
    page = _page()
    sel = str(args.get("selector") or "").strip()
    limit = int(args.get("limit") or 4000)
    if sel:
        try:
            els = page.locator(sel)
            n = els.count()
            if n == 0:
                return "ERROR: 未找到匹配元素"
            parts = []
            for i in range(min(n, int(args.get("max_elements") or 10))):
                try:
                    parts.append(els.nth(i).inner_text())
                except Exception:
                    pass
            return "\n\n---\n\n".join(parts)[:limit]
        except Exception as exc:
            return f"ERROR: 提取失败: {exc}"
    return _safe_text(page, limit)


def browser_screenshot(root, args: dict) -> str:
    page = _page()
    save_to = str(args.get("save_to") or "").strip()
    if not save_to:
        return "ERROR: 需要 save_to（截图保存路径）"
    path = Path(save_to).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=bool(args.get("full_page")))
    except Exception as exc:
        return f"ERROR: 截图失败: {exc}"
    return f"已截图: {path}"


def browser_url(root, args: dict) -> str:
    page = _page()
    try:
        return f"URL: {page.url}\n标题: {page.title()}"
    except Exception as exc:
        return f"ERROR: {exc}"


def browser_nav(root, args: dict) -> str:
    action = str(args.get("action") or "back")
    page = _page()
    try:
        if action == "back":
            page.go_back()
        elif action == "forward":
            page.go_forward()
        elif action == "reload":
            page.reload()
        else:
            return f"ERROR: 未知 action: {action}"
    except Exception as exc:
        return f"ERROR: {exc}"
    time.sleep(0.3)
    return f"{action} 完成。当前 URL: {page.url}"


def browser_wait(root, args: dict) -> str:
    ms = max(0, int(args.get("ms") or 1000))
    time.sleep(ms / 1000)
    return f"已等待 {ms} ms"


def browser_close(root, args: dict) -> str:
    global _BROWSER, _CONTEXT, _PW
    if _BROWSER is not None:
        try:
            _BROWSER.close()
        except Exception:
            pass
    if _PW is not None:
        try:
            _PW.stop()
        except Exception:
            pass
    _BROWSER, _CONTEXT, _PW = None, None, None
    return "浏览器已关闭"


BROWSER_HANDLERS = {
    "browser_open": browser_open,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_extract": browser_extract,
    "browser_screenshot": browser_screenshot,
    "browser_url": browser_url,
    "browser_nav": browser_nav,
    "browser_wait": browser_wait,
    "browser_close": browser_close,
}
