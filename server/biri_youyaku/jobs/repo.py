import json
import time
import uuid
from pathlib import Path
from typing import Any, Collection, Iterable

from biri_youyaku.db import connect
from biri_youyaku.jobs.model import (
    BULK_DELETE_JOB_STATUSES,
    Job,
    JobOptions,
    JobStatus,
    PAUSED_OR_TERMINAL_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
)
from biri_youyaku.modules.bilibili.meta import Chapter, canonical_video_url
from biri_youyaku.modules.transcript import TranscriptItem


def now_ms() -> int:
    return int(time.time() * 1000)


# 列表 / 抽屉 / 清理用的 lite 投影：不拉 `chapters_json` / `transcript_json` /
# `stage_timings_json` 这种长 JSON 字段，30 条一拉从十几兆降到几十 KB。
_LITE_COLUMNS = (
    "id, url, bvid, cid, mid, title, author, duration, status, "
    "error_stage, error_message, error_code, audio_path, "
    "subtitle_source, summary_path, options_json, effective_options_json, "
    "created_at, updated_at, completed_at, stream_finished_at, "
    "token_usage_json, email_error, tags_json"
)


def _opt_col(row: Any, key: str) -> Any:
    """旧库可能缺新增列（如 error_code / token_usage_json）。lite 投影里没投也走这里。"""
    return row[key] if key in row.keys() else None


def _opt_json(row: Any, key: str) -> Any:
    raw = _opt_col(row, key)
    return json.loads(raw) if raw else None


def _status_filter(statuses: Iterable[JobStatus]) -> tuple[str, list[str]]:
    values = [status.value for status in sorted(statuses, key=lambda status: status.value)]
    return ",".join("?" for _ in values), values


def _row_to_job(row: Any, *, lite: bool = False) -> Job:
    """把 SQLite Row 拼成 Job。

    - lite=True：列表 / 抽屉用，把 chapters / transcript / stage_timings 三个大 JSON 当 None。
      与 `_LITE_COLUMNS` 配套——SQL 都没拉这几列，这里也不要尝试解析。
    - lite=False：详情接口用，全量字段。
    """
    option_overrides = json.loads(row["options_json"])
    effective_options = json.loads(row["effective_options_json"] or row["options_json"])
    return Job(
        id=row["id"],
        url=row["url"],
        bvid=row["bvid"],
        cid=row["cid"],
        mid=_opt_col(row, "mid"),
        title=row["title"],
        author=row["author"],
        duration=row["duration"],
        status=JobStatus(row["status"]),
        error_stage=row["error_stage"],
        error_message=row["error_message"],
        error_code=_opt_col(row, "error_code"),
        audio_path=row["audio_path"],
        subtitle_source=row["subtitle_source"],
        chapters=None if lite else _opt_json(row, "chapters_json"),
        transcript=None if lite else _opt_json(row, "transcript_json"),
        summary_path=row["summary_path"],
        options=JobOptions.from_dict(effective_options),
        option_overrides=option_overrides,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        stream_finished_at=_opt_col(row, "stream_finished_at"),
        token_usage=_opt_json(row, "token_usage_json"),
        stage_timings=None if lite else _opt_json(row, "stage_timings_json"),
        email_error=_opt_col(row, "email_error"),
        tags=_opt_json(row, "tags_json"),
    )


def _row_to_job_lite(row: Any) -> Job:
    return _row_to_job(row, lite=True)


