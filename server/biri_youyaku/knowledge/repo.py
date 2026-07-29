"""SQLite CRUD for knowledge_* tables."""

from __future__ import annotations

import uuid
from typing import Any, Collection

from biri_youyaku.db import connect
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge.model import (
    ARTIFACT_KIND_SUMMARY,
    ARTIFACT_KIND_TRANSCRIPT_RAW,
    JobLink,
    PROVIDER_BILIBILI,
    ReconcileRow,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def find_document_id(
    *,
    provider: str,
    external_bvid: str,
    external_cid: int,
) -> str | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM knowledge_documents
            WHERE provider = ? AND external_bvid = ? AND external_cid = ?
            """,
            (provider, external_bvid, external_cid),
        ).fetchone()
    return row["id"] if row else None


def upsert_document(
    *,
    provider: str = PROVIDER_BILIBILI,
    external_bvid: str,
    external_cid: int,
    title: str | None,
    author: str | None,
    mid: int | None,
    source_url: str | None,
) -> str:
    """Find or create document by (provider, bvid, cid); refresh metadata."""
    timestamp = now_ms()
    existing = find_document_id(
        provider=provider, external_bvid=external_bvid, external_cid=external_cid
    )
    if existing is not None:
        with connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_documents
                SET title = COALESCE(?, title),
                    author = COALESCE(?, author),
                    mid = COALESCE(?, mid),
                    source_url = COALESCE(?, source_url),
                    updated_at = ?
                WHERE id = ?
                """,
                (title, author, mid, source_url, timestamp, existing),
            )
        return existing

    document_id = _new_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_documents (
              id, provider, external_bvid, external_cid, title, author, mid,
              source_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                provider,
                external_bvid,
                external_cid,
                title,
                author,
                mid,
                source_url,
                timestamp,
                timestamp,
            ),
        )
    return document_id


def get_artifact_id(
    document_id: str, kind: str, content_hash: str
) -> str | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM knowledge_artifacts
            WHERE document_id = ? AND kind = ? AND content_hash = ?
            """,
            (document_id, kind, content_hash),
        ).fetchone()
    return row["id"] if row else None


def insert_artifact(
    *,
    document_id: str,
    kind: str,
    content_hash: str,
    storage_path: str,
    byte_size: int,
) -> str:
    existing = get_artifact_id(document_id, kind, content_hash)
    if existing is not None:
        return existing
    artifact_id = _new_id()
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_artifacts (
              id, document_id, kind, content_hash, storage_path, byte_size, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                document_id,
                kind,
                content_hash,
                storage_path,
                byte_size,
                timestamp,
            ),
        )
    return artifact_id


def get_content_revision_id(document_id: str, content_hash: str) -> str | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM knowledge_content_revisions
            WHERE document_id = ? AND content_hash = ?
            """,
            (document_id, content_hash),
        ).fetchone()
    return row["id"] if row else None


def upsert_content_revision(
    *,
    document_id: str,
    artifact_id: str,
    content_hash: str,
    subtitle_source: str | None,
) -> str:
    existing = get_content_revision_id(document_id, content_hash)
    if existing is not None:
        return existing
    revision_id = _new_id()
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_content_revisions (
              id, document_id, artifact_id, content_hash, subtitle_source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                document_id,
                artifact_id,
                content_hash,
                subtitle_source,
                timestamp,
            ),
        )
    return revision_id


def find_summary_revision_by_hash(
    document_id: str, content_hash: str
) -> tuple[str, int] | None:
    """Return (revision_id, is_active) for the newest revision with this hash."""
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, is_active FROM knowledge_summary_revisions
            WHERE document_id = ? AND content_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id, content_hash),
        ).fetchone()
    if row is None:
        return None
    return row["id"], int(row["is_active"])


def deactivate_active_summary_revisions(document_id: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_summary_revisions
            SET is_active = 0
            WHERE document_id = ? AND is_active = 1
            """,
            (document_id,),
        )


def set_summary_revision_active(revision_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE knowledge_summary_revisions SET is_active = 1 WHERE id = ?",
            (revision_id,),
        )


def insert_summary_revision(
    *,
    document_id: str,
    artifact_id: str,
    content_hash: str,
    source_job_id: str | None,
    is_active: int = 1,
) -> str:
    revision_id = _new_id()
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_summary_revisions (
              id, document_id, artifact_id, content_hash, source_job_id,
              is_active, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                document_id,
                artifact_id,
                content_hash,
                source_job_id,
                is_active,
                timestamp,
            ),
        )
    return revision_id


def upsert_summary_revision(
    *,
    document_id: str,
    artifact_id: str,
    content_hash: str,
    source_job_id: str | None,
) -> str:
    """Activate a summary revision for this content hash (create if needed).

    New content hash → deactivate previous actives, insert new active revision.
    Same content hash → reuse existing revision; ensure it is the sole active.
    """
    found = find_summary_revision_by_hash(document_id, content_hash)
    if found is None:
        deactivate_active_summary_revisions(document_id)
        return insert_summary_revision(
            document_id=document_id,
            artifact_id=artifact_id,
            content_hash=content_hash,
            source_job_id=source_job_id,
            is_active=1,
        )
    revision_id, is_active = found
    if not is_active:
        deactivate_active_summary_revisions(document_id)
        set_summary_revision_active(revision_id)
    return revision_id


def get_job_link(job_id: str) -> JobLink | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_job_links WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return JobLink(
        job_id=row["job_id"],
        document_id=row["document_id"],
        summary_revision_id=row["summary_revision_id"],
        content_revision_id=row["content_revision_id"],
        linked_at=row["linked_at"],
        unlinked_at=row["unlinked_at"],
    )


def upsert_job_link(
    *,
    job_id: str,
    document_id: str,
    summary_revision_id: str | None,
    content_revision_id: str | None,
) -> None:
    """Insert job link if missing; do not re-link when already unlinked."""
    existing = get_job_link(job_id)
    if existing is not None:
        if existing.unlinked_at is not None:
            return
        with connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_job_links
                SET document_id = ?,
                    summary_revision_id = COALESCE(?, summary_revision_id),
                    content_revision_id = COALESCE(?, content_revision_id)
                WHERE job_id = ? AND unlinked_at IS NULL
                """,
                (document_id, summary_revision_id, content_revision_id, job_id),
            )
        return
    timestamp = now_ms()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_job_links (
              job_id, document_id, summary_revision_id, content_revision_id,
              linked_at, unlinked_at
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                job_id,
                document_id,
                summary_revision_id,
                content_revision_id,
                timestamp,
            ),
        )


