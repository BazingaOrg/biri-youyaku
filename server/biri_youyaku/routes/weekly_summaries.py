from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from biri_youyaku.auth import require_token
from biri_youyaku.rate_limit import limiter
from biri_youyaku.weekly import orchestrator, repo

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class RefreshPayload(BaseModel):
    refresh: bool = False


def _serialize(week_start: str) -> dict:
    try:
        stored, sources, _ = repo.state_for_week(week_start)
        _, _, week_end = repo.week_bounds(week_start)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    timezone = str(repo._zone())
    if stored is None:
        return {
            "ok": True,
            "week_start": week_start,
            "week_end": week_end,
            "timezone": timezone,
            "status": "MISSING",
            "source_count": len(sources),
            "content": None,
            "references": [],
            "error": None,
            "generated_at": None,
        }
    return {
        "ok": True,
        "week_start": stored.week_start,
        "week_end": stored.week_end,
        "timezone": stored.timezone,
        "status": stored.status,
        "source_count": len(sources),
        "content": stored.content if stored.status == "COMPLETED" else None,
        "references": stored.references if stored.status == "COMPLETED" else [],
        "error": stored.error if stored.status == "FAILED" else None,
        "generated_at": stored.generated_at,
    }


@router.get("/weekly-summaries")
async def get_weekly_summary(week_start: str = Query()) -> dict:
    return _serialize(week_start)


@router.post("/weekly-summaries/{week_start}/generate")
@limiter.limit("10/minute")
async def generate_weekly_summary(
    request: Request, week_start: str, payload: RefreshPayload
) -> dict:
    try:
        orchestrator.request_generation(week_start, refresh=payload.refresh)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _serialize(week_start)