def create_job(
    url: str, options: JobOptions, option_overrides: dict[str, Any] | None = None
) -> Job:
    timestamp = now_ms()
    option_overrides = option_overrides or {}
    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        status=JobStatus.PENDING,
        options=options,
        option_overrides=option_overrides,
        created_at=timestamp,
        updated_at=timestamp,
    )
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
              id, url, status, options_json, effective_options_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.url,
                job.status.value,
                json.dumps(option_overrides, ensure_ascii=False),
                json.dumps(options.as_dict(), ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    return job


def create_resummary_job(
    source: Job,
    options: JobOptions,
    option_overrides: dict[str, Any] | None = None,
) -> Job:
    timestamp = now_ms()
    option_overrides = option_overrides or {}
    job_id = str(uuid.uuid4())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
              id, url, bvid, cid, mid, title, author, duration, status,
              subtitle_source, chapters_json, transcript_json,
              options_json, effective_options_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                source.url,
                source.bvid,
                source.cid,
                source.mid,
                source.title,
                source.author,
                source.duration,
                JobStatus.TRANSCRIPT_READY.value,
                source.subtitle_source,
                json.dumps(source.chapters or [], ensure_ascii=False),
                json.dumps(source.transcript or [], ensure_ascii=False),
                json.dumps(option_overrides, ensure_ascii=False),
                json.dumps(options.as_dict(), ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    job = get_job(job_id)
    if job is None:
        raise RuntimeError("Created job not found")
    return job


def get_job(job_id: str) -> Job | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


# 蒸馏建的 job（task_type="distill"）走同一张 jobs 表复用转写/并发限流，但不该出现
# 在主历史列表里——它没有笔记、也不是用户主动发起的「一条总结任务」。task_type 不是
# 独立列（住在 effective_options_json 里），用 json_extract 过滤，不加新列/迁移。
_EXCLUDE_DISTILL_CLAUSE = "AND json_extract(effective_options_json, '$.task_type') IS NOT 'distill'"


UNKNOWN_AUTHOR_SENTINEL = "未知 UP"
_HISTORY_EFFECTIVE_AT = "COALESCE(completed_at, created_at)"


def encode_history_cursor(job: Job, *, terminal_only: bool = False) -> str:
    """The ordered pair used by history pagination (newest first)."""
    effective_at = job.completed_at if terminal_only and job.completed_at is not None else job.created_at
    return f"{effective_at}:{job.id}"


def _parse_history_cursor(cursor: str | int) -> tuple[int, str | None]:
    """Accept the former timestamp-only cursor while emitting stable cursors."""
    raw = str(cursor)
    timestamp, separator, job_id = raw.partition(":")
    try:
        created_at = int(timestamp)
    except ValueError as exc:
        raise ValueError("invalid history cursor") from exc
    if created_at < 0 or (separator and not job_id):
        raise ValueError("invalid history cursor")
    return created_at, job_id if separator else None


def _history_filter_clauses(
    *, query: str | None = None, author: str | None = None, tag: str | None = None
) -> tuple[list[str], list[Any]]:
    clauses = ["json_extract(effective_options_json, '$.task_type') IS NOT 'distill'"]
    parameters: list[Any] = []
    if query:
        escaped_query = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        clauses.append(
            """(
                lower(COALESCE(title, '')) LIKE ? ESCAPE '\\'
                OR lower(COALESCE(author, '')) LIKE ? ESCAPE '\\'
                OR lower(COALESCE(bvid, '')) LIKE ? ESCAPE '\\'
                OR lower(COALESCE(url, '')) LIKE ? ESCAPE '\\'
                OR EXISTS (
                    SELECT 1 FROM json_each(COALESCE(tags_json, '[]')) AS tag_item
                    WHERE lower(CAST(tag_item.value AS TEXT)) LIKE ? ESCAPE '\\'
                )
            )"""
        )
        parameters.extend([pattern, pattern, pattern, pattern, pattern])
    if author:
        if author == UNKNOWN_AUTHOR_SENTINEL:
            clauses.append("(author IS NULL OR TRIM(author) = '')")
        else:
            clauses.append("TRIM(COALESCE(author, '')) = ?")
            parameters.append(author)
    if tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(COALESCE(tags_json, '[]')) AS tag_item WHERE tag_item.value = ?)"
        )
        parameters.append(tag)
    return clauses, parameters


