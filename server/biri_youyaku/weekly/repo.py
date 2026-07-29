from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import Job, JobStatus


WEEKLY_STATUSES = frozenset({"MISSING", "EMPTY", "GENERATING", "COMPLETED", "FAILED", "STALE"})


@dataclass(frozen=True)
class WeeklySummary:
    week_start: str
    week_end: str
    timezone: str
    status: str
    content: str | None
    references: list[dict]
    sources_fingerprint: str | None
    error: str | None
    generated_at: int | None
    updated_at: int | None
    generation_token: str | None
    generation_expires_at: int | None


def _zone() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "weekly_summary_timezone", "Asia/Shanghai"))


def week_bounds(week_start: str) -> tuple[int, int, str]:
    """Return local-Monday [start, next start) milliseconds and normalized end date."""
    start = date.fromisoformat(week_start)
    if start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    zone = _zone()
    start_at = datetime(start.year, start.month, start.day, tzinfo=zone)
    end_at = start_at + timedelta(days=7)
    return (
        int(start_at.timestamp() * 1000),
        int(end_at.timestamp() * 1000),
        end_at.date().isoformat(),
    )


def current_week_start() -> str:
    today = datetime.now(_zone()).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def _job_week_at(job: Job) -> int:
    return job.completed_at or job.created_at


def sources_for_week(week_start: str, *, connection=None) -> list[Job]:
    start_ms, end_ms, _ = week_bounds(week_start)
    # Summary files are intentionally verified below: a stale path must not become an LLM source.
    if connection is None:
        with connect() as read_connection:
            rows = read_connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                  AND json_extract(effective_options_json, '$.task_type') IS NOT 'distill'
                  AND COALESCE(completed_at, created_at) >= ?
                  AND COALESCE(completed_at, created_at) < ?
                ORDER BY COALESCE(completed_at, created_at), id
                """,
                (JobStatus.COMPLETED.value, start_ms, end_ms),
            ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM jobs
            WHERE status = ?
              AND json_extract(effective_options_json, '$.task_type') IS NOT 'distill'
              AND COALESCE(completed_at, created_at) >= ?
              AND COALESCE(completed_at, created_at) < ?
            ORDER BY COALESCE(completed_at, created_at), id
            """,
            (JobStatus.COMPLETED.value, start_ms, end_ms),
        ).fetchall()
    jobs = [jobs_repo._row_to_job(row) for row in rows]
    return [job for job in jobs if job.summary_path and jobs_repo.read_summary(job)]


def fingerprint(sources: list[Job]) -> str:
    source_rows = []
    for job in sources:
        # Include body identity so a re-summarized source marks the cached weekly result stale.
        body = jobs_repo.read_summary(job) or ""
        source_rows.append(
            (job.id, job.completed_at or job.created_at, hashlib.sha256(body.encode()).hexdigest())
        )
    raw = json.dumps(source_rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def get(week_start: str) -> WeeklySummary | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM weekly_summaries WHERE week_start = ?", (week_start,)
        ).fetchone()
    if row is None:
        return None
    return WeeklySummary(
        week_start=row["week_start"],
        week_end=row["week_end"],
        timezone=row["timezone"],
        status=row["status"],
        content=row["content"],
        references=json.loads(row["references_json"] or "[]"),
        sources_fingerprint=row["sources_fingerprint"],
        error=row["error"],
        generated_at=row["generated_at"],
        updated_at=row["updated_at"],
        generation_token=row["generation_token"],
        generation_expires_at=row["generation_expires_at"],
    )


def statuses_for_weeks(week_starts: list[str]) -> dict[str, str]:
    """Return persisted weekly-summary status per Monday date (YYYY-MM-DD).

    Weeks with no row are reported as MISSING. Does not recompute staleness
    against live sources — navigator only needs a cheap glance map.
    """
    if not week_starts:
        return {}
    result = {week_start: "MISSING" for week_start in week_starts}
    with connect() as connection:
        if not _source_tables_exist(connection):
            return result
        placeholders = ",".join("?" for _ in week_starts)
        rows = connection.execute(
            f"SELECT week_start, status FROM weekly_summaries WHERE week_start IN ({placeholders})",
            week_starts,
        ).fetchall()
    for row in rows:
        status = str(row["status"] or "MISSING")
        if status in WEEKLY_STATUSES:
            result[str(row["week_start"])] = status
    return result


