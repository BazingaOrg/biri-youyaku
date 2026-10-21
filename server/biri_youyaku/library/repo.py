"""Library list, trash, and document content queries."""

from __future__ import annotations

import json
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs.model import JobStatus
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.library.util import (
    CursorError,
    days_left,
    decode_cursor,
    encode_cursor,
    expires_at_ms,
    parse_tags,
)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50


class LibraryError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _MAX_LIMIT))


def _tag_exists_sql(column: str) -> str:
    return (
        f"EXISTS (SELECT 1 FROM json_each(COALESCE({column}, '[]')) "
        "AS tag_item WHERE tag_item.value = ?)"
    )


def _row_item(
    *,
    kind: str,
    item_id: str,
    document_id: str | None,
    job_id: str | None,
    title: str | None,
    author: str | None,
    mid: Any,
    bvid: str | None,
    cid: Any,
    duration: Any,
    tags_json: Any,
    tldr: str | None,
    saved_at: int | None,
    source_url: str | None,
    legacy: bool,
    legacy_reason: str | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "document_id": document_id,
        "job_id": job_id,
        "title": title,
        "author": author,
        "mid": mid,
        "bvid": bvid,
        "cid": cid,
        "duration": duration,
        "tags": parse_tags(tags_json),
        "tldr": tldr,
        "saved_at": saved_at,
        "source_url": source_url,
        "legacy": legacy,
        "legacy_reason": legacy_reason,
    }


def _after_cursor_sql(alias_time: str, alias_kind: str, alias_id: str) -> str:
    return (
        f"({alias_time} < ?) OR "
        f"({alias_time} = ? AND {alias_kind} > ?) OR "
        f"({alias_time} = ? AND {alias_kind} = ? AND {alias_id} < ?)"
    )