def list_jobs(
    limit: int = 50,
    offset: int = 0,
    cursor: str | int | None = None,
    *,
    query: str | None = None,
    author: str | None = None,
    tag: str | None = None,
    active_only: bool = False,
    terminal_only: bool = False,
) -> list[Job]:
    """Jobs with compatible default scope plus history-specific scopes.

    Timestamp-only cursors are retained for older callers, while new cursors
    include ``id`` so jobs completed in the same millisecond cannot be skipped.
    """
    clauses, parameters = _history_filter_clauses(query=query, author=author, tag=tag)
    if active_only and terminal_only:
        raise ValueError("active and terminal scopes are mutually exclusive")
    terminal_placeholders, terminal_values = _status_filter(TERMINAL_JOB_STATUSES)
    legacy_cursor = False
    if active_only:
        clauses.append(f"status NOT IN ({terminal_placeholders})")
        parameters.extend(terminal_values)
    elif terminal_only:
        clauses.append(f"status IN ({terminal_placeholders})")
        parameters.extend(terminal_values)
    with connect() as connection:
        cursor_field = _HISTORY_EFFECTIVE_AT if terminal_only else "created_at"
        if cursor is not None and not active_only:
            effective_at, job_id = _parse_history_cursor(cursor)
            if job_id is None:
                # Compatibility for the old API. It cannot distinguish peers
                # with equal timestamps and always uses created_at ordering.
                legacy_cursor = True
                clauses.append("created_at < ?")
                parameters.append(effective_at)
            else:
                clauses.append(
                    f"({cursor_field} < ? OR ({cursor_field} = ? AND id < ?))"
                )
                parameters.extend([effective_at, effective_at, job_id])
        elif not active_only:
            # Offset is only for legacy callers; the history UI uses cursor.
            pass
        order_by = (
            "created_at DESC, id DESC"
            if active_only or not terminal_only or legacy_cursor
            else f"{_HISTORY_EFFECTIVE_AT} DESC, id DESC"
        )
        pagination = "" if active_only else "LIMIT ? OFFSET ?"
        statement = f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE {' AND '.join(clauses)}
            ORDER BY {order_by} {pagination}
        """
        page_parameters = [] if active_only else [limit, 0 if cursor is not None else offset]
        rows = connection.execute(statement, [*parameters, *page_parameters]).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_recoverable_jobs() -> list[Job]:
    """启动恢复：只需要 status / url / options 这些 lite 字段决定是否能恢复。"""
    placeholders, values = _status_filter(PAUSED_OR_TERMINAL_JOB_STATUSES)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE status NOT IN ({placeholders})
            ORDER BY created_at ASC
            """,
            values,
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_jobs_by_status(statuses: Collection[JobStatus]) -> list[Job]:
    """清理 / 批量删除用：走 lite 投影，省内存。"""
    if not statuses:
        return []
    placeholders, values = _status_filter(statuses)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_LITE_COLUMNS} FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            values,
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_jobs_by_status_before(statuses: Collection[JobStatus], before_ms: int) -> list[Job]:
    if not statuses:
        return []
    placeholders, values = _status_filter(statuses)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE status IN ({placeholders}) AND updated_at < ?
            ORDER BY updated_at ASC
            """,
            [*values, before_ms],
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_running_jobs_stale_before(before_ms: int) -> list[Job]:
    """非终态且 `updated_at` 早于 before_ms 的僵尸任务。"""
    placeholders, values = _status_filter(PAUSED_OR_TERMINAL_JOB_STATUSES)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE status NOT IN ({placeholders}) AND updated_at < ?
            ORDER BY updated_at ASC
            """,
            [*values, before_ms],
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def all_audio_paths() -> set[str]:
    """孤儿扫描用：返回 DB 里所有 `audio_path` 集合。"""
    with connect() as connection:
        rows = connection.execute(
            "SELECT audio_path FROM jobs WHERE audio_path IS NOT NULL"
        ).fetchall()
    return {row["audio_path"] for row in rows if row["audio_path"]}


def all_summary_paths() -> set[str]:
    """Resolved absolute path strings for orphan scan (legacy absolute + relative)."""
    from biri_youyaku.modules.storage import summary as summary_storage

    with connect() as connection:
        rows = connection.execute(
            "SELECT summary_path FROM jobs WHERE summary_path IS NOT NULL"
        ).fetchall()
    known: set[str] = set()
    for row in rows:
        stored = row["summary_path"]
        if not stored:
            continue
        resolved = summary_storage.resolve_stored_path(stored)
        known.add(str(resolved))
        # Keep raw DB form too so mixed absolute/relative comparisons still work.
        known.add(stored)
    return known


