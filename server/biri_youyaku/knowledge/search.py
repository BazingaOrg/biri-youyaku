"""FTS5 search over active summary chunks."""

from __future__ import annotations

from dataclasses import dataclass

from biri_youyaku.db import connect
from biri_youyaku.knowledge.chunker import fts_prepare_text


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document_id: str
    summary_revision_id: str
    title: str | None
    author: str | None
    bvid: str | None
    source_url: str | None
    heading_path: str
    chunk_text: str
    snippet: str
    score: float


def escape_fts_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression from user text.

    Uses phrase-ish AND of tokens; strips empty; empty input → empty string.
    """
    prepared = fts_prepare_text(query or "").strip()
    if not prepared:
        return ""
    # Split on whitespace; each token quoted with " and internal " doubled.
    tokens: list[str] = []
    for raw in prepared.split():
        token = raw.strip()
        if not token:
            continue
        # Drop pure operator-ish tokens.
        if token in {"AND", "OR", "NOT", "NEAR"}:
            continue
        safe = token.replace('"', '""')
        tokens.append(f'"{safe}"')
    return " ".join(tokens)


def search_summaries(query: str, *, limit: int = 10) -> list[Hit]:
    """FTS search; empty/invalid query → empty list."""
    limit = max(1, min(int(limit or 10), 50))
    match_expr = escape_fts_query(query)
    if not match_expr:
        return []

    # Restrict to chunks whose summary_revision is still active.
    sql = """
        SELECT
          c.id AS chunk_id,
          c.document_id AS document_id,
          c.summary_revision_id AS summary_revision_id,
          c.heading_path AS heading_path,
          c.chunk_text AS chunk_text,
          d.title AS title,
          d.author AS author,
          d.external_bvid AS bvid,
          d.source_url AS source_url,
          bm25(knowledge_rag_chunks_fts) AS score
        FROM knowledge_rag_chunks_fts f
        JOIN knowledge_rag_chunks c ON c.id = f.chunk_id
        JOIN knowledge_documents d ON d.id = c.document_id
        JOIN knowledge_summary_revisions sr
          ON sr.id = c.summary_revision_id AND sr.is_active = 1
        WHERE knowledge_rag_chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
    """
    try:
        with connect() as connection:
            rows = connection.execute(sql, (match_expr, limit)).fetchall()
    except Exception:
        # Malformed MATCH etc. — soft-fail to empty.
        return []

    hits: list[Hit] = []
    for row in rows:
        text = row["chunk_text"] or ""
        snippet = text if len(text) <= 280 else text[:277] + "…"
        hits.append(
            Hit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                summary_revision_id=row["summary_revision_id"],
                title=row["title"],
                author=row["author"],
                bvid=row["bvid"],
                source_url=row["source_url"],
                heading_path=row["heading_path"],
                chunk_text=text,
                snippet=snippet,
                score=float(row["score"] if row["score"] is not None else 0.0),
            )
        )
    return hits


def hit_to_dict(hit: Hit) -> dict:
    return {
        "chunk_id": hit.chunk_id,
        "document_id": hit.document_id,
        "summary_revision_id": hit.summary_revision_id,
        "title": hit.title,
        "author": hit.author,
        "bvid": hit.bvid,
        "source_url": hit.source_url,
        "heading_path": hit.heading_path,
        "snippet": hit.snippet,
        "chunk_text": hit.chunk_text,
        "score": hit.score,
        "source_level": "summary",
    }
