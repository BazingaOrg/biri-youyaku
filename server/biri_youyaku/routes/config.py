import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.jobs.model import JobOptions

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
# Routes that are intentionally not protected by API_TOKEN — they only expose
# booleans about whether something is configured, no secret values.
public_router = APIRouter(prefix="/v1")


def _validate_llm_base_url(base_url: str) -> None:
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


@router.get("/config/defaults")
async def get_config_defaults() -> dict:
    defaults = JobOptions.from_settings(settings).as_dict()
    return {
        "ok": True,
        "defaults": {
            **defaults,
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "llm_api_key_configured": bool(settings.llm_api_key),
            "asr_model": settings.asr_model,
            "asr_language": settings.asr_language_default,
            "audio_download_enabled": True,
        },
    }


@public_router.get("/config/runtime")
async def get_runtime_config() -> dict:
    # auth_mode 给前端用：api_token 模式前端需要带 Bearer；none 模式（仅本地）不需要。
    email_configured = bool(
        settings.email_enabled
        and (settings.email_webhook_url or "").strip()
        and (settings.email_webhook_token or "").strip()
        and (settings.email_default_recipient or "").strip()
    )
    return {
        "ok": True,
        "auth_mode": "api_token" if settings.api_token else "none",
        "llm_configured": bool(settings.llm_api_key),
        "email_configured": email_configured,
        "bilibili_cookie_configured": bool(settings.bili_sessdata),
    }
