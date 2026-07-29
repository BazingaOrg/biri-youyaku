"""Knowledge search + opt-in chat routes (Phase B/C)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.knowledge import index as knowledge_index
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.chat import stream_chat
from biri_youyaku.knowledge.retrieve import evidence_hit_to_dict, retrieve

logger = logging.getLogger("biri_youyaku.routes.knowledge")

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class ChatBody(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=6, ge=1, le=20)


def _search_enabled() -> bool:
    return bool(settings.knowledge_search_enabled and settings.knowledge_register_enabled)


@router.get("/knowledge/search")
async def knowledge_search(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    if not _search_enabled():
        raise HTTPException(
            status_code=403,
            detail="知识检索未启用（KNOWLEDGE_SEARCH_ENABLED 或 KNOWLEDGE_REGISTER_ENABLED）",
        )
    hits = retrieve(q, mode="search", limit=limit)
    return {
        "ok": True,
        "query": q,
        "hits": [evidence_hit_to_dict(h) for h in hits],
    }


@router.post("/knowledge/chat")
async def knowledge_chat(body: ChatBody) -> EventSourceResponse:
    if not settings.knowledge_chat_enabled:
        raise HTTPException(
            status_code=403,
            detail="知识问答未启用（KNOWLEDGE_CHAT_ENABLED=false）",
        )
    if not _search_enabled():
        raise HTTPException(
            status_code=403,
            detail="知识检索未启用，无法进行基于总结的问答",
        )

    async def generator():
        try:
            async for event in stream_chat(body.query, limit=body.limit):
                yield event
        except Exception:
            logger.exception("knowledge chat stream failed")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": "知识问答流异常"},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(generator(), ping=25)


@router.get("/knowledge/status")
async def knowledge_status() -> dict[str, Any]:
    return {
        "ok": True,
        "documents": knowledge_repo.count_documents(),
        "chunks": knowledge_index.count_chunks(),
        "summary_chunks": knowledge_index.count_summary_chunks(),
        "transcript_chunks": knowledge_index.count_transcript_chunks(),
        "chat_enabled": bool(settings.knowledge_chat_enabled),
        "search_enabled": _search_enabled(),
        "register_enabled": bool(settings.knowledge_register_enabled),
        "transcript_index_enabled": bool(settings.knowledge_transcript_index_enabled),
    }


@router.post("/knowledge/reindex")
async def knowledge_reindex() -> dict[str, Any]:
    """Ops: full rebuild of summary + transcript FTS from artifacts."""
    if not settings.knowledge_register_enabled:
        raise HTTPException(status_code=403, detail="知识登记未启用")
    try:
        revisions = knowledge_index.rebuild_all()
    except Exception as exc:
        logger.exception("knowledge reindex failed")
        raise HTTPException(status_code=500, detail=f"重建索引失败：{exc}") from exc
    return {
        "ok": True,
        "revisions_indexed": revisions,
        "chunks": knowledge_index.count_chunks(),
        "summary_chunks": knowledge_index.count_summary_chunks(),
        "transcript_chunks": knowledge_index.count_transcript_chunks(),
    }
