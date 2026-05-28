import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


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


@router.get("/config/runtime")
async def get_runtime_config() -> dict:
    return {
        "ok": True,
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
async def discover_llm_models(payload: ModelDiscoveryPayload) -> dict:
    base_url = _normalize_openai_base_url(payload.llm_base_url or settings.llm_base_url)
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
