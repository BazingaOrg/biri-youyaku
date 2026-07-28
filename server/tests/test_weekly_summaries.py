import asyncio

import pytest

from biri_youyaku import db
from biri_youyaku.db import connect
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.routes.weekly_summaries import _serialize
from biri_youyaku.weekly import orchestrator, repo


MONDAY_MS = 1785196800000  # 2026-07-27T00:00:00+08:00


@pytest.fixture(autouse=True)
def _reset_weekly_orchestrator():
    orchestrator.prepare_startup()
    orchestrator._tasks.clear()
    orchestrator._task_tokens.clear()
    yield
    orchestrator.prepare_startup()
    orchestrator._tasks.clear()
    orchestrator._task_tokens.clear()


def _completed_with_summary(tmp_path, *, title="本周视频"):
    job = jobs_repo.create_job("https://example.test/video", JobOptions(email_enabled=False))
    jobs_repo.update_meta(job.id, bvid="BVweekly", cid=None, title=title, author="作者", duration=1)
    path = tmp_path / f"{job.id}.md"
    path.write_text("## TL;DR\n内容", encoding="utf-8")
    jobs_repo.set_summary_path(job.id, path)
    jobs_repo.update_status(job.id, JobStatus.COMPLETED)
    return jobs_repo.get_job(job.id)


def test_empty_week_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    assert orchestrator.request_generation("2026-07-27") is False
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "EMPTY"


def test_missing_week_response_always_has_timezone_and_generated_at(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    response = _serialize("2026-07-27")

    assert response["timezone"] == "Asia/Shanghai"
    assert response["generated_at"] is None


def test_empty_week_becomes_generatable_after_a_source_arrives(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()

    assert orchestrator.request_generation("2026-07-27") is False
    _completed_with_summary(tmp_path)
    stored, sources, _ = repo.state_for_week("2026-07-27")
    assert sources
    assert stored is not None
    assert stored.status == "STALE"


def test_generation_request_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)

    assert repo.begin_generation("2026-07-27", fingerprint_value="same") is True
    assert repo.begin_generation("2026-07-27", fingerprint_value="same") is False


def test_restart_can_take_over_persisted_generation_without_old_write(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    job = _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    fingerprint_value = repo.fingerprint(sources)

    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=fingerprint_value, generation_token="old"
    )
    assert (
        repo.begin_generation(
            "2026-07-27", fingerprint_value=fingerprint_value, generation_token="new"
        )
        is False
    )
    with connect() as connection:
        connection.execute(
            "UPDATE weekly_summaries SET generation_expires_at = ? WHERE week_start = ?",
            (MONDAY_MS, "2026-07-27"),
        )
    assert repo.begin_generation(
        "2026-07-27",
        fingerprint_value=fingerprint_value,
        generation_token="new",
    )
    assert (
        repo.save_completed(
            "2026-07-27",
            fingerprint_value=fingerprint_value,
            sources=sources,
            content="过期结果",
            references=[],
            generation_token="old",
        )
        is False
    )
    assert repo.save_failed("2026-07-27", "过期错误", generation_token="old") is False
    assert (
        repo.save_completed(
            "2026-07-27",
            fingerprint_value=fingerprint_value,
            sources=sources,
            content="新结果",
            references=[{"job_id": job.id}],
            generation_token="new",
        )
        is True
    )
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert (stored.status, stored.content) == ("COMPLETED", "新结果")


def test_old_source_snapshot_cannot_stale_new_generation_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    fingerprint_value = repo.fingerprint(sources)
    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=fingerprint_value, generation_token="old"
    )
    with connect() as connection:
        connection.execute(
            "UPDATE weekly_summaries SET generation_expires_at = ? WHERE week_start = ?",
            (MONDAY_MS, "2026-07-27"),
        )
    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=fingerprint_value, generation_token="new"
    )

    assert repo.mark_stale("2026-07-27", generation_token="old") is False
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "GENERATING"
    assert stored.generation_token == "new"


