"""共享 slowapi 限流器。

部署在 Cloudflare Tunnel 后面时，`request.client.host` 永远是 CF 的边缘节点 IP，
导致所有用户被算成同一个客户端。这里优先读 `CF-Connecting-IP`（CF 必带），
其次 `X-Forwarded-For`（任何反代标准），兜底才用 socket 远端。
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip(request: Request) -> str:
    # Cloudflare 必带这个 header，且 CF 会忽略客户端伪造的同名 header
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    # 通用反代标准；取第一个（最左）= 最原始客户端
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# 默认限流策略不写死；每个路由用 @limiter.limit("...") 单独声明。
limiter = Limiter(key_func=_client_ip)
