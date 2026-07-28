from fastapi import APIRouter, Depends

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.modules.llm.balance import fetch_balance
from biri_youyaku.modules.llm.usage import cost_summary

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


@router.get("/stats/costs")
async def get_costs(refresh_balance: bool = False) -> dict:
    balance = await fetch_balance(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        force_refresh=refresh_balance,
        openrouter_management_api_key=settings.openrouter_management_api_key,
    )
    return {
        "ok": True,
        "current_balance": None if balance is None else balance.__dict__,
        **cost_summary(),
    }
