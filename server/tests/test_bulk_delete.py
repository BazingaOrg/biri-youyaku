import pytest
from fastapi import HTTPException

from biri_youyaku import db
from biri_youyaku.jobs import cleanup, repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.routes import jobs as jobs_route
from biri_youyaku.weekly import repo as weekly_summary_repo


def _create_finished_job(
    *,
    title: str,
    author: str,
    tags: list[str],
    status: JobStatus = JobStatus.COMPLETED,
    task_type: str = "summary",
):
    job = repo.create_job(
        f"https://www.bilibili.com/video/{title}",
        JobOptions(task_type=task_type, email_enabled=False),
    )
    repo.update_meta(job.id, bvid=f"BV{title}", cid=None, title=title, author=author, duration=1.0)
    repo.set_tags(job.id, tags)
    repo.update_status(job.id, status)
    return job


def test_bulk_delete_candidates_filter_the_complete_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    completed = _create_finished_job(title="AI review", author="Alice", tags=["知识"])
    failed = _create_finished_job(
        title="Other", author="Alice", tags=["技术"], status=JobStatus.FAILED
    )
    _create_finished_job(title="AI distill", author="Alice", tags=["知识"], task_type="distill")
    spaced_author = _create_finished_job(title="Spaced", author=" Alice ", tags=["知识"])
    blank_author = _create_finished_job(title="Blank", author="   ", tags=["知识"])
    unknown_author = _create_finished_job(title="Unknown", author="Placeholder", tags=["知识"])
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET author = NULL WHERE id = ?", (unknown_author.id,))
    paused = _create_finished_job(
        title="Paused", author="Alice", tags=["知识"], status=JobStatus.TRANSCRIPT_READY
    )

    assert [job.id for job in repo.list_bulk_delete_candidates(query="ai")] == [completed.id]
    assert [job.id for job in repo.list_bulk_delete_candidates(author="Alice", tag="技术")] == [
        failed.id
    ]
    assert repo.list_bulk_delete_candidates(tag="不存在") == []
    assert [
        job.id for job in repo.list_bulk_delete_candidates(query="bilibili.com/video/AI review")
    ] == [completed.id]
    assert {job.id for job in repo.list_bulk_delete_candidates(author="Alice")} == {
        spaced_author.id,
        failed.id,
        completed.id,
    }
    assert {job.id for job in repo.list_bulk_delete_candidates(author="未知 UP")} == {
        blank_author.id,
        unknown_author.id,
    }
    assert repo.get_job(paused.id) is not None


@pytest.mark.asyncio
async def test_bulk_delete_preview_and_execute_delete_all_matching_files(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    first = _create_finished_job(title="First", author="Alice", tags=["知识"])
    second = _create_finished_job(
        title="Second", author="Alice", tags=["技术"], status=JobStatus.FAILED
    )
    other = _create_finished_job(title="Other", author="Bob", tags=["知识"])
    audio_path = tmp_path / "first.wav"
    summary_path = tmp_path / "first.md"
    audio_path.write_text("audio", encoding="utf-8")
    summary_path.write_text("summary", encoding="utf-8")
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET audio_path = ?, summary_path = ? WHERE id = ?",
            (str(audio_path), str(summary_path), first.id),
        )

    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="Alice")
    )

    assert preview["matched_count"] == 2
    assert preview["expires_at"] > repo.now_ms()
    assert (
        jobs_route._decode_bulk_delete_preview(preview["preview_token"])["expires_at"]
        == preview["expires_at"]
    )
    assert preview["by_status"] == {"CANCELED": 0, "COMPLETED": 1, "FAILED": 1}
    assert {item["id"] for item in preview["sample"]} == {first.id, second.id}
    assert preview["affected_weekly_summaries"] == 0

    result = await jobs_route.execute_bulk_delete(
        jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
    )

    assert result == {
        "ok": True,
        "deleted_count": 2,
        "affected_weekly_summaries": 0,
        "cleanup_pending_count": 0,
        "cleanup_failures": [],
        "cleanup_retry": None,
    }
    assert repo.get_job(first.id) is None
    assert repo.get_job(second.id) is None
    assert repo.get_job(other.id) is not None
    assert not audio_path.exists()
    assert not summary_path.exists()


@pytest.mark.asyncio
async def test_bulk_delete_execute_rejects_changed_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = _create_finished_job(title="First", author="Alice", tags=["知识"])
    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="Alice")
    )
    repo.update_status(job.id, JobStatus.SUMMARIZING)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.execute_bulk_delete(
            jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
        )

    assert exc_info.value.status_code == 409
    assert repo.get_job(job.id) is not None


@pytest.mark.asyncio
async def test_bulk_delete_execute_rejects_status_change_inside_delete_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = _create_finished_job(title="First", author="Alice", tags=["知识"])
    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="Alice")
    )
    repo.update_status(job.id, JobStatus.FAILED)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.execute_bulk_delete(
            jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
        )

    assert exc_info.value.status_code == 409
    assert repo.get_job(job.id) is not None


@pytest.mark.asyncio
async def test_bulk_delete_execute_rejects_changed_weekly_summary_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = _create_finished_job(title="First", author="Alice", tags=["知识"])
    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="Alice")
    )
    weekly_summary_repo.begin_generation("2026-07-27", fingerprint_value="source-change")
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO weekly_summary_sources (week_start, job_id) VALUES (?, ?)",
            ("2026-07-27", job.id),
        )

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.execute_bulk_delete(
            jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
        )

    assert exc_info.value.status_code == 409
    assert repo.get_job(job.id) is not None


@pytest.mark.asyncio
async def test_bulk_delete_reports_post_commit_file_cleanup_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = _create_finished_job(title="First", author="Alice", tags=["知识"])
    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="Alice")
    )
    monkeypatch.setattr(
        jobs_route,
        "delete_job_file_targets_with_result",
        lambda _targets: [
            {"job_id": job.id, "file_type": "summary", "path": str(tmp_path / "stuck.md")}
        ],
    )

    result = await jobs_route.execute_bulk_delete(
        jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
    )

    assert repo.get_job(job.id) is None
    assert result["cleanup_pending_count"] == 1
    assert result["cleanup_failures"] == [{"job_id": job.id, "file_type": "summary"}]
    assert result["cleanup_retry"] == "pending_file_cleanup"
    with db.connect() as connection:
        pending = connection.execute(
            "SELECT job_id, file_type, path FROM pending_file_cleanup"
        ).fetchall()
    assert [tuple(row) for row in pending] == [(job.id, "summary", str(tmp_path / "stuck.md"))]
    (tmp_path / "stuck.md").write_text("retry me", encoding="utf-8")
    assert cleanup.retry_pending_file_cleanup_once() == 1
    assert not (tmp_path / "stuck.md").exists()
    with db.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) AS count FROM pending_file_cleanup").fetchone()[
                "count"
            ]
            == 0
        )