def update_status(job_id: str, status: JobStatus) -> None:
    completed_at = now_ms() if status == JobStatus.COMPLETED else None
    stream_finished_at = now_ms() if status in TERMINAL_JOB_STATUSES else None
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at),
                stream_finished_at = COALESCE(?, stream_finished_at)
            WHERE id = ?
            """,
            (status.value, now_ms(), completed_at, stream_finished_at, job_id),
        )


def transition_status(
    job_id: str,
    status: JobStatus,
    *,
    expected_statuses: Collection[JobStatus],
) -> bool:
    """Atomically move a job only when it is still in an expected state."""
    if not expected_statuses:
        return False
    placeholders, values = _status_filter(expected_statuses)
    timestamp = now_ms()
    completed_at = timestamp if status == JobStatus.COMPLETED else None
    stream_finished_at = timestamp if status in TERMINAL_JOB_STATUSES else None
    with connect() as connection:
        cursor = connection.execute(
            f"""
            UPDATE jobs
            SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at),
                stream_finished_at = COALESCE(?, stream_finished_at)
            WHERE id = ? AND status IN ({placeholders})
            """,
            (
                status.value,
                timestamp,
                completed_at,
                stream_finished_at,
                job_id,
                *values,
            ),
        )
    return cursor.rowcount == 1


def fail_stale_running_job(
    job_id: str,
    *,
    expected_status: JobStatus,
    cutoff_ms: int,
    message: str,
) -> bool:
    """Atomically mark one unchanged running job as stale/failed."""
    timestamp = now_ms()
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = ?, error_stage = ?, error_message = ?, error_code = ?,
                updated_at = ?, stream_finished_at = COALESCE(stream_finished_at, ?)
            WHERE id = ? AND status = ? AND updated_at < ?
            """,
            (
                JobStatus.FAILED.value,
                expected_status.value,
                message,
                "STAGE_STUCK",
                timestamp,
                timestamp,
                job_id,
                expected_status.value,
                cutoff_ms,
            ),
        )
    return cursor.rowcount == 1


def _set(job_id: str, **fields: Any) -> None:
    """通用 single-row 更新：拼 `SET col = ?, ..., updated_at = ? WHERE id = ?`。

    None 走原生绑定 → SQLite 写入 NULL。需要 NULL 的列直接传 `None` 即可。
    带 read-modify-write（add_stage_timing / add_token_usage）或多列协调（update_status）
    的 setter 不走这里，自己拼 SQL。
    """
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values())
    with connect() as connection:
        connection.execute(
            f"UPDATE jobs SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, now_ms(), job_id),
        )


def clear_error(job_id: str) -> None:
    _set(job_id, error_stage=None, error_message=None, error_code=None)


def update_meta(
    job_id: str,
    *,
    bvid: str,
    cid: int | None,
    title: str,
    author: str,
    duration: float,
    mid: int | None = None,
) -> None:
    _set(
        job_id,
        bvid=bvid,
        cid=cid,
        mid=mid,
        title=title,
        author=author,
        duration=duration,
    )
    # 顺手把这个作者的「老任务」（mid 列上线前建的，author 有但 mid 为空）补上 mid，
    # 之后它们的作者名也能直接点开「全部投稿」，不必每次现场解析。
    if mid is not None and author:
        backfill_mid_by_author(author, mid)


def set_tags(job_id: str, tags: list[str]) -> None:
    _set(job_id, tags_json=json.dumps(tags, ensure_ascii=False))


def list_completed_without_tags(limit: int = 500) -> list[Job]:
    """启动回填用：已完成但还没有标签的任务（lite 投影）。"""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_LITE_COLUMNS} FROM jobs "
            f"WHERE status = ? AND (tags_json IS NULL OR tags_json = '') "
            f"ORDER BY created_at DESC LIMIT ?",
            (JobStatus.COMPLETED.value, limit),
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def backfill_mid_by_author(author: str, mid: int) -> int:
    """把同名作者下 mid 仍为空的任务补上 mid，返回补了多少条。"""
    if not author:
        return 0
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE jobs SET mid = ? WHERE mid IS NULL AND author = ?",
            (mid, author),
        )
        return cursor.rowcount


def set_chapters(job_id: str, chapters: list[Chapter] | None) -> None:
    payload = [
        {"start": chapter.start, "end": chapter.end, "title": chapter.title}
        for chapter in chapters or []
    ]
    _set(job_id, chapters_json=json.dumps(payload, ensure_ascii=False))


def set_audio_path(job_id: str, audio_path: Path) -> None:
    _set(job_id, audio_path=str(audio_path))


def clear_audio_path(job_id: str) -> None:
    _set(job_id, audio_path=None)


def set_subtitle_source(job_id: str, subtitle_source: str) -> None:
    _set(job_id, subtitle_source=subtitle_source)


def set_transcript(job_id: str, items: list[TranscriptItem]) -> None:
    payload = [{"start": item.start, "end": item.end, "text": item.text} for item in items]
    _set(job_id, transcript_json=json.dumps(payload, ensure_ascii=False))