def generation_lease_ms() -> int:
    """Longer than all configured LLM attempts, with a small scheduler margin."""
    attempts = max(1, settings.llm_max_retries + 1)
    return max(60_000, (settings.llm_timeout_seconds * attempts + 60) * 1000)


def generation_expired(stored: WeeklySummary, *, now: int | None = None) -> bool:
    return stored.status == "GENERATING" and (stored.generation_expires_at or 0) <= (
        jobs_repo.now_ms() if now is None else now
    )


def renew_generation_lease(week_start: str, generation_token: str) -> bool:
    now = jobs_repo.now_ms()
    with connect() as connection:
        cursor = connection.execute(
            """UPDATE weekly_summaries SET generation_expires_at=?, updated_at=?
               WHERE week_start=? AND status='GENERATING' AND generation_token=?""",
            (now + generation_lease_ms(), now, week_start, generation_token),
        )
    return cursor.rowcount == 1


def state_for_week(week_start: str) -> tuple[WeeklySummary | None, list[Job], str]:
    stored = get(week_start)
    sources = sources_for_week(week_start)
    source_fingerprint = fingerprint(sources)
    if stored and generation_expired(stored):
        mark_stale(week_start, generation_token=stored.generation_token)
        stored = get(week_start)
    if (
        stored
        and stored.status in {"COMPLETED", "EMPTY"}
        and stored.sources_fingerprint != source_fingerprint
    ):
        mark_stale(week_start)
        stored = get(week_start)
    return stored, sources, source_fingerprint


def begin_generation(
    week_start: str,
    *,
    fingerprint_value: str,
    generation_token: str | None = None,
    sources: list[Job] | None = None,
) -> bool:
    _, _, week_end = week_bounds(week_start)
    now = jobs_repo.now_ms()
    expires_at = now + generation_lease_ms()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO weekly_summaries (week_start, week_end, timezone, status, sources_fingerprint, generation_token, generation_expires_at, created_at, updated_at)
            VALUES (?, ?, ?, 'GENERATING', ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET status='GENERATING', sources_fingerprint=excluded.sources_fingerprint,
              generation_token=excluded.generation_token, generation_expires_at=excluded.generation_expires_at,
              content=NULL, references_json=NULL, error=NULL, updated_at=excluded.updated_at
            WHERE weekly_summaries.status != 'GENERATING'
               OR COALESCE(weekly_summaries.generation_expires_at, 0) <= ?
            """,
            (
                week_start,
                week_end,
                str(_zone()),
                fingerprint_value,
                generation_token,
                expires_at,
                now,
                now,
                now,
            ),
        )
        if cursor.rowcount == 1:
            connection.execute(
                "DELETE FROM weekly_summary_sources WHERE week_start = ?", (week_start,)
            )
            connection.executemany(
                "INSERT INTO weekly_summary_sources (week_start, job_id) VALUES (?, ?)",
                [(week_start, job.id) for job in sources or []],
            )
    return cursor.rowcount == 1


def save_empty(week_start: str, *, fingerprint_value: str) -> None:
    _, _, week_end = week_bounds(week_start)
    now = jobs_repo.now_ms()
    with connect() as connection:
        connection.execute(
            """INSERT INTO weekly_summaries (week_start, week_end, timezone, status, sources_fingerprint, created_at, updated_at)
               VALUES (?, ?, ?, 'EMPTY', ?, ?, ?)
               ON CONFLICT(week_start) DO UPDATE SET status='EMPTY', content=NULL, references_json=NULL, generation_token=NULL, generation_expires_at=NULL,
                 sources_fingerprint=excluded.sources_fingerprint, error=NULL, updated_at=excluded.updated_at""",
            (week_start, week_end, str(_zone()), fingerprint_value, now, now),
        )


def save_completed(
    week_start: str,
    *,
    fingerprint_value: str,
    sources: list[Job],
    content: str,
    references: list[dict],
    generation_token: str | None = None,
) -> bool:
    now = jobs_repo.now_ms()
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        current_sources = sources_for_week(week_start, connection=connection)
        if fingerprint(current_sources) != fingerprint_value:
            connection.execute(
                """UPDATE weekly_summaries SET status='STALE', content=NULL, references_json=NULL,
                   generation_token=NULL, generation_expires_at=NULL, error=NULL, updated_at=?
                   WHERE week_start=? AND status='GENERATING' AND (? IS NULL OR generation_token=?)""",
                (now, week_start, generation_token, generation_token),
            )
            connection.commit()
            return False
        cursor = connection.execute(
            """UPDATE weekly_summaries SET status='COMPLETED', content=?, references_json=?, sources_fingerprint=?,
                 generation_token=NULL, generation_expires_at=NULL, error=NULL, generated_at=?, updated_at=? WHERE week_start=?
                 AND status='GENERATING' AND (? IS NULL OR generation_token=?)""",
            (
                content,
                json.dumps(references, ensure_ascii=False),
                fingerprint_value,
                now,
                now,
                week_start,
                generation_token,
                generation_token,
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return False
        connection.execute("DELETE FROM weekly_summary_sources WHERE week_start = ?", (week_start,))
        connection.executemany(
            "INSERT INTO weekly_summary_sources (week_start, job_id) VALUES (?, ?)",
            [(week_start, job.id) for job in current_sources],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return True


def save_failed(week_start: str, error: str, *, generation_token: str | None = None) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            """UPDATE weekly_summaries SET status='FAILED', generation_token=NULL, generation_expires_at=NULL, error=?, updated_at=?
               WHERE week_start=? AND status='GENERATING' AND (? IS NULL OR generation_token=?)""",
            (error[:1000], jobs_repo.now_ms(), week_start, generation_token, generation_token),
        )
    return cursor.rowcount == 1


def mark_stale(week_start: str, *, generation_token: str | None = None) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            """UPDATE weekly_summaries SET status='STALE', content=NULL, references_json=NULL,
               generation_token=NULL, generation_expires_at=NULL, error=NULL, updated_at=? WHERE week_start=?
               AND (? IS NULL OR (status='GENERATING' AND generation_token IS ?))""",
            (jobs_repo.now_ms(), week_start, generation_token, generation_token),
        )
    return cursor.rowcount == 1


def delete(week_start: str) -> bool:
    """Remove the persisted weekly summary and its source links for one week.

    Does not touch underlying video jobs. Returns False when no row existed.
    """
    with connect() as connection:
        if not _source_tables_exist(connection):
            return False
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                "DELETE FROM weekly_summaries WHERE week_start = ?", (week_start,)
            )
            connection.execute(
                "DELETE FROM weekly_summary_sources WHERE week_start = ?", (week_start,)
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return cursor.rowcount > 0


def _source_tables_exist(connection) -> bool:
    """Older databases and narrow route tests can predate the weekly-summary migration."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('weekly_summaries', 'weekly_summary_sources')"
    ).fetchall()
    return {row["name"] for row in rows} == {"weekly_summaries", "weekly_summary_sources"}


