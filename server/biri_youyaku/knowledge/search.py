"""FTS5 search over active summary chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from biri_youyaku.db import connect

# List cards: short preview; full chunk_text is always returned for expand.
_SNIPPET_MAX = 160
_QUERY_TOKEN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[^\W_]+", re.UNICODE)
_MATCH_SEPARATOR = r"[\W_]*"
_FTS_OPERATORS = frozenset({"AND", "OR", "NOT", "NEAR"})


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


def _query_token_groups(query: str) -> list[list[str]]:
    raw = (query or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s+", raw) if re.search(r"\s", raw) else [raw]
    groups: list[list[str]] = []
    for part in parts:
        tokens = [token for token in _QUERY_TOKEN_RE.findall(part) if token not in _FTS_OPERATORS]
        if tokens:
            groups.append(tokens)
    return groups


def _query_match_patterns(query: str) -> list[re.Pattern[str]]:
    return [
        re.compile(_MATCH_SEPARATOR.join(re.escape(token) for token in group), re.IGNORECASE)
        for group in _query_token_groups(query)
    ]


def escape_fts_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression from user text.

    - Continuous query with no whitespace (e.g. 人名「张三」): FTS **phrase** so
      tokens must appear in order and adjacent. Avoids 「张三」 matching 「三张牌」
      (which only has 三 then 张 under character tokenization).
    - Multi-word queries: AND of quoted tokens (broader recall).
    """
    raw = (query or "").strip()
    groups = _query_token_groups(raw)
    if not groups:
        return ""
    return " ".join(f'"{" ".join(_safe_token(token) for token in group)}"' for group in groups)


def make_snippet(text: str, *, query: str = "", max_len: int = _SNIPPET_MAX) -> str:
    body = (text or "").strip()
    if len(body) <= max_len:
        return body
    matches = [match.start() for pattern in _query_match_patterns(query) if (match := pattern.search(body))]
    if not matches:
        return body[: max_len - 1].rstrip() + "…"
    match_at = min(matches)
    start = max(0, match_at - max_len // 3)
    end = min(len(body), start + max_len)
    start = max(0, end - max_len)
    snippet = body[start:end].strip()
    return f"{'…' if start else ''}{snippet}{'…' if end < len(body) else ''}"


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
        snippet = make_snippet(text, query=query)
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