def list_library(
    *,
    cursor: str | None = None,
    up: str | int | None = None,
    tag: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    page_size = _clamp_limit(limit)
    mid: int | None = None
    if up is not None and str(up).strip() != "":
        try:
            mid = int(str(up).strip())
        except ValueError as exc:
            raise LibraryError("up 必须是数字 mid", status_code=400) from exc
    tag_value = tag.strip() if isinstance(tag, str) and tag.strip() else None
    try:
        cursor_payload = decode_cursor(cursor)
    except CursorError as exc:
        raise LibraryError("cursor 无效", status_code=400) from exc

    cursor_t: int | None = None
    cursor_k: str | None = None
    cursor_i: str | None = None
    if cursor_payload is not None:
        try:
            cursor_t = int(cursor_payload["t"])
            cursor_k = str(cursor_payload["k"])
            cursor_i = str(cursor_payload["i"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LibraryError("cursor 无效", status_code=400) from exc

    if not settings.knowledge_register_enabled:
        items = _list_jobs_only(
            mid=mid,
            tag_value=tag_value,
            cursor_t=cursor_t,
            cursor_k=cursor_k,
            cursor_i=cursor_i,
            page_size=page_size,
            register_disabled=True,
        )
    else:
        items = _list_documents_and_legacy(
            mid=mid,
            tag_value=tag_value,
            cursor_t=cursor_t,
            cursor_k=cursor_k,
            cursor_i=cursor_i,
            page_size=page_size,
        )

    next_cursor = None
    if len(items) > page_size:
        items = items[:page_size]
        last = items[-1]
        next_cursor = encode_cursor(
            {"t": last["saved_at"] or 0, "k": last["kind"], "i": last["id"]}
        )
    total = _count_library(
        mid=mid,
        tag_value=tag_value,
        jobs_only=not settings.knowledge_register_enabled,
    )
    return {"ok": True, "items": items, "next_cursor": next_cursor, "total": total}


def _count_library(*, mid: int | None, tag_value: str | None, jobs_only: bool) -> int:
    """Match the list filters, ignoring the page cursor."""
    if jobs_only:
        where = [
            "j.status = ?",
            "IFNULL(j.summary_path, '') != ''",
            "IFNULL(r.status, '') != 'purged'",
        ]
        params: list[Any] = [JobStatus.COMPLETED.value]
        if mid is not None:
            where.append("j.mid = ?")
            params.append(mid)
        if tag_value is not None:
            where.append(_tag_exists_sql("j.tags_json"))
            params.append(tag_value)
        sql = f"""
            SELECT COUNT(*) AS n
            FROM jobs j
            LEFT JOIN knowledge_reconcile r ON r.job_id = j.id
            WHERE {' AND '.join(where)}
        """
        count_params = params
    else:
        doc_where = ["d.deleted_at IS NULL"]
        job_where = [
            "j.status = ?",
            "IFNULL(j.summary_path, '') != ''",
            "l.job_id IS NULL",
            "IFNULL(r.status, '') != 'purged'",
        ]
        doc_params: list[Any] = []
        job_params: list[Any] = [JobStatus.COMPLETED.value]
        if mid is not None:
            doc_where.append("d.mid = ?")
            job_where.append("j.mid = ?")
            doc_params.append(mid)
            job_params.append(mid)
        if tag_value is not None:
            doc_where.append(_tag_exists_sql("d.tags_json"))
            job_where.append(_tag_exists_sql("j.tags_json"))
            doc_params.append(tag_value)
            job_params.append(tag_value)
        sql = f"""
            SELECT
              (
                SELECT COUNT(*) FROM knowledge_documents d
                WHERE {' AND '.join(doc_where)}
              ) + (
                SELECT COUNT(*)
                FROM jobs j
                LEFT JOIN knowledge_job_links l ON l.job_id = j.id
                LEFT JOIN knowledge_reconcile r ON r.job_id = j.id
                WHERE {' AND '.join(job_where)}
              ) AS n
        """
        count_params = [*doc_params, *job_params]
    with connect() as connection:
        row = connection.execute(sql, count_params).fetchone()
    return int(row["n"] or 0)


def _list_jobs_only(
    *,
    mid: int | None,
    tag_value: str | None,
    cursor_t: int | None,
    cursor_k: str | None,
    cursor_i: str | None,
    page_size: int,
    register_disabled: bool,
) -> list[dict[str, Any]]:
    where = [
        "j.status = ?",
        "IFNULL(j.summary_path, '') != ''",
        "IFNULL(r.status, '') != 'purged'",
    ]
    params: list[Any] = [JobStatus.COMPLETED.value]
    if mid is not None:
        where.append("j.mid = ?")
        params.append(mid)
    if tag_value is not None:
        where.append(_tag_exists_sql("j.tags_json"))
        params.append(tag_value)
    if cursor_t is not None and cursor_k is not None and cursor_i is not None:
        where.append(
            _after_cursor_sql("COALESCE(j.completed_at, j.created_at)", "'legacy_job'", "j.id")
        )
        params.extend([cursor_t, cursor_t, cursor_k, cursor_t, cursor_k, cursor_i])
    sql = f"""
        SELECT
          j.id AS job_id,
          j.title AS title,
          j.author AS author,
          j.mid AS mid,
          j.bvid AS bvid,
          j.cid AS cid,
          j.duration AS duration,
          j.tags_json AS tags_json,
          j.url AS source_url,
          COALESCE(j.completed_at, j.created_at) AS saved_at,
          r.reason AS legacy_reason
        FROM jobs j
        LEFT JOIN knowledge_reconcile r ON r.job_id = j.id
        WHERE {' AND '.join(where)}
        ORDER BY saved_at DESC, j.id DESC
        LIMIT ?
    """
    params.append(page_size + 1)
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        reason = row["legacy_reason"]
        if register_disabled and not reason:
            reason = "knowledge_register_disabled"
        items.append(
            _row_item(
                kind="legacy_job",
                item_id=row["job_id"],
                document_id=None,
                job_id=row["job_id"],
                title=row["title"],
                author=row["author"],
                mid=row["mid"],
                bvid=row["bvid"],
                cid=row["cid"],
                duration=row["duration"],
                tags_json=row["tags_json"],
                tldr=None,
                saved_at=row["saved_at"],
                source_url=row["source_url"],
                legacy=True,
                legacy_reason=reason,
            )
        )
    return items


def _list_documents_and_legacy(
    *,
    mid: int | None,
    tag_value: str | None,
    cursor_t: int | None,
    cursor_k: str | None,
    cursor_i: str | None,
    page_size: int,
) -> list[dict[str, Any]]:
    doc_where = ["d.deleted_at IS NULL"]
    job_where = [
        "j.status = ?",
        "IFNULL(j.summary_path, '') != ''",
        "l.job_id IS NULL",
        "IFNULL(r.status, '') != 'purged'",
    ]
    doc_params: list[Any] = []
    job_params: list[Any] = [JobStatus.COMPLETED.value]
    if mid is not None:
        doc_where.append("d.mid = ?")
        job_where.append("j.mid = ?")
        doc_params.append(mid)
        job_params.append(mid)
    if tag_value is not None:
        doc_where.append(_tag_exists_sql("d.tags_json"))
        job_where.append(_tag_exists_sql("j.tags_json"))
        doc_params.append(tag_value)
        job_params.append(tag_value)
    if cursor_t is not None and cursor_k is not None and cursor_i is not None:
        doc_where.append(_after_cursor_sql("d.updated_at", "'document'", "d.id"))
        job_where.append(
            _after_cursor_sql("COALESCE(j.completed_at, j.created_at)", "'legacy_job'", "j.id")
        )
        cursor_params = [cursor_t, cursor_t, cursor_k, cursor_t, cursor_k, cursor_i]
        doc_params.extend(cursor_params)
        job_params.extend(cursor_params)

    sql = f"""
        SELECT * FROM (
          SELECT
            'document' AS kind,
            d.id AS id,
            d.id AS document_id,
            (
              SELECT l.job_id FROM knowledge_job_links l
              WHERE l.document_id = d.id AND l.unlinked_at IS NULL
              ORDER BY l.linked_at DESC
              LIMIT 1
            ) AS job_id,
            d.title AS title,
            d.author AS author,
            d.mid AS mid,
            d.external_bvid AS bvid,
            d.external_cid AS cid,
            d.duration AS duration,
            d.tags_json AS tags_json,
            d.tldr AS tldr,
            d.updated_at AS saved_at,
            d.source_url AS source_url,
            0 AS legacy,
            NULL AS legacy_reason
          FROM knowledge_documents d
          WHERE {' AND '.join(doc_where)}
          UNION ALL
          SELECT
            'legacy_job' AS kind,
            j.id AS id,
            NULL AS document_id,
            j.id AS job_id,
            j.title AS title,
            j.author AS author,
            j.mid AS mid,
            j.bvid AS bvid,
            j.cid AS cid,
            j.duration AS duration,
            j.tags_json AS tags_json,
            NULL AS tldr,
            COALESCE(j.completed_at, j.created_at) AS saved_at,
            j.url AS source_url,
            1 AS legacy,
            r.reason AS legacy_reason
          FROM jobs j
          LEFT JOIN knowledge_job_links l ON l.job_id = j.id
          LEFT JOIN knowledge_reconcile r ON r.job_id = j.id
          WHERE {' AND '.join(job_where)}
        ) AS library_items
        ORDER BY saved_at DESC, kind ASC, id DESC
        LIMIT ?
    """
    params = [*doc_params, *job_params, page_size + 1]
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            _row_item(
                kind=row["kind"],
                item_id=row["id"],
                document_id=row["document_id"],
                job_id=row["job_id"],
                title=row["title"],
                author=row["author"],
                mid=row["mid"],
                bvid=row["bvid"],
                cid=row["cid"],
                duration=row["duration"],
                tags_json=row["tags_json"],
                tldr=row["tldr"],
                saved_at=row["saved_at"],
                source_url=row["source_url"],
                legacy=bool(row["legacy"]),
                legacy_reason=row["legacy_reason"],
            )
        )
    return items


def list_trash(*, limit: int = 500) -> dict[str, Any]:
    cap = max(1, min(int(limit or 500), 1000))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
              id, title, author, external_bvid AS bvid, deleted_at
            FROM knowledge_documents
            WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC, id DESC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        deleted_at = row["deleted_at"]
        items.append(
            {
                "document_id": row["id"],
                "title": row["title"],
                "author": row["author"],
                "bvid": row["bvid"],
                "deleted_at": deleted_at,
                "expires_at": expires_at_ms(deleted_at),
                "days_left": days_left(deleted_at),
            }
        )
    return {"ok": True, "items": items}


def get_document_content(document_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        doc = connection.execute(
            """
            SELECT
              id, title, author, mid, external_bvid, external_cid, source_url,
              tags_json, duration, tldr, created_at, updated_at, deleted_at
            FROM knowledge_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        if doc is None:
            return None
        job_row = connection.execute(
            """
            SELECT job_id FROM knowledge_job_links
            WHERE document_id = ? AND unlinked_at IS NULL
            ORDER BY linked_at DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        summary_row = connection.execute(
            """
            SELECT sr.content_hash AS content_hash, a.storage_path AS storage_path
            FROM knowledge_summary_revisions sr
            JOIN knowledge_artifacts a ON a.id = sr.artifact_id
            WHERE sr.document_id = ? AND sr.is_active = 1
            ORDER BY sr.created_at DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        content_row = connection.execute(
            """
            SELECT cr.id AS content_revision_id, a.storage_path AS storage_path
            FROM knowledge_content_revisions cr
            JOIN knowledge_artifacts a ON a.id = cr.artifact_id
            WHERE cr.document_id = ?
            ORDER BY cr.created_at DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        note_rows = connection.execute(
            """
            SELECT c.chunk_ord AS chunk_ord,
                   c.heading_path AS heading_path,
                   c.start_sec AS start_sec,
                   c.chunk_text AS chunk_text
            FROM knowledge_rag_chunks c
            JOIN knowledge_summary_revisions sr
              ON sr.id = c.summary_revision_id AND sr.is_active = 1
            WHERE c.document_id = ?
            ORDER BY c.chunk_ord ASC
            """,
            (document_id,),
        ).fetchall()
        transcript_chunk_rows = []
        if content_row is not None:
            transcript_chunk_rows = connection.execute(
                """
                SELECT chunk_ord, start_sec, end_sec, chunk_text
                FROM knowledge_transcript_chunks
                WHERE document_id = ? AND content_revision_id = ?
                ORDER BY chunk_ord ASC
                """,
                (document_id, content_row["content_revision_id"]),
            ).fetchall()

    markdown = ""
    content_hash = None
    if summary_row is not None:
        content_hash = summary_row["content_hash"]
        path = art.resolve_stored_path(summary_row["storage_path"])
        try:
            if path.is_file():
                markdown = path.read_text(encoding="utf-8")
        except OSError:
            markdown = ""

    cues: list[dict[str, Any]] = []
    if content_row is not None:
        cues = _cues_from_artifact(content_row["storage_path"])

    deleted_at = doc["deleted_at"]
    document = {
        "document_id": doc["id"],
        "job_id": job_row["job_id"] if job_row else None,
        "title": doc["title"],
        "author": doc["author"],
        "mid": doc["mid"],
        "bvid": doc["external_bvid"],
        "cid": doc["external_cid"],
        "source_url": doc["source_url"],
        "tags": parse_tags(doc["tags_json"]),
        "tldr": doc["tldr"],
        "duration": doc["duration"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "deleted_at": deleted_at,
        "expires_at": expires_at_ms(deleted_at),
    }
    return {
        "ok": True,
        "document": document,
        "markdown": markdown,
        "cues": cues,
        "note_chunks": [
            {
                "chunk_ord": row["chunk_ord"],
                "heading_path": row["heading_path"],
                "start_sec": row["start_sec"],
                "text": row["chunk_text"],
            }
            for row in note_rows
        ],
        "transcript_chunks": [
            {
                "chunk_ord": row["chunk_ord"],
                "start_sec": row["start_sec"],
                "end_sec": row["end_sec"],
                "text": row["chunk_text"],
            }
            for row in transcript_chunk_rows
        ],
        "content_hash": content_hash,
    }


def _cues_from_artifact(storage_path: str) -> list[dict[str, Any]]:
    path = art.resolve_stored_path(storage_path)
    try:
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    segments = payload.get("segments") or []
    if not isinstance(segments, list):
        return []
    cues: list[dict[str, Any]] = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("raw_text") or item.get("text") or "").strip()
        if not text:
            continue
        cues.append(
            {
                "start": float(item.get("start") or 0.0),
                "end": float(item.get("end") or 0.0),
                "text": text,
            }
        )
    return cues
