import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.rate_limit import limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
# Routes that are intentionally not protected by API_TOKEN — they only expose
# booleans about whether something is configured, no secret values.
public_router = APIRouter(prefix="/v1")


class ModelDiscoveryPayload(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.lower().startswith("https://generativelanguage.googleapis.com"):
        return normalized
    if not normalized.lower().endswith("/v1") and "/v" not in normalized.rsplit("/", 1)[-1].lower():
        normalized = f"{normalized}/v1"
    return normalized


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
    auth_mode = "api_token" if settings.api_token else "none"
    return {
        "ok": True,
        "auth_mode": auth_mode,
        # 兼容旧字段：保留 1-2 个版本再删。
        "api_token_required": auth_mode == "api_token",
        "llm_configured": bool(settings.llm_api_key),
        "email_configured": bool(settings.email_enabled and settings.email_webhook_url),
        "bilibili_cookie_configured": bool(settings.bili_sessdata),
    }


@router.get("/usage")
async def get_usage(range: str = Query(default="7d")) -> dict:
    if not range.endswith("d"):
        raise HTTPException(status_code=400, detail="range must be like 7d")
    try:
        days = int(range[:-1])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="range must be like 7d") from exc
    if days <= 0 or days > 365:
        raise HTTPException(status_code=400, detail="range days must be between 1 and 365")
    since_ms = repo.now_ms() - days * 24 * 60 * 60 * 1000
    return {"ok": True, "range": range, "usage": repo.usage_since(since_ms)}


@router.post("/llm/models")
@limiter.limit("10/minute")
async def discover_llm_models(request: Request, payload: ModelDiscoveryPayload) -> dict:
    base_url = _normalize_openai_base_url(payload.llm_base_url or settings.llm_base_url)
    _validate_llm_base_url(base_url)
    api_key = (payload.llm_api_key or settings.llm_api_key).strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="LLM_API_KEY 未配置")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"模型列表请求失败：{exc}") from exc

    if response.is_error:
        try:
            body = response.json()
        except ValueError:
            body = {}
        detail = (
            body.get("error", {}).get("message")
            if isinstance(body.get("error"), dict)
            else body.get("message") or body.get("detail")
        )
        raise HTTPException(
            status_code=502,
            detail=detail or f"模型列表请求失败：HTTP {response.status_code}",
        )

    payload_json = response.json()
    model_set = {
        item.get("id", "").strip()
        for item in payload_json.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id", "").strip()
    }
    models = sorted(model_set)
    if not models:
        raise HTTPException(status_code=502, detail="模型列表为空")
    return {"ok": True, "models": models}
