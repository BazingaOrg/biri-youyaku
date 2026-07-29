"""Build / rebuild FTS index from active knowledge summary revisions.

Index failures must never fail summary jobs — callers use best-effort try/except.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from biri_youyaku.db import connect
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge.chunker import chunk_summary_markdown, fts_prepare_text

logger = logging.getLogger("biri_youyaku.knowledge.index")


def _new_id() -> str:
    return str(uuid.uuid4())


def _delete_chunks_for_revision(connection: Any, summary_revision_id: str) -> None:
    rows = connection.execute(
        "SELECT id FROM knowledge_rag_chunks WHERE summary_revision_id = ?",
        (summary_revision_id,),
    ).fetchall()
    for row in rows:
        connection.execute(
            "DELETE FROM knowledge_rag_chunks_fts WHERE chunk_id = ?",
            (row["id"],),
        )
    connection.execute(
        "DELETE FROM knowledge_rag_chunks WHERE summary_revision_id = ?",
        (summary_revision_id,),
    )


def _delete_chunks_for_document(connection: Any, document_id: str) -> None:
    rows = connection.execute(
        "SELECT id FROM knowledge_rag_chunks WHERE document_id = ?",
        (document_id,),
    ).fetchall()
    for row in rows:
        connection.execute(
            "DELETE FROM knowledge_rag_chunks_fts WHERE chunk_id = ?",
            (row["id"],),
        )
    connection.execute(
        "DELETE FROM knowledge_rag_chunks WHERE document_id = ?",
        (document_id,),
    )


def index_summary_revision(
    document_id: str,
    revision_id: str,
    *,
    artifact_path: str | Path | None = None,
    text: str | None = None,
) -> int:
    """Replace chunks for this summary revision. Returns number of chunks written."""
    body = text
    if body is None:
        if artifact_path is None:
            raise ValueError("artifact_path or text required")
        path = Path(artifact_path)
        if not path.is_file():
            logger.warning(
                "index_summary_revision: artifact missing doc=%s rev=%s path=%s",
                document_id,
                revision_id,
                path,
            )
            return 0
        body = path.read_text(encoding="utf-8")

    chunks = chunk_summary_markdown(body)
    timestamp = now_ms()
    with connect() as connection:
        _delete_chunks_for_revision(connection, revision_id)
        for chunk in chunks:
            chunk_id = _new_id()
            connection.execute(
                """
                INSERT INTO knowledge_rag_chunks (
                  id, document_id, summary_revision_id, source_level,
                  heading_path, chunk_text, chunk_ord, created_at
                )
                VALUES (?, ?, ?, 'summary', ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    revision_id,
                    chunk.heading_path,
                    chunk.chunk_text,
                    chunk.chunk_ord,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_rag_chunks_fts (
                  chunk_id, document_id, summary_revision_id, heading_path, body
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    revision_id,
                    fts_prepare_text(chunk.heading_path),
                    fts_prepare_text(chunk.chunk_text),
                ),
            )
    return len(chunks)


def _active_summary_rows(*, limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
          sr.id AS revision_id,
          sr.document_id AS document_id,
          a.storage_path AS storage_path
        FROM knowledge_summary_revisions sr
        JOIN knowledge_artifacts a ON a.id = sr.artifact_id
        WHERE sr.is_active = 1
        ORDER BY sr.created_at DESC
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _revision_has_chunks(summary_revision_id: str) -> bool:
    with connect() as connection:
        row = connection.execute(
            "SELECT 1 AS n FROM knowledge_rag_chunks WHERE summary_revision_id = ? LIMIT 1",
            (summary_revision_id,),
        ).fetchone()
    return row is not None


def index_document_active_summary(document_id: str) -> int:
    """Index the active summary revision for one document (if any).

    Drops chunks for inactive revisions of the same document so FTS stays lean.
    """
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
              sr.id AS revision_id,
              a.storage_path AS storage_path
            FROM knowledge_summary_revisions sr
            JOIN knowledge_artifacts a ON a.id = sr.artifact_id
            WHERE sr.document_id = ? AND sr.is_active = 1
            ORDER BY sr.created_at DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        # Remove chunks belonging to non-active revisions for this document.
        stale = connection.execute(
            """
            SELECT c.id AS chunk_id, c.summary_revision_id AS revision_id
            FROM knowledge_rag_chunks c
            LEFT JOIN knowledge_summary_revisions sr ON sr.id = c.summary_revision_id
            WHERE c.document_id = ?
              AND (sr.id IS NULL OR sr.is_active = 0)
            """,
            (document_id,),
        ).fetchall()
        for item in stale:
            connection.execute(
                "DELETE FROM knowledge_rag_chunks_fts WHERE chunk_id = ?",
                (item["chunk_id"],),
            )
            connection.execute(
                "DELETE FROM knowledge_rag_chunks WHERE id = ?",
                (item["chunk_id"],),
            )
    if row is None:
        with connect() as connection:
            _delete_chunks_for_document(connection, document_id)
        return 0
    return index_summary_revision(
        document_id,
        row["revision_id"],
        artifact_path=row["storage_path"],
    )


def index_active_summaries(*, limit: int | None = None, only_missing: bool = True) -> int:
    """Index active summary revisions. Returns number of revisions indexed."""
    rows = _active_summary_rows(limit=limit)
    indexed = 0
    for row in rows:
        if only_missing and _revision_has_chunks(row["revision_id"]):
            continue
        try:
            n = index_summary_revision(
                row["document_id"],
                row["revision_id"],
                artifact_path=row["storage_path"],
            )
            if n >= 0:
                indexed += 1
        except Exception:
            logger.exception(
                "index_active_summaries failed doc=%s rev=%s",
                row["document_id"],
                row["revision_id"],
            )
    return indexed


def rebuild_all() -> int:
    """Clear all chunks + FTS, reindex every active summary revision."""
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_rag_chunks_fts")
        connection.execute("DELETE FROM knowledge_rag_chunks")
    return index_active_summaries(limit=None, only_missing=False)


def count_chunks() -> int:
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM knowledge_rag_chunks"
        ).fetchone()
    return int(row["n"])
