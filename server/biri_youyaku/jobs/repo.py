import json
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
    )


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


def list_jobs(limit: int = 50, offset: int = 0) -> list[Job]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_recoverable_jobs() -> list[Job]:
    terminal_statuses = (
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TRANSCRIPT_READY.value,
    )
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM jobs
            WHERE status NOT IN (?, ?, ?, ?)
            ORDER BY created_at ASC
            """,
            terminal_statuses,
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_jobs_by_status(statuses: set[JobStatus]) -> list[Job]:
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    values = [status.value for status in statuses]
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            values,
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def update_status(job_id: str, status: JobStatus) -> None:
    completed_at = now_ms() if status == JobStatus.COMPLETED else None
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
            WHERE id = ?
            """,
            (status.value, now_ms(), completed_at, job_id),
        )


def update_meta(job_id: str, *, bvid: str, cid: int | None, title: str, author: str, duration: float) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET bvid = ?, cid = ?, title = ?, author = ?, duration = ?, updated_at = ?
            WHERE id = ?
            """,
            (bvid, cid, title, author, duration, now_ms(), job_id),
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


def set_error(job_id: str, stage: str, message: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET error_stage = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (stage, message, now_ms(), job_id),
        )


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