def clear_transcript(job_id: str) -> None:
    """Clear transcript, subtitle source, and summary so the job can re-run ASR."""
    _set(job_id, transcript_json=None, subtitle_source=None, summary_path=None)


def update_options(
    job_id: str,
    options: JobOptions,
    option_overrides: dict[str, Any] | None = None,
) -> None:
    _set(
        job_id,
        options_json=json.dumps(option_overrides or {}, ensure_ascii=False),
        effective_options_json=json.dumps(options.as_dict(), ensure_ascii=False),
    )


def set_summary_path(job_id: str, summary_path: Path | str) -> None:
    from biri_youyaku.modules.storage import summary as summary_storage

    _set(job_id, summary_path=summary_storage.to_stored_path(summary_path))


def add_stage_timing(job_id: str, stage: str, started_at: int, ended_at: int) -> None:
    duration_ms = max(0, ended_at - started_at)
    with connect() as connection:
        row = connection.execute(
            "SELECT stage_timings_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        timings = json.loads(row["stage_timings_json"]) if row and row["stage_timings_json"] else []
        timings.append(
            {
                "stage": stage,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms,
            }
        )
        connection.execute(
            "UPDATE jobs SET stage_timings_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(timings, ensure_ascii=False), now_ms(), job_id),
        )


def add_token_usage(job_id: str, usage: dict[str, Any]) -> None:
    """Atomically increment token counters using json_set + json_extract arithmetic.

    Avoids a SELECT→UPDATE read-modify-write race that would silently lose tokens
    when concurrent segment-summary tasks (``_summarize_chunked``) call this for the
    same job.
    """
    input_delta = int(usage.get("input_tokens") or 0)
    output_delta = int(usage.get("output_tokens") or 0)
    total_delta = int(usage.get("total_tokens") or 0)
    cost_estimate = usage.get("cost_estimate")
    with connect() as connection:
        # COALESCE + arithmetic in a single UPDATE so concurrent callers don't
        # clobber each other's increments.
        connection.execute(
            """
            UPDATE jobs
            SET token_usage_json = json_set(
                    COALESCE(token_usage_json, '{}'),
                    '$.input_tokens',
                        COALESCE(json_extract(token_usage_json, '$.input_tokens'), 0) + ?,
                    '$.output_tokens',
                        COALESCE(json_extract(token_usage_json, '$.output_tokens'), 0) + ?,
                    '$.total_tokens',
                        COALESCE(json_extract(token_usage_json, '$.total_tokens'), 0) + ?,
                    '$.cost_estimate', json(?)
                ),
                updated_at = ?
            WHERE id = ?
            """,
            (input_delta, output_delta, total_delta, json.dumps(cost_estimate), now_ms(), job_id),
        )


def clear_summary_path(job_id: str) -> None:
    # summary 重做时把 completed_at 也清掉，保持「有 summary 才算完成」的一致性。
    _set(job_id, summary_path=None, completed_at=None)


def set_email_error(job_id: str, message: str | None) -> None:
    """`COMPLETED + email_error` 表示总结成功但邮件失败，前端展示「邮件未送达 ↻ 重发」。"""
    _set(job_id, email_error=message)


def set_error(job_id: str, stage: str, message: str, code: str | None = None) -> None:
    _set(job_id, error_stage=stage, error_message=message, error_code=code)


def summary_status_for_bvids(bvids: list[str]) -> dict[str, dict[str, Any]]:
    """给一批 bvid，返回 {bvid: {"status": ..., "job_id": ...}}。

    UP 投稿列表只给 bvid（不含 cid/分 P），所以按 **bvid 粒度**匹配。一个 bvid 可能有
    多条任务，按相关性取一条：COMPLETED 优先，其次进行中，最后失败/取消；同档取最新。
    没有任何任务的 bvid 不出现在结果里。
    """
    unique = [b for b in dict.fromkeys(bvids) if b]
    if not unique:
        return {}
    placeholders = ",".join("?" for _ in unique)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT id, bvid, status, created_at FROM jobs "
            f"WHERE bvid IN ({placeholders}) {_EXCLUDE_DISTILL_CLAUSE} ORDER BY created_at ASC",
            unique,
        ).fetchall()

    # 状态优先级：COMPLETED 最高，进行中其次，终态失败最低。
    def rank(status: str) -> int:
        if status == JobStatus.COMPLETED.value:
            return 3
        if status in (JobStatus.FAILED.value, JobStatus.CANCELED.value):
            return 1
        return 2  # 进行中

    best: dict[str, tuple[int, int, str, str]] = {}  # bvid -> (rank, created_at, status, job_id)
    for row in rows:
        bvid = row["bvid"]
        candidate = (rank(row["status"]), row["created_at"], row["status"], row["id"])
        current = best.get(bvid)
        # 同 rank 时 created_at 大者胜（rows 已按 created_at 升序，直接覆盖即可）。
        if current is None or candidate[0] >= current[0]:
            best[bvid] = candidate
    return {bvid: {"status": value[2], "job_id": value[3]} for bvid, value in best.items()}


