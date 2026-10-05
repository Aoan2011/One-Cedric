# -*- coding: utf-8 -*-
"""mock 网关：验证 /settings /stats /static 新路由"""
import sys, threading, time, json, os
sys.path.insert(0, r"F:\one-cedric5")

from one_cedric.gateway.server import get_gateway, reset_gateway

class MockCopilot:
    """极简 mock copilot，仅提供 gateway 需要的方法"""
    model = "deepseek-flash"
    root = r"F:\one-cedric5"
    host = "http://localhost:11434"
    api_key = ""
    def status(self):
        return {"model": self.model, "root": self.root, "token_set": False}
    def list_tools(self):
        return [{"name": "read", "enabled": True, "description": "读取文件"},
                {"name": "grep", "enabled": True, "description": "搜索内容"},
                {"name": "search", "enabled": False, "description": "网页搜索"}]
    def recent_logs(self, n=20):
        return []
    def cost(self):
        return {"total": 0.0}

reset_gateway()
gw = get_gateway(copilot=MockCopilot())
gw.start(port=2051)
time.sleep(1.2)

import urllib.request

def get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:2051" + path, timeout=5) as r:
            body = r.read().decode("utf-8")
            return r.status, body, dict(r.headers)
    except Exception as e:
        return 0, str(e), {}

for path in ["/", "/settings", "/stats", "/static/app.js?v=20261005e",
             "/static/settings.html", "/static/stats.html"]:
    st, body, hdrs = get(path)
    ctype = hdrs.get("Content-Type", "")
    print(f"{path} -> {st} [{ctype}] len={len(body)}")

st, body, _ = get("/api/status")
print("/api/status ->", st, body[:120])
st, body, _ = get("/api/tools")
print("/api/tools ->", st, body[:120])

gw.stop()
print("OK")
