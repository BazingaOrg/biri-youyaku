"""Layered retrieval: summary discovery → transcript evidence (Phase C)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.knowledge.search import (
    Hit,
    escape_fts_query,
    make_snippet,
    search_summaries,
)

# Query heuristics for transcript evidence need / global fallback.
_DIGIT_RE = re.compile(r"\d")
_QUOTE_RE = re.compile(r'[「」『』""\'\'`]|“|”|‘|’')
_TIME_HINT_RE = re.compile(
    r"几点|几分|分钟|秒钟|多少秒|多少分|时间点|时间戳|第\s*\d+\s*[分秒]"
)
_COMMAND_HINT_RE = re.compile(
    r"(?i)\b(npm|npx|pip|uv|git|curl|wget|docker|kubectl|python|node|bash|zsh|"
    r"sudo|chmod|chown|export|source|brew|apt|yum|cargo|go\s+run|make)\b|"
    r"[\$#]\s*\w+|`[^`]+`"
)

_DEFAULT_SUMMARY_TOP = 8
_DEFAULT_TRANSCRIPT_LOCAL = 12
_DEFAULT_TRANSCRIPT_GLOBAL = 8
_MAX_SUMMARY_HITS = 6
_MAX_TRANSCRIPT_PER_DOC = 3
_MAX_TOTAL = 12


@dataclass(frozen=True)
class EvidenceHit:
    chunk_id: str
    document_id: str
    source_level: str  # summary | transcript
    title: str | None
    author: str | None
    bvid: str | None
    source_url: str | None
    heading_path: str | None
    start_sec: float | None
    end_sec: float | None
    subtitle_source: str | None
    chunk_text: str
    snippet: str
    score: float
    locator: str
    summary_revision_id: str | None = None
    content_revision_id: str | None = None
    chunk_ord: int | None = None


def format_mmss(sec: float) -> str:
    """Format seconds as mm:ss (non-negative; floor to whole seconds)."""
    total = max(0, int(sec))
    minutes, seconds = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def transcript_locator(start_sec: float, end_sec: float) -> str:
    return f"转写：{format_mmss(start_sec)}–{format_mmss(end_sec)}"


def query_needs_transcript_evidence(query: str, *, summary_hit_count: int = 0) -> bool:
    """True when query looks factual/numeric or summary recall is weak."""
    q = (query or "").strip()
    if not q:
        return False
    if summary_hit_count < 2:
        return True
    if _DIGIT_RE.search(q):
        return True
    if _QUOTE_RE.search(q):
        return True
    if _TIME_HINT_RE.search(q):
        return True
    if _COMMAND_HINT_RE.search(q):
        return True
    return False


def _summary_to_evidence(hit: Hit) -> EvidenceHit:
    return EvidenceHit(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        source_level="summary",
        title=hit.title,
        author=hit.author,
        bvid=hit.bvid,
        source_url=hit.source_url,
        heading_path=hit.heading_path,
        start_sec=None,
        end_sec=None,
        subtitle_source=None,
        chunk_text=hit.chunk_text,
        snippet=hit.snippet,
        score=hit.score,
        locator=hit.heading_path,
        summary_revision_id=hit.summary_revision_id,
        content_revision_id=None,
        chunk_ord=None,
    )


def _search_transcripts(
    query: str,
    *,
    limit: int = 10,
    document_ids: list[str] | None = None,
) -> list[EvidenceHit]:
    if not settings.knowledge_transcript_index_enabled:
        return []
    limit = max(1, min(int(limit or 10), 50))
    match_expr = escape_fts_query(query)
    if not match_expr:
        return []

    params: list[object] = [match_expr]
    doc_filter = ""
    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        doc_filter = f" AND c.document_id IN ({placeholders})"
        params.extend(document_ids)
    params.append(limit)

    sql = f"""
        SELECT
          c.id AS chunk_id,
          c.document_id AS document_id,
          c.content_revision_id AS content_revision_id,
          c.start_sec AS start_sec,
          c.end_sec AS end_sec,
          c.subtitle_source AS subtitle_source,
          c.chunk_text AS chunk_text,
          c.chunk_ord AS chunk_ord,
          d.title AS title,
          d.author AS author,
          d.external_bvid AS bvid,
          d.source_url AS source_url,
          bm25(knowledge_transcript_chunks_fts) AS score
        FROM knowledge_transcript_chunks_fts f
        JOIN knowledge_transcript_chunks c ON c.id = f.chunk_id
        JOIN knowledge_documents d ON d.id = c.document_id AND d.deleted_at IS NULL
        WHERE knowledge_transcript_chunks_fts MATCH ?
        {doc_filter}
        ORDER BY score
        LIMIT ?
    """
    try:
        with connect() as connection:
            rows = connection.execute(sql, params).fetchall()
    except Exception:
        return []

    hits: list[EvidenceHit] = []
    for row in rows:
        text = row["chunk_text"] or ""
        start = float(row["start_sec"] if row["start_sec"] is not None else 0.0)
        end = float(row["end_sec"] if row["end_sec"] is not None else start)
        locator = transcript_locator(start, end)
        hits.append(
            EvidenceHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                source_level="transcript",
                title=row["title"],
                author=row["author"],
                bvid=row["bvid"],
                source_url=row["source_url"],
                heading_path=None,
                start_sec=start,
                end_sec=end,
                subtitle_source=row["subtitle_source"],
                chunk_text=text,
                snippet=make_snippet(text),
                score=float(row["score"] if row["score"] is not None else 0.0),
                locator=locator,
                summary_revision_id=None,
                content_revision_id=row["content_revision_id"],
                chunk_ord=int(row["chunk_ord"]) if row["chunk_ord"] is not None else None,
            )
        )
    return hits


def _load_adjacent_transcript_chunks(
    hits: list[EvidenceHit],
    *,
    per_doc_cap: int = _MAX_TRANSCRIPT_PER_DOC,
) -> list[EvidenceHit]:
    """Expand ±1 chunk_ord per hit within same document/revision; respect cap."""
    if not hits:
        return []

    by_key: dict[tuple[str, str], list[EvidenceHit]] = {}
    for hit in hits:
        if hit.source_level != "transcript" or hit.content_revision_id is None:
            continue
        key = (hit.document_id, hit.content_revision_id)
        by_key.setdefault(key, []).append(hit)

    expanded: list[EvidenceHit] = []
    seen_ids: set[str] = set()

    for (document_id, content_revision_id), group in by_key.items():
        ords: set[int] = set()
        for hit in group:
            if hit.chunk_ord is None:
                continue
            ords.add(hit.chunk_ord)
            ords.add(hit.chunk_ord - 1)
            ords.add(hit.chunk_ord + 1)
        ords = {o for o in ords if o >= 0}
        if not ords:
            for hit in group:
                if hit.chunk_id not in seen_ids:
                    expanded.append(hit)
                    seen_ids.add(hit.chunk_id)
            continue

        placeholders = ",".join("?" for _ in ords)
        sql = f"""
            SELECT
              c.id AS chunk_id,
              c.document_id AS document_id,
              c.content_revision_id AS content_revision_id,
              c.start_sec AS start_sec,
              c.end_sec AS end_sec,
              c.subtitle_source AS subtitle_source,
              c.chunk_text AS chunk_text,
              c.chunk_ord AS chunk_ord,
              d.title AS title,
              d.author AS author,
              d.external_bvid AS bvid,
              d.source_url AS source_url
            FROM knowledge_transcript_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id AND d.deleted_at IS NULL
            WHERE c.document_id = ?
              AND c.content_revision_id = ?
              AND c.chunk_ord IN ({placeholders})
            ORDER BY c.chunk_ord
        """
        params: list[object] = [document_id, content_revision_id, *sorted(ords)]
        try:
            with connect() as connection:
                rows = connection.execute(sql, params).fetchall()
        except Exception:
            rows = []

        # Prefer original match order; fill with neighbors by ord.
        matched_ids = {h.chunk_id for h in group}
        primary: list[EvidenceHit] = []
        neighbors: list[EvidenceHit] = []
        for row in rows:
            start = float(row["start_sec"] if row["start_sec"] is not None else 0.0)
            end = float(row["end_sec"] if row["end_sec"] is not None else start)
            text = row["chunk_text"] or ""
            eh = EvidenceHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                source_level="transcript",
                title=row["title"],
                author=row["author"],
                bvid=row["bvid"],
                source_url=row["source_url"],
                heading_path=None,
                start_sec=start,
                end_sec=end,
                subtitle_source=row["subtitle_source"],
                chunk_text=text,
                snippet=make_snippet(text),
                score=0.0,
                locator=transcript_locator(start, end),
                summary_revision_id=None,
                content_revision_id=row["content_revision_id"],
                chunk_ord=int(row["chunk_ord"]) if row["chunk_ord"] is not None else None,
            )
            if eh.chunk_id in matched_ids:
                # Keep best score from original hit when available.
                orig = next((h for h in group if h.chunk_id == eh.chunk_id), None)
                if orig is not None:
                    eh = EvidenceHit(
                        chunk_id=eh.chunk_id,
                        document_id=eh.document_id,
                        source_level=eh.source_level,
                        title=eh.title,
                        author=eh.author,
                        bvid=eh.bvid,
                        source_url=eh.source_url,
                        heading_path=eh.heading_path,
                        start_sec=eh.start_sec,
                        end_sec=eh.end_sec,
                        subtitle_source=eh.subtitle_source,
                        chunk_text=eh.chunk_text,
                        snippet=eh.snippet,
                        score=orig.score,
                        locator=eh.locator,
                        summary_revision_id=None,
                        content_revision_id=eh.content_revision_id,
                        chunk_ord=eh.chunk_ord,
                    )
                primary.append(eh)
            else:
                neighbors.append(eh)

        doc_hits: list[EvidenceHit] = []
        for eh in primary + neighbors:
            if eh.chunk_id in seen_ids:
                continue
            doc_hits.append(eh)
            seen_ids.add(eh.chunk_id)
            if len(doc_hits) >= per_doc_cap:
                break
        expanded.extend(doc_hits)

    return expanded


def retrieve(
    query: str,
    *,
    mode: str = "search",
    limit: int = 10,
) -> list[EvidenceHit]:
    """Layered: summary discovery → local transcript → optional global fallback.

    Caps: up to 6 summary, 3 transcript per doc, total ``limit`` (default 12 max 12).
    """
    q = (query or "").strip()
    if not q:
        return []

    total_limit = max(1, min(int(limit or 10), _MAX_TOTAL))
    summary_top = _DEFAULT_SUMMARY_TOP if mode == "search" else max(6, total_limit)

    summary_hits = search_summaries(q, limit=summary_top)
    candidate_doc_ids: list[str] = []
    seen_docs: set[str] = set()
    for hit in summary_hits:
        if hit.document_id not in seen_docs:
            seen_docs.add(hit.document_id)
            candidate_doc_ids.append(hit.document_id)

    need_global = query_needs_transcript_evidence(
        q, summary_hit_count=len(summary_hits)
    )

    local_transcript: list[EvidenceHit] = []
    if candidate_doc_ids and settings.knowledge_transcript_index_enabled:
        local_transcript = _search_transcripts(
            q,
            limit=_DEFAULT_TRANSCRIPT_LOCAL,
            document_ids=candidate_doc_ids,
        )

    global_transcript: list[EvidenceHit] = []
    if need_global and settings.knowledge_transcript_index_enabled:
        global_transcript = _search_transcripts(
            q,
            limit=_DEFAULT_TRANSCRIPT_GLOBAL,
            document_ids=None,
        )

    # Prefer local; add global not already covered by chunk_id or same window.
    transcript_pool: list[EvidenceHit] = []
    seen_chunk: set[str] = set()
    for hit in local_transcript + global_transcript:
        if hit.chunk_id in seen_chunk:
            continue
        seen_chunk.add(hit.chunk_id)
        transcript_pool.append(hit)

    expanded = _load_adjacent_transcript_chunks(
        transcript_pool, per_doc_cap=_MAX_TRANSCRIPT_PER_DOC
    )

    # Merge with caps: summary first (discovery), then transcript evidence.
    # When evidence exists, reserve one slot for it so summary discovery cannot
    # crowd it out at the public API's small default limits.
    summary_budget = _MAX_SUMMARY_HITS
    if expanded:
        summary_budget = min(summary_budget, total_limit - 1)

    result: list[EvidenceHit] = []
    seen_final: set[str] = set()
    summary_count = 0
    for hit in summary_hits:
        if summary_count >= summary_budget:
            break
        if hit.chunk_id in seen_final:
            continue
        eh = _summary_to_evidence(hit)
        result.append(eh)
        seen_final.add(eh.chunk_id)
        summary_count += 1
        if len(result) >= total_limit:
            return result

    # Cap transcript already applied per-doc in expand; still enforce total.
    for hit in expanded:
        if hit.chunk_id in seen_final:
            continue
        result.append(hit)
        seen_final.add(hit.chunk_id)
        if len(result) >= total_limit:
            break

    return result


def evidence_hit_to_dict(hit: EvidenceHit) -> dict:
    """API shape: backward-compatible summary fields + optional transcript fields."""
    out: dict = {
        "chunk_id": hit.chunk_id,
        "document_id": hit.document_id,
        "summary_revision_id": hit.summary_revision_id or "",
        "title": hit.title,
        "author": hit.author,
        "bvid": hit.bvid,
        "source_url": hit.source_url,
        "heading_path": hit.heading_path or hit.locator,
        "snippet": hit.snippet,
        "chunk_text": hit.chunk_text,
        "score": hit.score,
        "source_level": hit.source_level,
        "locator": hit.locator,
    }
    if hit.start_sec is not None:
        out["start_sec"] = hit.start_sec
    if hit.end_sec is not None:
        out["end_sec"] = hit.end_sec
    if hit.subtitle_source is not None:
        out["subtitle_source"] = hit.subtitle_source
    if hit.content_revision_id is not None:
        out["content_revision_id"] = hit.content_revision_id
    return out
