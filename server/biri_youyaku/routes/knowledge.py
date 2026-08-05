"""Knowledge FTS search + document lifecycle + backup."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.knowledge import backup as knowledge_backup
from biri_youyaku.knowledge import index as knowledge_index
from biri_youyaku.knowledge import lifecycle as knowledge_lifecycle
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.lifecycle import LifecycleError
from biri_youyaku.knowledge.retrieve import evidence_hit_to_dict, retrieve

logger = logging.getLogger("biri_youyaku.routes.knowledge")

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class SoftDeleteBody(BaseModel):
    confirm: bool | None = None
    reason: str | None = None


class PurgeBody(BaseModel):
    confirm: bool = True
    confirm_title: str = Field(..., min_length=1)


class BackupBody(BaseModel):
    dry_run: bool = False


def _search_enabled() -> bool:
    return bool(settings.knowledge_search_enabled and settings.knowledge_register_enabled)


def _lifecycle_http(exc: LifecycleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


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


@router.get("/knowledge/status")
async def knowledge_status() -> dict[str, Any]:
    return {
        "ok": True,
        "documents": knowledge_repo.count_documents(),
        "documents_deleted": knowledge_repo.count_deleted_documents(),
        "chunks": knowledge_index.count_chunks(),
        "summary_chunks": knowledge_index.count_summary_chunks(),
        "transcript_chunks": knowledge_index.count_transcript_chunks(),
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
        # rebuild_all does heavy FTS writes — run in thread to avoid blocking the event loop.
        revisions = await asyncio.to_thread(knowledge_index.rebuild_all)
    except Exception as exc:
        logger.exception("knowledge reindex failed")
        raise HTTPException(status_code=500, detail="重建索引失败") from exc
    return {
        "ok": True,
        "revisions_indexed": revisions,
        "chunks": await asyncio.to_thread(knowledge_index.count_chunks),
        "summary_chunks": await asyncio.to_thread(knowledge_index.count_summary_chunks),
        "transcript_chunks": await asyncio.to_thread(knowledge_index.count_transcript_chunks),
    }


# --- Phase D: documents lifecycle + audit + backup ---


@router.get("/knowledge/documents")
async def knowledge_list_documents(
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    docs = knowledge_lifecycle.list_documents(
        include_deleted=include_deleted, limit=limit, offset=offset,
    )
    return {"ok": True, "documents": docs}


@router.get("/knowledge/documents/{document_id}")
async def knowledge_get_document(document_id: str) -> dict[str, Any]:
    doc = knowledge_lifecycle.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "ok": True,
        "document": {
            "id": doc["id"],
            "title": doc.get("title"),
            "author": doc.get("author"),
            "bvid": doc.get("external_bvid"),
            "cid": doc.get("external_cid"),
            "mid": doc.get("mid"),
            "source_url": doc.get("source_url"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "deleted_at": doc.get("deleted_at"),
            "delete_reason": doc.get("delete_reason"),
            "provider": doc.get("provider"),
        },
    }


@router.post("/knowledge/documents/{document_id}/soft-delete")
async def knowledge_soft_delete(
    document_id: str,
    body: SoftDeleteBody | None = None,
) -> dict[str, Any]:
    try:
        doc = knowledge_lifecycle.soft_delete(
            document_id,
            reason=(body.reason if body else None),
            actor="api",
        )
    except LifecycleError as exc:
        raise _lifecycle_http(exc) from exc
    return {
        "ok": True,
        "document": {
            "id": doc["id"],
            "title": doc.get("title"),
            "author": doc.get("author"),
            "bvid": doc.get("external_bvid"),
            "cid": doc.get("external_cid"),
            "deleted_at": doc.get("deleted_at"),
            "delete_reason": doc.get("delete_reason"),
        },
    }


@router.post("/knowledge/documents/{document_id}/restore")
async def knowledge_restore(document_id: str) -> dict[str, Any]:
    try:
        doc = knowledge_lifecycle.restore(document_id, actor="api")
    except LifecycleError as exc:
        raise _lifecycle_http(exc) from exc
    return {
        "ok": True,
        "document": {
            "id": doc["id"],
            "title": doc.get("title"),
            "author": doc.get("author"),
            "bvid": doc.get("external_bvid"),
            "cid": doc.get("external_cid"),
            "deleted_at": doc.get("deleted_at"),
        },
    }


@router.post("/knowledge/documents/{document_id}/purge")
async def knowledge_purge(document_id: str, body: PurgeBody) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="永久删除需要 confirm=true")
    try:
        result = knowledge_lifecycle.purge_permanent(
            document_id,
            confirm_title=body.confirm_title,
            actor="api",
            force=False,
        )
    except LifecycleError as exc:
        raise _lifecycle_http(exc) from exc
    return {"ok": True, **result}


@router.get("/knowledge/audit")
async def knowledge_audit(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    events = knowledge_lifecycle.list_audit_events(limit=limit)
    return {"ok": True, "events": events}


@router.post("/knowledge/backup")
async def create_knowledge_backup(body: BackupBody | None = None) -> dict[str, Any]:
    dry_run = bool(body.dry_run) if body else False
    try:
        # create_backup hashes artifacts and copies trees — run in thread.
        result = await asyncio.to_thread(
            knowledge_backup.create_backup, dry_run=dry_run, actor="api"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="备份失败：源文件缺失") from exc
    except Exception as exc:
        logger.exception("knowledge backup failed")
        raise HTTPException(status_code=500, detail="备份失败") from exc
    return result