def find_completed_by_bvid(bvid: str, *, include_distill: bool = False) -> Job | None:
    """同一 BV 号最近一条「已完成」任务，用于创建时去重（命中就复用、不重复总结）。

    默认排除 distill 任务：它们 COMPLETED 但只有转写、没有总结，普通总结流程若复用
    等于拿到一条空结果。蒸馏编排器复用转写时传 include_distill=True。
    """
    if not bvid:
        return None
    clause = "" if include_distill else _EXCLUDE_DISTILL_CLAUSE
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT * FROM jobs
            WHERE bvid = ? AND status = ? {clause}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (bvid, JobStatus.COMPLETED.value),
        ).fetchone()
    return _row_to_job(row) if row else None


def find_active_distill_by_bvid(bvid: str) -> Job | None:
    """Return the newest in-flight distill job by persisted BV or its canonical source URL."""
    if not bvid:
        return None
    placeholders, statuses = _status_filter(TERMINAL_JOB_STATUSES)
    source_url = canonical_video_url(bvid)
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT * FROM jobs
            WHERE json_extract(effective_options_json, '$.task_type') = 'distill'
              AND status NOT IN ({placeholders})
              AND (bvid = ? OR (bvid IS NULL AND url = ?))
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (*statuses, bvid, source_url),
        ).fetchone()
    return _row_to_job(row) if row else None


def read_summary(job: Job) -> str | None:
    if job.summary_path is None:
        return None
    from biri_youyaku.modules.storage import summary as summary_storage

    path = summary_storage.resolve_stored_path(job.summary_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def delete_job(job_id: str) -> int:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount


def delete_jobs_by_status(statuses: Collection[JobStatus]) -> int:
    if not statuses:
        return 0
    placeholders, values = _status_filter(statuses)
    with connect() as connection:
        cursor = connection.execute(
            f"DELETE FROM jobs WHERE status IN ({placeholders})",
            values,
        )
        return cursor.rowcount


def list_bulk_delete_candidates(
    *,
    query: str | None = None,
    author: str | None = None,
    tag: str | None = None,
    connection: Any | None = None,
) -> list[Job]:
    """Return every history-page bulk-delete candidate, independent of pagination.

    This is intentionally a database query rather than a filter over the list API:
    the browser may only have rendered a small, scroll-loaded subset of history.
    """
    placeholders, values = _status_filter(BULK_DELETE_JOB_STATUSES)
    filter_clauses, filter_params = _history_filter_clauses(query=query, author=author, tag=tag)
    clauses = [f"status IN ({placeholders})", *filter_clauses]
    parameters: list[Any] = [*values, *filter_params]

    statement = f"""
        SELECT {_LITE_COLUMNS} FROM jobs
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC, id DESC
        """
    if connection is None:
        with connect() as read_connection:
            rows = read_connection.execute(statement, parameters).fetchall()
    else:
        rows = connection.execute(statement, parameters).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def delete_jobs_by_ids(job_ids: Collection[str], *, connection: Any | None = None) -> int:
    if not job_ids:
        return 0
    placeholders = ",".join("?" for _ in job_ids)
    statement = f"DELETE FROM jobs WHERE id IN ({placeholders})"
    if connection is None:
        with connect() as write_connection:
            cursor = write_connection.execute(statement, list(job_ids))
            return cursor.rowcount
    cursor = connection.execute(statement, list(job_ids))
    return cursor.rowcount


def count_jobs_excluding_status(statuses: Collection[JobStatus]) -> int:
    if not statuses:
        with connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
        return int(row["count"])
    placeholders, values = _status_filter(statuses)
    with connect() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM jobs WHERE status NOT IN ({placeholders})",
            values,
        ).fetchone()
    return int(row["count"])