def test_deleted_source_between_generation_and_save_cannot_be_revived(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    job = _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    fingerprint_value = repo.fingerprint(sources)
    assert repo.begin_generation(
        "2026-07-27",
        fingerprint_value=fingerprint_value,
        generation_token="generation",
        sources=sources,
    )
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        assert repo.mark_stale_for_job_ids([job.id], connection=connection) == 1
        assert jobs_repo.delete_jobs_by_ids([job.id], connection=connection) == 1
        connection.commit()

    assert (
        repo.save_completed(
            "2026-07-27",
            fingerprint_value=fingerprint_value,
            sources=sources,
            content="不应保存",
            references=[{"job_id": job.id}],
            generation_token="generation",
        )
        is False
    )
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "STALE"


def test_new_source_after_precheck_stales_old_generation_before_save(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path, title="原来源")
    sources = repo.sources_for_week("2026-07-27")
    fingerprint_value = repo.fingerprint(sources)
    assert repo.begin_generation(
        "2026-07-27",
        fingerprint_value=fingerprint_value,
        generation_token="old-generation",
        sources=sources,
    )
    _completed_with_summary(tmp_path, title="新来源")

    assert (
        repo.save_completed(
            "2026-07-27",
            fingerprint_value=fingerprint_value,
            sources=sources,
            content="旧内容",
            references=[],
            generation_token="old-generation",
        )
        is False
    )
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "STALE"


def test_queued_old_owner_cannot_renew_or_spend_after_takeover(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    fingerprint_value = repo.fingerprint(sources)
    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=fingerprint_value, generation_token="queued-old"
    )
    with connect() as connection:
        connection.execute(
            "UPDATE weekly_summaries SET generation_expires_at = ? WHERE week_start = ?",
            (MONDAY_MS, "2026-07-27"),
        )
    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=fingerprint_value, generation_token="new-owner"
    )

    assert repo.renew_generation_lease("2026-07-27", "queued-old") is False
    assert repo.renew_generation_lease("2026-07-27", "new-owner") is True


@pytest.mark.asyncio
async def test_same_process_generation_is_single_flight_and_shutdown_marks_stale(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)
    orchestrator.prepare_startup()
    entered = asyncio.Event()

    async def wait_for_completion(*_args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(orchestrator, "_run", wait_for_completion)
    assert orchestrator.request_generation("2026-07-27") is True
    await entered.wait()
    assert orchestrator.request_generation("2026-07-27", refresh=True) is False

    await orchestrator.shutdown()
    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "STALE"
    assert not orchestrator._tasks


@pytest.mark.asyncio
async def test_cancelled_generation_does_not_late_write_failed_status(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)
    orchestrator.prepare_startup()
    started = asyncio.Event()

    async def cancellable_run(*_args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(orchestrator, "_run", cancellable_run)
    assert orchestrator.request_generation("2026-07-27") is True
    await started.wait()
    await orchestrator.shutdown()

    stored = repo.get("2026-07-27")
    assert stored is not None
    assert stored.status == "STALE"
    assert stored.error is None


def test_model_references_must_be_source_whitelisted():
    with pytest.raises(ValueError, match="不允许"):
        orchestrator._parse('{"summary":"x","references":[{"job_id":"not-input"}]}', {"known"})
    summary, refs = orchestrator._parse(
        '{"summary":"x","references":[{"job_id":"known"}]}', {"known"}
    )
    assert summary == "x"
    assert refs == ["known"]
    with pytest.raises(ValueError, match="最多 5"):
        orchestrator._parse(
            '{"summary":"x","references":['
            '{"job_id":"known"},{"job_id":"known"},{"job_id":"known"},'
            '{"job_id":"known"},{"job_id":"known"},{"job_id":"known"}]}',
            {"known"},
        )


@pytest.mark.asyncio
async def test_expired_generation_is_staled_when_read_and_can_be_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    assert repo.begin_generation(
        "2026-07-27", fingerprint_value=repo.fingerprint(sources), generation_token="expired"
    )
    with connect() as connection:
        connection.execute(
            "UPDATE weekly_summaries SET generation_expires_at = ? WHERE week_start = ?",
            (MONDAY_MS, "2026-07-27"),
        )

    response = _serialize("2026-07-27")

    assert response["status"] == "STALE"
    entered = asyncio.Event()

    async def wait_for_retry(*_args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(orchestrator, "_run", wait_for_retry)
    orchestrator.prepare_startup()
    assert orchestrator.request_generation("2026-07-27") is True
    await entered.wait()
    await orchestrator.shutdown()


def test_deleting_source_marks_weekly_summary_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs_repo, "now_ms", lambda: MONDAY_MS + 1)
    db.init_db()
    job = _completed_with_summary(tmp_path)
    sources = repo.sources_for_week("2026-07-27")
    repo.begin_generation("2026-07-27", fingerprint_value=repo.fingerprint(sources))
    repo.save_completed(
        "2026-07-27",
        fingerprint_value=repo.fingerprint(sources),
        sources=sources,
        content="周总结",
        references=[],
    )

    assert repo.affected_count_for_job_ids([job.id]) == 1
    assert repo.mark_stale_for_job_ids([job.id]) == 1
    assert repo.get("2026-07-27").status == "STALE"
