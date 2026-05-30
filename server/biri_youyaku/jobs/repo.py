import json
import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from biri_youyaku.db import connect
from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import Chapter
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


def now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_job(row: Any) -> Job:
    option_overrides = json.loads(row["options_json"])
    effective_options = json.loads(row["effective_options_json"] or row["options_json"])
    chapters = json.loads(row["chapters_json"]) if row["chapters_json"] else None
    transcript = json.loads(row["transcript_json"]) if row["transcript_json"] else None
    return Job(
        id=row["id"],
        url=row["url"],
        bvid=row["bvid"],
        cid=row["cid"],
        title=row["title"],
        author=row["author"],
        duration=row["duration"],
        status=JobStatus(row["status"]),
        error_stage=row["error_stage"],
        error_message=row["error_message"],
        error_code=row["error_code"] if "error_code" in row.keys() else None,
        audio_path=row["audio_path"],
        subtitle_source=row["subtitle_source"],
        chapters=chapters,
        transcript=transcript,
        summary_path=row["summary_path"],
        options=JobOptions.from_dict(effective_options),
        option_overrides=option_overrides,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        stream_finished_at=row["stream_finished_at"] if "stream_finished_at" in row.keys() else None,
        token_usage=json.loads(row["token_usage_json"]) if "token_usage_json" in row.keys() and row["token_usage_json"] else None,
        content_hash=row["content_hash"] if "content_hash" in row.keys() else None,
        stage_timings=json.loads(row["stage_timings_json"]) if "stage_timings_json" in row.keys() and row["stage_timings_json"] else None,
        email_error=row["email_error"] if "email_error" in row.keys() else None,
    )


# 列表 / 抽屉 / 清理用的 lite 投影：不拉 `chapters_json` / `transcript_json` /
# `stage_timings_json` 这种长 JSON 字段，30 条一拉从十几兆降到几十 KB。
_LITE_COLUMNS = (
    "id, url, bvid, cid, title, author, duration, status, "
    "error_stage, error_message, error_code, audio_path, "
    "subtitle_source, summary_path, options_json, effective_options_json, "
    "created_at, updated_at, completed_at, stream_finished_at, "
    "token_usage_json, content_hash, email_error"
)


def _row_to_job_lite(row: Any) -> Job:
    """与 `_row_to_job` 行为一致，但把长 JSON 字段（chapters/transcript/stage_timings）
    视为 None，避免在列表页拉巨型 payload。详情接口仍走 get_job → _row_to_job 拿全量。
    """
    option_overrides = json.loads(row["options_json"])
    effective_options = json.loads(row["effective_options_json"] or row["options_json"])
    return Job(
        id=row["id"],
        url=row["url"],
        bvid=row["bvid"],
        cid=row["cid"],
        title=row["title"],
        author=row["author"],
        duration=row["duration"],
        status=JobStatus(row["status"]),
        error_stage=row["error_stage"],
        error_message=row["error_message"],
        error_code=row["error_code"] if "error_code" in row.keys() else None,
        audio_path=row["audio_path"],
        subtitle_source=row["subtitle_source"],
        chapters=None,
        transcript=None,
        summary_path=row["summary_path"],
        options=JobOptions.from_dict(effective_options),
        option_overrides=option_overrides,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        stream_finished_at=row["stream_finished_at"] if "stream_finished_at" in row.keys() else None,
        token_usage=json.loads(row["token_usage_json"]) if "token_usage_json" in row.keys() and row["token_usage_json"] else None,
        content_hash=row["content_hash"] if "content_hash" in row.keys() else None,
        stage_timings=None,
        email_error=row["email_error"] if "email_error" in row.keys() else None,
    )


def content_hash_for(bvid: str, cid: int | None) -> str:
    return hashlib.sha256(f"{bvid}:{cid or ''}".encode("utf-8")).hexdigest()


def create_job(url: str, options: JobOptions, option_overrides: dict[str, Any] | None = None) -> Job:
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


def get_job(job_id: str) -> Job | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs(limit: int = 50, offset: int = 0, cursor: int | None = None) -> list[Job]:
    """列表页接口：走 lite 投影，不拉 transcript/chapters/stage_timings。"""
    with connect() as connection:
        if cursor is not None:
            rows = connection.execute(
                f"SELECT {_LITE_COLUMNS} FROM jobs WHERE created_at < ? ORDER BY created_at DESC LIMIT ?",
                (cursor, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                f"SELECT {_LITE_COLUMNS} FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_recoverable_jobs() -> list[Job]:
    """启动恢复：只需要 status / url / options 这些 lite 字段决定是否能恢复。"""
    terminal_statuses = (
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TRANSCRIPT_READY.value,
    )
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE status NOT IN (?, ?, ?, ?)
            ORDER BY created_at ASC
            """,
            terminal_statuses,
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_jobs_by_status(statuses: set[JobStatus]) -> list[Job]:
    """清理 / 批量删除用：走 lite 投影，省内存。"""
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    values = [status.value for status in statuses]
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_LITE_COLUMNS} FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            values,
        ).fetchall()
    return [_row_to_job_lite(row) for row in rows]


def list_jobs_by_status_before(statuses: set[JobStatus], before_ms: int) -> list[Job]:
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    values = [status.value for status in statuses]
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
    terminal = (
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TRANSCRIPT_READY.value,
    )
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {_LITE_COLUMNS} FROM jobs
            WHERE status NOT IN (?, ?, ?, ?) AND updated_at < ?
            ORDER BY updated_at ASC
            """,
            (*terminal, before_ms),
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
    stream_finished_at = now_ms() if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED} else None
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


def clear_error(job_id: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET error_stage = NULL, error_message = NULL, error_code = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now_ms(), job_id),
        )


