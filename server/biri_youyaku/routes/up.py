import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from biri_youyaku.auth import require_token
from biri_youyaku.jobs import repo
from biri_youyaku.modules.bilibili import space
from biri_youyaku.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/up", dependencies=[Depends(require_token)])


@router.get("/resolve")
@limiter.limit("30/minute")
async def resolve_up(request: Request, input: str = Query(..., min_length=1)) -> dict:
    try:
        mid = await space.resolve_mid(input)
    except space.SpaceFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "mid": mid}


@router.get("/{mid}/videos")
@limiter.limit("30/minute")
async def up_videos(
    request: Request,
    mid: int,
    page: int = Query(default=1, ge=1),
    keyword: str = Query(default=""),
    order: str = Query(default="pubdate"),
) -> dict:
    try:
        result = await space.fetch_up_videos(mid, page=page, keyword=keyword, order=order)
    except space.SpaceRateLimited as exc:
        # 风控 / 频控。用 503 让前端能拿到 detail（429 通道是通用文案），
        # 并提示配置 SESSDATA 提升成功率。
        raise HTTPException(
            status_code=503,
            detail=f"B 站风控拦截（{exc}）。稍后重试；在 server/.env 配置 BILI_SESSDATA 可显著提升成功率。",
        ) from exc
    except space.SpaceFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status_by_bvid = repo.summary_status_for_bvids([v.bvid for v in result.videos])
    videos = []
    for video in result.videos:
        match = status_by_bvid.get(video.bvid)
        videos.append(
            {
                "bvid": video.bvid,
                "title": video.title,
                "cover": video.cover,
                "pubdate": video.pubdate,
                "duration": video.duration,
                "url": f"https://www.bilibili.com/video/{video.bvid}",
                "status": match["status"] if match else None,
                "job_id": match["job_id"] if match else None,
            }
        )
    return {
        "ok": True,
        "mid": result.mid,
        "author": result.author,
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "has_more": result.has_more,
        "videos": videos,
    }
