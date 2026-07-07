import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from biri_youyaku.auth import require_token
from biri_youyaku.distill import orchestrator
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.distill.model import DistillRun, TERMINAL_DISTILL_RUN_STATUS_VALUES
from biri_youyaku.events import event_bus
from biri_youyaku.modules.storage import distill as distill_storage
from biri_youyaku.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class StartDistillPayload(BaseModel):
    video_limit: int = 50


def _serialize_run(run: DistillRun) -> dict:
    return {
        "id": run.id,
        "mid": run.mid,
        "up_name": run.up_name,
        "status": run.status.value,
        "video_limit": run.video_limit,
        "dynamics_status": run.dynamics_status,
        "counters": run.counters,
        "error": run.error,
        "dir_path": run.dir_path,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@router.post("/up/{mid}/distill")
@limiter.limit("5/minute")
async def start_distill(request: Request, mid: int, payload: StartDistillPayload) -> dict:
    try:
        run = await orchestrator.start_run(mid, video_limit=payload.video_limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "run": _serialize_run(run)}


@router.get("/distill/{run_id}")
async def get_distill(run_id: str) -> dict:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Distill run not found")
    return {"ok": True, "run": _serialize_run(run)}


@router.get("/distill/{run_id}/events")
async def stream_distill(run_id: str):
    if distill_repo.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Distill run not found")

    async def generator():
        async with event_bus.subscribe(run_id) as subscriber:
            run = distill_repo.get_run(run_id)
            if run is None:
                logger.info("stream_distill: run %s vanished after handler entry", run_id)
                return
            yield {"event": "status", "data": json.dumps(_serialize_run(run), ensure_ascii=False)}
            if run.status.value in TERMINAL_DISTILL_RUN_STATUS_VALUES:
                return

            while True:
                try:
                    message = await asyncio.wait_for(subscriber.pop(), timeout=25)
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                yield {
                    "event": message["event"],
                    "data": json.dumps(message["data"], ensure_ascii=False),
                }
                if (
                    message["event"] == "status"
                    and message["data"].get("status") in TERMINAL_DISTILL_RUN_STATUS_VALUES
                ):
                    return

    return EventSourceResponse(generator(), ping=25)


@router.post("/distill/{run_id}/cancel")
async def cancel_distill(run_id: str) -> dict:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Distill run not found")
    orchestrator.cancel_run(run_id)
    return {"ok": True}


@router.get("/distill/{run_id}/corpus")
async def get_distill_corpus(run_id: str) -> dict:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Distill run not found")
    corpus = distill_storage.read_corpus(run.mid)
    if corpus is None:
        raise HTTPException(status_code=404, detail="蒸馏语料尚未生成完成")
    return {"ok": True, "run_id": run_id, "corpus": corpus}


@router.get("/up/{mid}/distill/latest")
async def get_latest_distill(mid: int) -> dict:
    run = distill_repo.latest_by_mid(mid)
    if run is None:
        return {"ok": True, "run": None}
    return {"ok": True, "run": _serialize_run(run)}
