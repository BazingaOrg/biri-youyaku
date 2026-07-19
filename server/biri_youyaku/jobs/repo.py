import json
import time
import uuid
from pathlib import Path
from typing import Any, Collection, Iterable

from biri_youyaku.db import connect
from biri_youyaku.jobs.model import (
    Job,
    JobOptions,
    JobStatus,
    PAUSED_OR_TERMINAL_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
)
from biri_youyaku.modules.bilibili.meta import Chapter
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


def list_jobs(limit: int = 50, offset: int = 0, cursor: int | None = None) -> list[Job]:
    """列表页接口：走 lite 投影，不拉 transcript/chapters/stage_timings；默认排除 distill 任务。"""
    with connect() as connection:
        if cursor is not None:
            rows = connection.execute(
                f"""
                SELECT {_LITE_COLUMNS} FROM jobs
                WHERE created_at < ? {_EXCLUDE_DISTILL_CLAUSE}
                ORDER BY created_at DESC LIMIT ?
                """,
                (cursor, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT {_LITE_COLUMNS} FROM jobs
                WHERE 1=1 {_EXCLUDE_DISTILL_CLAUSE}
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
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
    with connect() as connection:
        rows = connection.execute(
            "SELECT summary_path FROM jobs WHERE summary_path IS NOT NULL"
        ).fetchall()
    return {row["summary_path"] for row in rows if row["summary_path"]}


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


def set_summary_path(job_id: str, summary_path: Path) -> None:
    _set(job_id, summary_path=str(summary_path))


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
    with connect() as connection:
        row = connection.execute(
            "SELECT token_usage_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        current = json.loads(row["token_usage_json"]) if row and row["token_usage_json"] else {}
        next_usage = dict(current)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            next_usage[key] = int(next_usage.get(key) or 0) + int(usage.get(key) or 0)
        next_usage["cost_estimate"] = usage.get("cost_estimate")
        connection.execute(
            "UPDATE jobs SET token_usage_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(next_usage, ensure_ascii=False), now_ms(), job_id),
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


def read_summary(job: Job) -> str | None:
    if job.summary_path is None:
        return None
    path = Path(job.summary_path)
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
