"""Library list / search / reading / trash (v2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from biri_youyaku.auth import require_token
from biri_youyaku.library.repo import LibraryError, get_document_content, list_library, list_trash
from biri_youyaku.library.search import SearchError, search_library
from biri_youyaku.library.util import etag_matches

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


def _http(exc: LibraryError | SearchError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/library")
async def library_list(
    cursor: str | None = Query(default=None),
    up: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    try:
        return list_library(cursor=cursor, up=up, tag=tag, limit=limit)
    except LibraryError as exc:
        raise _http(exc) from exc


@router.get("/library/search")
async def library_search(
    q: str = Query(default=""),
    scope: str = Query(default="all"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    try:
        return search_library(q=q, scope=scope, cursor=cursor, limit=limit)
    except SearchError as exc:
        raise _http(exc) from exc


@router.get("/library/trash")
async def library_trash() -> dict[str, Any]:
    return list_trash()


@router.get("/library/documents/{document_id}/content")
async def library_document_content(
    document_id: str,
    request: Request,
) -> Any:
    payload = get_document_content(document_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    content_hash = payload.pop("content_hash", None)
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    token = f"{content_hash or '-'}|{document.get('deleted_at') or 0}|{document.get('updated_at') or 0}"
    headers = {"ETag": f'"{token}"'}
    if etag_matches(request.headers.get("if-none-match"), token):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)
