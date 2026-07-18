from fastapi import APIRouter, Depends

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules.llm.balance import fetch_balance

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
# Routes that are intentionally not protected by API_TOKEN — they only expose
# booleans about whether something is configured, no secret values.
public_router = APIRouter(prefix="/v1")


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


@router.get("/llm/balance")
async def get_llm_balance(refresh: bool = False) -> dict:
    balance = await fetch_balance(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        force_refresh=refresh,
    )
    if balance is None:
        return {"ok": True, "supported": False}
    return {
        "ok": True,
        "supported": True,
        "provider": balance.provider,
        "balance": balance.balance,
        "currency": balance.currency,
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