def mark_stale_for_job_ids(job_ids: list[str], *, connection=None) -> int:
    if not job_ids:
        return 0
    placeholders = ",".join("?" for _ in job_ids)
    statement = f"""UPDATE weekly_summaries SET status='STALE', content=NULL, references_json=NULL, error=NULL, updated_at=?
        WHERE week_start IN
        (SELECT DISTINCT week_start FROM weekly_summary_sources WHERE job_id IN ({placeholders}))"""
    if connection is None:
        with connect() as write_connection:
            if not _source_tables_exist(write_connection):
                return 0
            cursor = write_connection.execute(statement, [jobs_repo.now_ms(), *job_ids])
            return cursor.rowcount
    if not _source_tables_exist(connection):
        return 0
    cursor = connection.execute(statement, [jobs_repo.now_ms(), *job_ids])
    return cursor.rowcount


def affected_count_for_job_ids(job_ids: list[str]) -> int:
    return len(affected_week_starts_for_job_ids(job_ids))


def affected_week_starts_for_job_ids(job_ids: list[str], *, connection=None) -> list[str]:
    """Return the stable, complete weekly-summary scope affected by source deletion."""
    if not job_ids:
        return []
    placeholders = ",".join("?" for _ in job_ids)
    statement = f"""SELECT DISTINCT week_start FROM weekly_summary_sources
        WHERE job_id IN ({placeholders}) ORDER BY week_start"""
    if connection is None:
        with connect() as read_connection:
            if not _source_tables_exist(read_connection):
                return []
            rows = read_connection.execute(statement, job_ids).fetchall()
    else:
        if not _source_tables_exist(connection):
            return []
        rows = connection.execute(statement, job_ids).fetchall()
    return [str(row["week_start"]) for row in rows]
