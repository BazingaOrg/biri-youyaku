"""Document-aggregated library search (metadata LIKE + FTS, layered ranking)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs.model import JobStatus
from biri_youyaku.knowledge.search import escape_fts_query, make_snippet
from biri_youyaku.library.util import (
    CursorError,
    bvid_exact_match,
    decode_cursor,
    encode_cursor,
    like_contains,
    parse_tags,
)

SCOPES = frozenset({"all", "notes", "subs"})
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50
_HITS_PER_GROUP = 2


class SearchError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class _Hit:
    kind: str
    chunk_ord: int
    heading_path: str | None
    start_sec: float | None
    end_sec: float | None
    snippet: str


@dataclass
class _Group:
    key: str
    kind: str
    document_id: str | None
    job_id: str | None
    title: str | None
    author: str | None
    provider: str
    source_id: str | None
    source_part: str
    mid: Any
    bvid: str | None
    cid: Any
    source_url: str | None
    saved_at: int
    tags: list[str]
    tldr: str | None
    duration: Any
    legacy: bool
    legacy_reason: str | None
    match_title: bool = False
    match_author: bool = False
    match_bvid: bool = False
    match_source: bool = False
    match_tags: list[str] = field(default_factory=list)
    notes_hits: list[_Hit] = field(default_factory=list)
    subs_hits: list[_Hit] = field(default_factory=list)
    notes_count: int = 0
    subs_count: int = 0

    def sort_tuple(self) -> tuple:
        return (
            0 if self.match_bvid or self.match_source else 1,
            0 if self.match_title else 1,
            -self.notes_count,
            -self.subs_count,
            -(self.saved_at or 0),
            self.key,
        )


def search_library(
    *,
    q: str,
    scope: str = "all",
    cursor: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    query = (q or "").strip()
    if not query:
        raise SearchError("q 不能为空", status_code=400)
    scope_key = (scope or "all").strip() or "all"
    if scope_key not in SCOPES:
        raise SearchError("scope 必须是 all、notes 或 subs", status_code=400)
    page_size = _DEFAULT_LIMIT if limit is None else max(1, min(int(limit), _MAX_LIMIT))
    try:
        cursor_payload = decode_cursor(cursor)
    except CursorError as exc:
        raise SearchError("cursor 无效", status_code=400) from exc

    groups: dict[str, _Group] = {}
    partial: list[str] = []
    register_on = bool(settings.knowledge_register_enabled)
    want_notes = scope_key in {"all", "notes"}
    want_subs = scope_key in {"all", "subs"}
    include_legacy = scope_key in {"all", "notes"}
    include_meta = scope_key in {"all", "notes"} or not register_on

    if include_meta or scope_key == "subs":
        for row in _query_document_metadata(query, include_deleted=False):
            group = _group_from_document_row(row, query)
            groups[group.key] = group
        if include_legacy:
            for row in _query_legacy_job_metadata(query, register_on=register_on):
                group = _group_from_job_row(row, query)
                groups[group.key] = group

    notes_map: dict[str, dict[str, Any]] = {}
    subs_map: dict[str, dict[str, Any]] = {}
    match_expr = escape_fts_query(query)
    if register_on and match_expr:
        if want_notes:
            try:
                notes_map = query_notes_fts(match_expr, query)
            except Exception:
                partial.append("notes")
                notes_map = {}
        if want_subs:
            try:
                subs_map = query_subs_fts(match_expr, query)
            except Exception:
                partial.append("subs")
                subs_map = {}
    elif not register_on and want_subs:
        partial.append("subs")

    if scope_key == "subs" and "subs" in partial:
        for row in _query_document_metadata(query, include_deleted=False):
            key = f"d:{row['id']}"
            if key not in groups:
                groups[key] = _group_from_document_row(row, query)

    fts_ids = set(notes_map) | set(subs_map)
    missing_ids = [document_id for document_id in fts_ids if f"d:{document_id}" not in groups]
    if missing_ids:
        for row in _load_documents(missing_ids):
            group = _group_from_document_row(row, query)
            groups[group.key] = group

    for document_id, payload in notes_map.items():
        group = groups.get(f"d:{document_id}")
        if group is None:
            continue
        group.notes_hits = payload["hits"]
        group.notes_count = payload["count"]

    for document_id, payload in subs_map.items():
        group = groups.get(f"d:{document_id}")
        if group is None:
            continue
        group.subs_hits = payload["hits"]
        group.subs_count = payload["count"]

    ranked = list(groups.values())
    if scope_key == "subs":
        if "subs" in partial:
            ranked = [g for g in ranked if not g.legacy]
        else:
            ranked = [g for g in ranked if g.subs_count > 0]
    ranked.sort(key=lambda g: g.sort_tuple())

    start = 0
    if cursor_payload is not None:
        try:
            last_key = str(cursor_payload["id"])
            last_kind = str(cursor_payload.get("k", "d"))
        except (KeyError, TypeError, ValueError) as exc:
            raise SearchError("cursor 无效", status_code=400) from exc
        cursor_group_key = f"{'d' if last_kind == 'd' else 'j'}:{last_key}"
        found = False
        for index, group in enumerate(ranked):
            if group.key == cursor_group_key:
                start = index + 1
                found = True
                break
        if not found:
            last_tuple = (
                int(cursor_payload.get("b", 1)),
                int(cursor_payload.get("ti", 1)),
                -int(cursor_payload.get("n", 0)),
                -int(cursor_payload.get("s", 0)),
                -int(cursor_payload.get("at", 0)),
                cursor_group_key,
            )
            start = 0
            for index, group in enumerate(ranked):
                if group.sort_tuple() > last_tuple:
                    start = index
                    break
            else:
                start = len(ranked)

    page = ranked[start : start + page_size]
    next_cursor = None
    if start + page_size < len(ranked) and page:
        last = page[-1]
        next_cursor = encode_cursor(
            {
                "id": last.document_id or last.job_id,
                "k": "j" if last.legacy else "d",
                "b": 0 if last.match_bvid or last.match_source else 1,
                "ti": 0 if last.match_title else 1,
                "n": last.notes_count,
                "s": last.subs_count,
                "at": last.saved_at or 0,
            }
        )

    return {
        "ok": True,
        "query": query,
        "scope": scope_key,
        "partial": partial,
        "next_cursor": next_cursor,
        "groups": [_group_to_dict(group) for group in page],
    }


def _contains(haystack: str | None, needle: str) -> bool:
    if not haystack:
        return False
    return needle.casefold() in haystack.casefold()


def _apply_match(group: _Group, query: str) -> None:
    group.match_title = _contains(group.title, query)
    group.match_author = _contains(group.author, query)
    group.match_bvid = bvid_exact_match(query, group.bvid)
    group.match_source = bool(
        group.provider != "bilibili"
        and group.source_id
        and query.casefold() == group.source_id.casefold()
    )
    group.match_tags = [tag for tag in group.tags if _contains(tag, query)]


def _group_from_document_row(row: Any, query: str) -> _Group:
    group = _Group(
        key=f"d:{row['id']}",
        kind="document",
        document_id=row["id"],
        job_id=row["job_id"],
        title=row["title"],
        author=row["author"],
        provider=row["provider"],
        source_id=row["source_id"],
        source_part=row["source_part"],
        mid=row["mid"],
        bvid=row["bvid"],
        cid=row["cid"],
        source_url=row["source_url"],
        saved_at=int(row["saved_at"] or 0),
        tags=parse_tags(row["tags_json"]),
        tldr=row["tldr"],
        duration=row["duration"],
        legacy=False,
        legacy_reason=None,
    )
    _apply_match(group, query)
    return group


def _group_from_job_row(row: Any, query: str) -> _Group:
    reason = row["legacy_reason"]
    if not settings.knowledge_register_enabled and not reason:
        reason = "knowledge_register_disabled"
    group = _Group(
        key=f"j:{row['job_id']}",
        kind="legacy_job",
        document_id=None,
        job_id=row["job_id"],
        title=row["title"],
        author=row["author"],
        provider=row["provider"],
        source_id=row["source_id"],
        source_part=row["source_part"],
        mid=row["mid"],
        bvid=row["bvid"],
        cid=row["cid"],
        source_url=row["source_url"],
        saved_at=int(row["saved_at"] or 0),
        tags=parse_tags(row["tags_json"]),
        tldr=None,
        duration=row["duration"],
        legacy=True,
        legacy_reason=reason,
    )
    _apply_match(group, query)
    return group


def _load_documents(document_ids: list[str]) -> list[Any]:
    if not document_ids:
        return []
    placeholders = ",".join("?" for _ in document_ids)
    sql = f"""
        SELECT
          d.id AS id,
          d.title AS title,
          d.author AS author,
          d.provider AS provider,
          d.source_id AS source_id,
          d.source_part AS source_part,
          d.mid AS mid,
          d.external_bvid AS bvid,
          d.external_cid AS cid,
          d.duration AS duration,
          d.tags_json AS tags_json,
          d.tldr AS tldr,
          d.updated_at AS saved_at,
          d.source_url AS source_url,
          (
            SELECT l.job_id FROM knowledge_job_links l
            WHERE l.document_id = d.id AND l.unlinked_at IS NULL
            ORDER BY l.linked_at DESC LIMIT 1
          ) AS job_id
        FROM knowledge_documents d
        WHERE d.deleted_at IS NULL AND d.id IN ({placeholders})
    """
    with connect() as connection:
        return list(connection.execute(sql, document_ids).fetchall())


def _meta_like_clause(columns: list[str]) -> str:
    return " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in columns)


def _query_document_metadata(query: str, *, include_deleted: bool) -> list[Any]:
    pattern = like_contains(query)
    where = []
    if not include_deleted:
        where.append("d.deleted_at IS NULL")
    like_sql = _meta_like_clause(
        [
            "IFNULL(d.title, '')",
            "IFNULL(d.author, '')",
            "IFNULL(d.external_bvid, '')",
            "IFNULL(d.source_id, '')",
            "IFNULL(d.tags_json, '')",
        ]
    )
    where.append(f"({like_sql})")
    sql = f"""
        SELECT
          d.id AS id,
          d.title AS title,
          d.author AS author,
          d.provider AS provider,
          d.source_id AS source_id,
          d.source_part AS source_part,
          d.mid AS mid,
          d.external_bvid AS bvid,
          d.external_cid AS cid,
          d.duration AS duration,
          d.tags_json AS tags_json,
          d.tldr AS tldr,
          d.updated_at AS saved_at,
          d.source_url AS source_url,
          (
            SELECT l.job_id FROM knowledge_job_links l
            WHERE l.document_id = d.id AND l.unlinked_at IS NULL
            ORDER BY l.linked_at DESC LIMIT 1
          ) AS job_id
        FROM knowledge_documents d
        WHERE {' AND '.join(where)}
    """
    params = [pattern, pattern, pattern, pattern, pattern]
    with connect() as connection:
        return list(connection.execute(sql, params).fetchall())


def _query_legacy_job_metadata(query: str, *, register_on: bool) -> list[Any]:
    pattern = like_contains(query)
    where = [
        "j.status = ?",
        "IFNULL(j.summary_path, '') != ''",
        "IFNULL(r.status, '') != 'purged'",
    ]
    params: list[Any] = [JobStatus.COMPLETED.value]
    if register_on:
        where.append("l.job_id IS NULL")
    like_sql = _meta_like_clause(
        [
            "IFNULL(j.title, '')",
            "IFNULL(j.author, '')",
            "IFNULL(j.bvid, '')",
            "IFNULL(j.source_id, '')",
            "IFNULL(j.tags_json, '')",
        ]
    )
    where.append(f"({like_sql})")
    params.extend([pattern, pattern, pattern, pattern, pattern])
    sql = f"""
        SELECT
          j.id AS job_id,
          j.title AS title,
          j.author AS author,
          j.source_provider AS provider,
          j.source_id AS source_id,
          j.source_part AS source_part,
          j.mid AS mid,
          j.bvid AS bvid,
          j.cid AS cid,
          j.duration AS duration,
          j.tags_json AS tags_json,
          j.url AS source_url,
          COALESCE(j.completed_at, j.created_at) AS saved_at,
          r.reason AS legacy_reason
        FROM jobs j
        LEFT JOIN knowledge_job_links l ON l.job_id = j.id
        LEFT JOIN knowledge_reconcile r ON r.job_id = j.id
        WHERE {' AND '.join(where)}
    """
    with connect() as connection:
        return list(connection.execute(sql, params).fetchall())


def query_notes_fts(match_expr: str, query: str) -> dict[str, dict[str, Any]]:
    sql = """
        WITH matched AS (
          SELECT
            c.document_id AS document_id,
            c.chunk_ord AS chunk_ord,
            c.heading_path AS heading_path,
            c.start_sec AS start_sec,
            c.chunk_text AS chunk_text,
            COUNT(*) OVER (PARTITION BY c.document_id) AS hit_count,
            ROW_NUMBER() OVER (
              PARTITION BY c.document_id
              ORDER BY c.chunk_ord ASC
            ) AS rn
          FROM knowledge_rag_chunks_fts f
          JOIN knowledge_rag_chunks c ON c.id = f.chunk_id
          JOIN knowledge_documents d ON d.id = c.document_id AND d.deleted_at IS NULL
          JOIN knowledge_summary_revisions sr
            ON sr.id = c.summary_revision_id AND sr.is_active = 1
          WHERE knowledge_rag_chunks_fts MATCH ?
        )
        SELECT document_id, chunk_ord, heading_path, start_sec, chunk_text, hit_count
        FROM matched
        WHERE rn <= 2
    """
    with connect() as connection:
        rows = connection.execute(sql, (match_expr,)).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        document_id = row["document_id"]
        bucket = out.setdefault(document_id, {"count": int(row["hit_count"] or 0), "hits": []})
        bucket["hits"].append(
            _Hit(
                kind="notes",
                chunk_ord=int(row["chunk_ord"] or 0),
                heading_path=row["heading_path"],
                start_sec=row["start_sec"],
                end_sec=None,
                snippet=make_snippet(row["chunk_text"] or "", query=query),
            )
        )
    return out


def query_subs_fts(match_expr: str, query: str) -> dict[str, dict[str, Any]]:
    sql = """
        WITH matched AS (
          SELECT
            c.document_id AS document_id,
            c.chunk_ord AS chunk_ord,
            c.start_sec AS start_sec,
            c.end_sec AS end_sec,
            c.chunk_text AS chunk_text,
            COUNT(*) OVER (PARTITION BY c.document_id) AS hit_count,
            ROW_NUMBER() OVER (
              PARTITION BY c.document_id
              ORDER BY c.start_sec ASC, c.chunk_ord ASC
            ) AS rn
          FROM knowledge_transcript_chunks_fts f
          JOIN knowledge_transcript_chunks c ON c.id = f.chunk_id
          JOIN knowledge_documents d ON d.id = c.document_id AND d.deleted_at IS NULL
          WHERE knowledge_transcript_chunks_fts MATCH ?
        )
        SELECT document_id, chunk_ord, start_sec, end_sec, chunk_text, hit_count
        FROM matched
        WHERE rn <= 2
    """
    with connect() as connection:
        rows = connection.execute(sql, (match_expr,)).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        document_id = row["document_id"]
        bucket = out.setdefault(document_id, {"count": int(row["hit_count"] or 0), "hits": []})
        bucket["hits"].append(
            _Hit(
                kind="subs",
                chunk_ord=int(row["chunk_ord"] or 0),
                heading_path=None,
                start_sec=row["start_sec"],
                end_sec=row["end_sec"],
                snippet=make_snippet(row["chunk_text"] or "", query=query),
            )
        )
    return out


def _group_to_dict(group: _Group) -> dict[str, Any]:
    notes_take = group.notes_hits[:_HITS_PER_GROUP]
    remaining = _HITS_PER_GROUP - len(notes_take)
    subs_take = group.subs_hits[: max(0, remaining)]
    hits = notes_take + subs_take
    more = (group.notes_count > len(notes_take)) or (group.subs_count > len(subs_take))
    return {
        "document_id": group.document_id,
        "job_id": group.job_id,
        "title": group.title,
        "author": group.author,
        "provider": group.provider,
        "source_id": group.source_id,
        "source_part": group.source_part,
        "mid": group.mid,
        "bvid": group.bvid,
        "cid": group.cid,
        "source_url": group.source_url,
        "saved_at": group.saved_at,
        "tags": group.tags,
        "tldr": group.tldr,
        "duration": group.duration,
        "legacy": group.legacy,
        "legacy_reason": group.legacy_reason,
        "match": {
            "title": group.match_title,
            "author": group.match_author,
            "bvid": group.match_bvid,
            "source_id": group.match_source,
            "tags": group.match_tags,
        },
        "hits": [
            {
                "kind": hit.kind,
                "chunk_ord": hit.chunk_ord,
                "heading_path": hit.heading_path,
                "start_sec": hit.start_sec,
                "end_sec": hit.end_sec,
                "snippet": hit.snippet,
            }
            for hit in hits
        ],
        "hit_counts": {"notes": group.notes_count, "subs": group.subs_count},
        "more": more,
    }
