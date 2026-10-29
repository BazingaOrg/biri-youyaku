import os
from pathlib import Path

import pytest

from biri_youyaku import db
from biri_youyaku.jobs import cleanup, repo
from biri_youyaku.jobs.model import JobOptions, JobStatus


def _age(path: Path, days: int) -> None:
    value = repo.now_ms() / 1000 - days * 24 * 60 * 60
    os.utime(path, (value, value))


def _age_job(job_id: str, days: int) -> None:
    value = repo.now_ms() - days * 24 * 60 * 60 * 1000
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (value, value, value, job_id),
        )


def _age_terminal_job(job_id: str, days: int) -> None:
    value = repo.now_ms() - days * 24 * 60 * 60 * 1000
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ?, completed_at = NULL WHERE id = ?",
            (value, value, job_id),
        )


def _uploaded_job(root: Path):
    job = repo.create_job("upload://input", JobOptions())
    source = root / f"{job.id}.wav"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"uploaded")
    repo.set_source(job.id, "upload", job.id, "", input_path=str(source))
    return job, source


@pytest.mark.asyncio
async def test_cleanup_removes_expired_uploaded_input_and_clears_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    monkeypatch.setattr(cleanup, "AUDIO_RETENTION_DAYS", 1)
    db.init_db()
    job, source = _uploaded_job(tmp_path / "imports")
    repo.update_status(job.id, JobStatus.COMPLETED)
    _age_job(job.id, 2)

    await cleanup.cleanup_once()

    loaded = repo.get_job(job.id)
    assert loaded is not None
    assert loaded.input_path is None
    assert not source.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.CANCELED])
async def test_cleanup_keeps_recently_terminal_uploaded_input(monkeypatch, tmp_path, status):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    monkeypatch.setattr(cleanup, "AUDIO_RETENTION_DAYS", 1)
    db.init_db()
    job, source = _uploaded_job(tmp_path / "imports")
    _age_terminal_job(job.id, 2)
    repo.update_status(job.id, status)

    await cleanup.cleanup_once()

    loaded = repo.get_job(job.id)
    assert loaded is not None
    assert loaded.input_path == str(source)
    assert source.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.CANCELED])
async def test_cleanup_removes_uploaded_input_after_terminal_retention(monkeypatch, tmp_path, status):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    monkeypatch.setattr(cleanup, "AUDIO_RETENTION_DAYS", 1)
    db.init_db()
    job, source = _uploaded_job(tmp_path / "imports")
    repo.update_status(job.id, status)
    _age_terminal_job(job.id, 2)

    await cleanup.cleanup_once()

    loaded = repo.get_job(job.id)
    assert loaded is not None
    assert loaded.input_path is None
    assert not source.exists()


@pytest.mark.asyncio
async def test_cleanup_keeps_active_uploaded_input(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    monkeypatch.setattr(cleanup, "AUDIO_RETENTION_DAYS", 1)
    db.init_db()
    job, source = _uploaded_job(tmp_path / "imports")
    _age_job(job.id, 2)

    await cleanup.cleanup_once()

    assert source.exists()
    assert repo.get_job(job.id).input_path == str(source)


def test_audio_only_cleanup_keeps_uploaded_input(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    db.init_db()
    job, source = _uploaded_job(tmp_path / "imports")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    repo.set_audio_path(job.id, audio)

    cleanup.delete_job_files(repo.get_job(job.id), audio_only=True)

    assert source.exists()
    assert not audio.exists()


def test_bulk_targets_skip_external_input(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    db.init_db()
    job = repo.create_job("upload://input", JobOptions())
    external = tmp_path / "outside.wav"
    external.write_bytes(b"outside")
    repo.set_source(job.id, "upload", job.id, "", input_path=str(external))

    assert all(target["file_type"] != "input" for target in cleanup.collect_job_file_cleanup_targets(repo.get_job(job.id)))
    assert external.exists()


@pytest.mark.asyncio
async def test_orphan_scan_only_removes_unreferenced_regular_import_files(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(cleanup.settings, "upload_storage_dir", tmp_path / "imports")
    monkeypatch.setattr(cleanup, "ORPHAN_FILE_RETENTION_DAYS", 1)
    db.init_db()
    _, referenced = _uploaded_job(tmp_path / "imports")
    orphan = tmp_path / "imports" / "orphan.wav"
    orphan.write_bytes(b"orphan")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    linked = tmp_path / "imports" / "linked.wav"
    linked.symlink_to(outside)
    for path in (referenced, orphan, outside):
        _age(path, 2)

    await cleanup.scan_orphans_once()

    assert referenced.exists()
    assert not orphan.exists()
    assert linked.is_symlink()
    assert outside.exists()


def test_youtube_crash_residue_cleanup_preserves_active_fresh_and_external(monkeypatch, tmp_path):
    from biri_youyaku.sources import youtube

    root = tmp_path / "audio"
    root.mkdir()
    stale = root / "biri-youyaku-youtube-stale"
    active = root / "biri-youyaku-youtube-active"
    fresh = root / "biri-youyaku-youtube-fresh"
    unrelated = root / "unrelated"
    external = tmp_path / "external"
    for path in (stale, active, fresh, unrelated, external):
        path.mkdir()
        (path / "audio.part").write_bytes(b"temporary")
    for path in (stale, active, unrelated, external):
        _age(path, 2)
    (root / "biri-youyaku-youtube-link").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(youtube, "_active_work_dirs", {active.resolve()})
    assert cleanup._scan_youtube_work_dirs(root) == 1
    assert not stale.exists()
    for path in (active, fresh, unrelated, external):
        assert (path / "audio.part").exists()
