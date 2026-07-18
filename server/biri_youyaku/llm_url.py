import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

from biri_youyaku.config import settings


def validate_llm_base_url(base_url: str) -> None:
    """防 SSRF：检查 base_url 的 host 是否在白名单内，且不是内网/loopback/元数据 IP。

    白名单为空 = 允许任意（仅适合本地 dev）。生产环境务必在 .env 配 LLM_BASE_URL_ALLOWED_HOSTS。
    """
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="llm_base_url 必须是 http(s)://")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="llm_base_url 缺少 host")

    # 拒绝直接传 IP 探内网/云元数据（169.254.169.254 / 127.0.0.1 / 10.x / 192.168.x 等）
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise HTTPException(status_code=400, detail="llm_base_url 不允许指向内网或保留地址")

    allowed = settings.llm_allowed_hosts
    if not allowed:
        return  # 白名单空 = 不限制（本地 dev 模式）
    if not any(host == item or host.endswith("." + item) for item in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"llm_base_url 的 host '{host}' 不在白名单内。允许的 host：{', '.join(allowed)}",
        )