def update_meta(job_id: str, *, bvid: str, cid: int | None, title: str, author: str, duration: float) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET bvid = ?, cid = ?, title = ?, author = ?, duration = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (bvid, cid, title, author, duration, content_hash_for(bvid, cid), now_ms(), job_id),
        )


def set_chapters(job_id: str, chapters: list[Chapter] | None) -> None:
    payload = [
        {
            "start": chapter.start,
            "end": chapter.end,
            "title": chapter.title,
        }
        for chapter in chapters or []
    ]
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET chapters_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), now_ms(), job_id),
        )


def set_audio_path(job_id: str, audio_path: Path) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET audio_path = ?, updated_at = ? WHERE id = ?",
            (str(audio_path), now_ms(), job_id),
        )


def clear_audio_path(job_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET audio_path = NULL, updated_at = ? WHERE id = ?",
            (now_ms(), job_id),
        )


def set_subtitle_source(job_id: str, subtitle_source: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET subtitle_source = ?, updated_at = ? WHERE id = ?",
            (subtitle_source, now_ms(), job_id),
        )


def set_transcript(job_id: str, items: list[TranscriptItem]) -> None:
    payload = [
        {
            "start": item.start,
            "end": item.end,
            "text": item.text,
        }
        for item in items
    ]
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET transcript_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), now_ms(), job_id),
        )


def clear_transcript(job_id: str) -> None:
    """Clear transcript, subtitle source, and summary so the job can re-run ASR."""
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET transcript_json = NULL, subtitle_source = NULL, summary_path = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now_ms(), job_id),
        )


def update_options(
    job_id: str,
    options: JobOptions,
    option_overrides: dict[str, Any] | None = None,
) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET options_json = ?, effective_options_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(option_overrides or {}, ensure_ascii=False),
                json.dumps(options.as_dict(), ensure_ascii=False),
                now_ms(),
                job_id,
            ),
        )


def set_summary_path(job_id: str, summary_path: Path) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET summary_path = ?, updated_at = ? WHERE id = ?",
            (str(summary_path), now_ms(), job_id),
        )


def add_stage_timing(job_id: str, stage: str, started_at: int, ended_at: int) -> None:
    duration_ms = max(0, ended_at - started_at)
    with connect() as connection:
        row = connection.execute("SELECT stage_timings_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
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
        row = connection.execute("SELECT token_usage_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        current = json.loads(row["token_usage_json"]) if row and row["token_usage_json"] else {}
        next_usage = dict(current)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            next_usage[key] = int(next_usage.get(key) or 0) + int(usage.get(key) or 0)
        next_usage["cost_estimate"] = usage.get("cost_estimate")
        connection.execute(
            "UPDATE jobs SET token_usage_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(next_usage, ensure_ascii=False), now_ms(), job_id),
        )


def usage_since(since_ms: int) -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT token_usage_json FROM jobs
            WHERE completed_at IS NOT NULL AND completed_at >= ? AND token_usage_json IS NOT NULL
            """,
            (since_ms,),
        ).fetchall()
    jobs_count = 0
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for row in rows:
        usage = json.loads(row["token_usage_json"])
        jobs_count += 1
        for key in totals:
            totals[key] += int(usage.get(key) or 0)
    return {"jobs_count": jobs_count, **totals, "cost_estimate": None}


def clear_summary_path(job_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET summary_path = NULL, completed_at = NULL, updated_at = ? WHERE id = ?",
            (now_ms(), job_id),
        )


def set_email_error(job_id: str, message: str | None) -> None:
    """`COMPLETED + email_error` 表示总结成功但邮件失败，前端展示「邮件未送达 ↻ 重发」。"""
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET email_error = ?, updated_at = ? WHERE id = ?",
            (message, now_ms(), job_id),
        )


def set_error(job_id: str, stage: str, message: str, code: str | None = None) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET error_stage = ?, error_message = ?, error_code = ?, updated_at = ?
            WHERE id = ?
            """,
            (stage, message, code, now_ms(), job_id),
        )


def find_latest_by_video(bvid: str, cid: int | None) -> Job | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM jobs
            WHERE content_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (content_hash_for(bvid, cid),),
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


def delete_jobs_by_status(statuses: set[JobStatus]) -> int:
    if not statuses:
        return 0
    placeholders = ",".join("?" for _ in statuses)
    values = [status.value for status in statuses]
    with connect() as connection:
        cursor = connection.execute(
            f"DELETE FROM jobs WHERE status IN ({placeholders})",
            values,
        )
        return cursor.rowcount


def count_jobs_excluding_status(statuses: set[JobStatus]) -> int:
    if not statuses:
        with connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
        return int(row["count"])
    placeholders = ",".join("?" for _ in statuses)
    values = [status.value for status in statuses]
    with connect() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM jobs WHERE status NOT IN ({placeholders})",
            values,
        ).fetchone()
    return int(row["count"])
