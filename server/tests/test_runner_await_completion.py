import asyncio

import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobOptions, JobStatus


def _make_job(tmp_path, monkeypatch, status: JobStatus):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    repo.update_status(job.id, status)
    return job


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED]
)
async def test_await_job_completion_returns_immediately_for_terminal_job(
    monkeypatch, tmp_path, status
):
    """job 已经是终态：不需要任何在跑的 task，直接返回，不挂 future。"""
    job = _make_job(tmp_path, monkeypatch, status)

    result = await runner.await_job_completion(job.id)

    assert result == status
    assert job.id not in runner._completion


@pytest.mark.asyncio
async def test_await_job_completion_resolves_when_task_finishes_completed(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    runner._registry.reset_for_tests()

    async def _slow_finish():
        await asyncio.sleep(0.05)
        repo.update_status(job.id, JobStatus.COMPLETED)

    runner._spawn(job.id, _slow_finish)

    result = await runner.await_job_completion(job.id)

    assert result == JobStatus.COMPLETED
    assert job.id not in runner._completion


@pytest.mark.asyncio
async def test_await_job_completion_resolves_when_task_finishes_failed(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    runner._registry.reset_for_tests()

    async def _slow_finish():
        await asyncio.sleep(0.05)
        repo.update_status(job.id, JobStatus.FAILED)

    runner._spawn(job.id, _slow_finish)

    result = await runner.await_job_completion(job.id)

    assert result == JobStatus.FAILED
    assert job.id not in runner._completion


@pytest.mark.asyncio
async def test_await_job_completion_multiple_waiters_share_future(monkeypatch, tmp_path):
    """多个调用方等同一个 job：都应该拿到同样的终态，且 future 用完即清。"""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())
    runner._registry.reset_for_tests()

    async def _slow_finish():
        await asyncio.sleep(0.05)
        repo.update_status(job.id, JobStatus.CANCELED)

    runner._spawn(job.id, _slow_finish)

    results = await asyncio.gather(
        runner.await_job_completion(job.id), runner.await_job_completion(job.id)
    )

    assert results == [JobStatus.CANCELED, JobStatus.CANCELED]
    assert job.id not in runner._completion
