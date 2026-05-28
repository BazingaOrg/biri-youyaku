import pytest

from biri_youyaku import db
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
