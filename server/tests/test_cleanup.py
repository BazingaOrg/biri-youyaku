import os
import sqlite3
from contextlib import contextmanager

import pytest

from biri_youyaku import db
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.jobs import cleanup, repo
from biri_youyaku.jobs.model import JobOptions, JobStatus


@pytest.mark.asyncio
async def test_cleanup_removes_expired_audio_without_deleting_job(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "audio_retention_days", 1)
    monkeypatch.setattr(cleanup.settings, "job_retention_days", 180)
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    audio_path = tmp_path / f"{job.id}.wav"
    audio_path.write_text("audio", encoding="utf-8")
    repo.set_audio_path(job.id, audio_path)
    repo.update_status(job.id, JobStatus.COMPLETED)
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (repo.now_ms() - 2 * 24 * 60 * 60 * 1000, job.id),
        )

    result = await cleanup.cleanup_once()

    assert result["audio_removed"] == 1
    assert result["jobs_removed"] == 0
    assert not audio_path.exists()
    loaded = repo.get_job(job.id)
    assert loaded is not None
    assert loaded.audio_path is None


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_terminal_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "audio_retention_days", 7)
    monkeypatch.setattr(cleanup.settings, "job_retention_days", 1)
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    summary_path = tmp_path / f"{job.id}.md"
    summary_path.write_text("summary", encoding="utf-8")
    repo.set_summary_path(job.id, summary_path)
    repo.update_status(job.id, JobStatus.COMPLETED)
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (repo.now_ms() - 2 * 24 * 60 * 60 * 1000, job.id),
        )

    result = await cleanup.cleanup_once()

    assert result["jobs_removed"] == 1
    assert repo.get_job(job.id) is None
    assert not summary_path.exists()


@pytest.mark.asyncio
async def test_fail_stale_running_skips_active_task_and_uses_atomic_transition(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "stale_running_fail_hours", 1)
    db.init_db()
    active = repo.create_job("https://www.bilibili.com/video/BV-active", JobOptions())
    stale = repo.create_job("https://www.bilibili.com/video/BV-stale", JobOptions())
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id IN (?, ?)",
            (repo.now_ms() - 2 * 60 * 60 * 1000, active.id, stale.id),
        )
    monkeypatch.setattr(cleanup, "has_active_task", lambda job_id: job_id == active.id)

    assert await cleanup.fail_stale_running_once() == 1
    assert repo.get_job(active.id).status == JobStatus.PENDING
    failed = repo.get_job(stale.id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "STAGE_STUCK"


def _age_dir(path, days):
    old_time = repo.now_ms() / 1000 - days * 24 * 60 * 60
    os.utime(path, (old_time, old_time))


@pytest.mark.asyncio
async def test_scan_orphans_removes_distill_dir_without_db_record(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "orphan_file_retention_days", 1)
    distill_dir = tmp_path / "distill"
    monkeypatch.setattr(cleanup.settings, "distill_storage_dir", distill_dir)
    db.init_db()

    orphan_dir = distill_dir / "123"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "corpus.md").write_text("stale", encoding="utf-8")
    _age_dir(orphan_dir, 2)

    result = await cleanup.scan_orphans_once()

    assert result["distill_orphans"] == 1
    assert not orphan_dir.exists()


@pytest.mark.asyncio
async def test_scan_orphans_keeps_distill_dir_with_db_record(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "orphan_file_retention_days", 1)
    distill_dir = tmp_path / "distill"
    monkeypatch.setattr(cleanup.settings, "distill_storage_dir", distill_dir)
    db.init_db()
    distill_repo.create_run(456, video_limit=50, dir_path="d")

    kept_dir = distill_dir / "456"
    kept_dir.mkdir(parents=True)
    (kept_dir / "corpus.md").write_text("kept", encoding="utf-8")
    _age_dir(kept_dir, 2)

    result = await cleanup.scan_orphans_once()

    assert result["distill_orphans"] == 0
    assert kept_dir.exists()


@pytest.mark.asyncio
async def test_scan_orphans_respects_retention_window_for_distill_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "orphan_file_retention_days", 3)
    distill_dir = tmp_path / "distill"
    monkeypatch.setattr(cleanup.settings, "distill_storage_dir", distill_dir)
    db.init_db()

    fresh_orphan_dir = distill_dir / "789"
    fresh_orphan_dir.mkdir(parents=True)
    (fresh_orphan_dir / "corpus.md").write_text("fresh", encoding="utf-8")
    _age_dir(fresh_orphan_dir, 1)  # 未过 retention 期，不该被删

    result = await cleanup.scan_orphans_once()

    assert result["distill_orphans"] == 0
    assert fresh_orphan_dir.exists()


@pytest.mark.asyncio
async def test_checkpoint_uses_short_connection_without_committing_repo_transaction(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    shared_connection = db.connect()
    shared_connection.execute("UPDATE jobs SET title = ? WHERE id = ?", ("uncommitted", job.id))

    @contextmanager
    def short_maintenance_connection():
        connection = sqlite3.connect(tmp_path / "jobs.db")
        connection.execute("PRAGMA busy_timeout=1")
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(cleanup, "maintenance_connection", short_maintenance_connection)

    await cleanup.checkpoint_wal()

    assert shared_connection.in_transaction
    shared_connection.rollback()
    assert repo.get_job(job.id).title is None