def unlink_job(job_id: str, *, connection: Any | None = None) -> None:
    """Soft-unlink: set unlinked_at where still linked. Never touches artifacts."""
    timestamp = now_ms()
    if connection is not None:
        connection.execute(
            """
            UPDATE knowledge_job_links
            SET unlinked_at = ?
            WHERE job_id = ? AND unlinked_at IS NULL
            """,
            (timestamp, job_id),
        )
        return
    with connect() as conn:
        conn.execute(
            """
            UPDATE knowledge_job_links
            SET unlinked_at = ?
            WHERE job_id = ? AND unlinked_at IS NULL
            """,
            (timestamp, job_id),
        )


def unlink_jobs(job_ids: Collection[str], *, connection: Any | None = None) -> None:
    ids = list(job_ids)
    if not ids:
        return
    timestamp = now_ms()
    placeholders = ",".join("?" for _ in ids)
    sql = f"""
        UPDATE knowledge_job_links
        SET unlinked_at = ?
        WHERE job_id IN ({placeholders}) AND unlinked_at IS NULL
    """
    params = (timestamp, *ids)
    if connection is not None:
        connection.execute(sql, params)
        return
    with connect() as conn:
        conn.execute(sql, params)


def get_reconcile(job_id: str) -> ReconcileRow | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_reconcile WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return ReconcileRow(
        job_id=row["job_id"],
        status=row["status"],
        reason=row["reason"],
        attempts=row["attempts"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def set_reconcile(
    job_id: str,
    *,
    status: str,
    reason: str | None = None,
    last_error: str | None = None,
    increment_attempts: bool = False,
) -> None:
    timestamp = now_ms()
    existing = get_reconcile(job_id)
    if existing is None:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_reconcile (
                  job_id, status, reason, attempts, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    status,
                    reason,
                    1 if increment_attempts else 0,
                    last_error,
                    timestamp,
                    timestamp,
                ),
            )
        return
    attempts = existing.attempts + (1 if increment_attempts else 0)
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_reconcile
            SET status = ?, reason = ?, attempts = ?, last_error = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, reason, attempts, last_error, timestamp, job_id),
        )


def count_documents() -> int:
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS n FROM knowledge_documents").fetchone()
    return int(row["n"])


def count_artifacts(*, document_id: str | None = None, kind: str | None = None) -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if document_id is not None:
        clauses.append("document_id = ?")
        params.append(document_id)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_artifacts {where}", params
        ).fetchone()
    return int(row["n"])


def count_summary_revisions(document_id: str, *, active_only: bool = False) -> int:
    sql = "SELECT COUNT(*) AS n FROM knowledge_summary_revisions WHERE document_id = ?"
    params: list[Any] = [document_id]
    if active_only:
        sql += " AND is_active = 1"
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
    return int(row["n"])


def count_content_revisions(document_id: str) -> int:
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM knowledge_content_revisions WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    return int(row["n"])


def list_artifact_paths(document_id: str) -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT storage_path FROM knowledge_artifacts WHERE document_id = ?",
            (document_id,),
        ).fetchall()
    return [row["storage_path"] for row in rows]


def list_completed_jobs_with_summary(*, limit: int = 200) -> list[str]:
    """Return job ids eligible for knowledge registration scan (lite)."""
    from biri_youyaku.jobs.model import JobStatus

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id FROM jobs
            WHERE status = ?
              AND summary_path IS NOT NULL
              AND summary_path != ''
            ORDER BY completed_at DESC, created_at DESC
            LIMIT ?
            """,
            (JobStatus.COMPLETED.value, limit),
        ).fetchall()
    return [row["id"] for row in rows]


# Re-export kind constants for callers that import repo only.
__all__ = [
    "ARTIFACT_KIND_SUMMARY",
    "ARTIFACT_KIND_TRANSCRIPT_RAW",
    "count_artifacts",
    "count_content_revisions",
    "count_documents",
    "count_summary_revisions",
    "deactivate_active_summary_revisions",
    "find_document_id",
    "find_summary_revision_by_hash",
    "get_artifact_id",
    "get_content_revision_id",
    "get_job_link",
    "get_reconcile",
    "insert_artifact",
    "insert_summary_revision",
    "list_artifact_paths",
    "list_completed_jobs_with_summary",
    "set_reconcile",
    "set_summary_revision_active",
    "unlink_job",
    "unlink_jobs",
    "upsert_content_revision",
    "upsert_document",
    "upsert_job_link",
    "upsert_summary_revision",
]
