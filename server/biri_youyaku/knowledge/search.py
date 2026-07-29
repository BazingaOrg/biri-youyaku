"""FTS5 search over active summary chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from biri_youyaku.db import connect
from biri_youyaku.knowledge.chunker import fts_prepare_text

# List cards: short preview; full chunk_text is always returned for expand.
_SNIPPET_MAX = 160


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


def _safe_token(token: str) -> str:
    return token.replace('"', '""')


def escape_fts_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression from user text.

    - Continuous query with no whitespace (e.g. 人名「张三」): FTS **phrase** so
      tokens must appear in order and adjacent. Avoids 「张三」 matching 「三张牌」
      (which only has 三 then 张 under character tokenization).
    - Multi-word queries: AND of quoted tokens (broader recall).
    """
    raw = (query or "").strip()
    prepared = fts_prepare_text(raw)
    if not prepared:
        return ""
    tokens: list[str] = []
    for part in prepared.split():
        token = part.strip()
        if not token or token in {"AND", "OR", "NOT", "NEAR"}:
            continue
        tokens.append(_safe_token(token))
    if not tokens:
        return ""
    if len(tokens) == 1:
        return f'"{tokens[0]}"'
    # No whitespace in original → one phrase (names, fixed terms, product ids).
    if not re.search(r"\s", raw):
        return f'"{" ".join(tokens)}"'
    return " ".join(f'"{t}"' for t in tokens)


def make_snippet(text: str, *, max_len: int = _SNIPPET_MAX) -> str:
    body = (text or "").strip()
    if len(body) <= max_len:
        return body
    return body[: max_len - 1].rstrip() + "…"


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
        JOIN knowledge_documents d ON d.id = c.document_id AND d.deleted_at IS NULL
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
        snippet = make_snippet(text)
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
        "locator": hit.heading_path,
    }
