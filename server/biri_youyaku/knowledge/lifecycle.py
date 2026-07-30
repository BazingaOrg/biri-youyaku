"""Document soft-delete / restore / permanent purge + audit (Phase D)."""

from __future__ import annotations

import json
import logging
import shutil
from typing import Any

from biri_youyaku.db import connect
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.knowledge.index import (
    _delete_chunks_for_document,
    _delete_transcript_chunks_for_document,
)

logger = logging.getLogger("biri_youyaku.knowledge.lifecycle")

ACTION_SOFT_DELETE = "soft_delete"
ACTION_RESTORE = "restore"
ACTION_PURGE = "purge"
ACTION_BACKUP = "backup"


class LifecycleError(Exception):
    """Domain error for lifecycle operations (mapped to HTTP by routes)."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def record_audit(
    action: str,
    *,
    document_id: str | None = None,
    detail: dict[str, Any] | None = None,
    actor: str = "api",
) -> None:
    timestamp = now_ms()
    detail_json = json.dumps(detail, ensure_ascii=False) if detail is not None else None
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_audit_events (
              occurred_at, action, document_id, detail_json, actor
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (timestamp, action, document_id, detail_json, actor),
        )


def list_audit_events(*, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, occurred_at, action, document_id, detail_json, actor
            FROM knowledge_audit_events
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        detail = None
        if row["detail_json"]:
            try:
                detail = json.loads(row["detail_json"])
            except json.JSONDecodeError:
                detail = {"raw": row["detail_json"]}
        out.append(
            {
                "id": row["id"],
                "occurred_at": row["occurred_at"],
                "action": row["action"],
                "document_id": row["document_id"],
                "detail": detail,
                "actor": row["actor"],
            }
        )
    return out


def get_document(document_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
              id, provider, external_bvid, external_cid, title, author, mid,
              source_url, created_at, updated_at, deleted_at, delete_reason
            FROM knowledge_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_documents(*, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Lite list: id, title, author, bvid, cid, deleted_at."""
    sql = """
        SELECT
          id,
          title,
          author,
          external_bvid AS bvid,
          external_cid AS cid,
          deleted_at
        FROM knowledge_documents
    """
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY updated_at DESC, created_at DESC"
    with connect() as connection:
        rows = connection.execute(sql).fetchall()
    return [dict(row) for row in rows]


def soft_delete(
    document_id: str,
    *,
    reason: str | None = None,
    actor: str = "api",
) -> dict[str, Any]:
    doc = get_document(document_id)
    if doc is None:
        raise LifecycleError("文档不存在", status_code=404)
    if doc.get("deleted_at") is not None:
        return doc
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_documents
            SET deleted_at = ?, delete_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (timestamp, reason, timestamp, document_id),
        )
    record_audit(
        ACTION_SOFT_DELETE,
        document_id=document_id,
        detail={"reason": reason, "title": doc.get("title"), "bvid": doc.get("external_bvid")},
        actor=actor,
    )
    updated = get_document(document_id)
    assert updated is not None
    return updated


def restore(document_id: str, *, actor: str = "api") -> dict[str, Any]:
    doc = get_document(document_id)
    if doc is None:
        raise LifecycleError("文档不存在", status_code=404)
    if doc.get("deleted_at") is None:
        return doc
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_documents
            SET deleted_at = NULL, delete_reason = NULL, updated_at = ?
            WHERE id = ?
            """,
            (timestamp, document_id),
        )
    record_audit(
        ACTION_RESTORE,
        document_id=document_id,
        detail={"title": doc.get("title"), "bvid": doc.get("external_bvid")},
        actor=actor,
    )
    updated = get_document(document_id)
    assert updated is not None
    return updated


def _confirm_matches(doc: dict[str, Any], confirm_title: str) -> bool:
    token = (confirm_title or "").strip()
    if not token:
        return False
    title = (doc.get("title") or "").strip()
    bvid = (doc.get("external_bvid") or "").strip()
    return token == title or token == bvid


def purge_permanent(
    document_id: str,
    *,
    confirm_title: str | None = None,
    actor: str = "api",
    force: bool = False,
) -> dict[str, Any]:
    """Hard-delete document: chunks, revisions, job_links, artifacts, row + disk tree.

    API callers must pass ``confirm_title`` matching title or bvid unless ``force``.
    Cleanup auto-purge uses ``force=True``.
    """
    doc = get_document(document_id)
    if doc is None:
        raise LifecycleError("文档不存在", status_code=404)
    if not force and not _confirm_matches(doc, confirm_title or ""):
        raise LifecycleError(
            "永久删除需二次确认：confirm_title 必须与文档标题或 bvid 完全一致",
            status_code=400,
        )

    with connect() as connection:
        artifact_rows = connection.execute(
            "SELECT storage_path FROM knowledge_artifacts WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        storage_paths = [row["storage_path"] for row in artifact_rows]

        _delete_chunks_for_document(connection, document_id)
        _delete_transcript_chunks_for_document(connection, document_id)

        connection.execute(
            "DELETE FROM knowledge_job_links WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_summary_revisions WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_content_revisions WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_artifacts WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_documents WHERE id = ?",
            (document_id,),
        )

    # Disk: individual files then document directory if empty/remaining.
    for path_str in storage_paths:
        path = art.resolve_stored_path(path_str)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            logger.warning("Failed to remove artifact file %s", path, exc_info=True)
    doc_dir = art.document_dir(document_id)
    try:
        if doc_dir.is_dir():
            shutil.rmtree(doc_dir, ignore_errors=True)
    except OSError:
        logger.warning("Failed to remove document dir %s", doc_dir, exc_info=True)

    record_audit(
        ACTION_PURGE,
        document_id=document_id,
        detail={
            "title": doc.get("title"),
            "bvid": doc.get("external_bvid"),
            "cid": doc.get("external_cid"),
            "artifact_count": len(storage_paths),
            "force": force,
        },
        actor=actor,
    )
    return {
        "id": document_id,
        "purged": True,
        "title": doc.get("title"),
        "bvid": doc.get("external_bvid"),
    }


def list_expired_soft_deleted(*, older_than_ms: int) -> list[str]:
    """Document ids soft-deleted before ``older_than_ms`` (absolute cutoff timestamp)."""
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id FROM knowledge_documents
            WHERE deleted_at IS NOT NULL AND deleted_at < ?
            ORDER BY deleted_at ASC
            """,
            (older_than_ms,),
        ).fetchall()
    return [row["id"] for row in rows]


def purge_expired_soft_deleted(*, retention_days: int) -> int:
    """Auto-purge soft-deleted docs older than retention_days. Returns count purged."""
    if retention_days < 0:
        return 0
    cutoff = now_ms() - int(retention_days) * 24 * 60 * 60 * 1000
    ids = list_expired_soft_deleted(older_than_ms=cutoff)
    purged = 0
    for document_id in ids:
        try:
            purge_permanent(document_id, actor="cleanup", force=True)
            purged += 1
        except LifecycleError:
            logger.warning("auto-purge skipped missing doc %s", document_id)
        except Exception:
            logger.exception("auto-purge failed for document %s", document_id)
    return purged
