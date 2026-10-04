"""HTTP Gateway 服务。

把 One Cedric 暴露为本地 HTTP API，其他程序（编辑器插件、脚本）可以调用。

默认仅监听 127.0.0.1，需要时通过 token 认证。
"""
from .server import Gateway, get_gateway, reset_gateway

__all__ = ["Gateway", "get_gateway", "reset_gateway"]