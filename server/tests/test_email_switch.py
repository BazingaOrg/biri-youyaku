from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobOptions, JobStatus, video_meta_from_job
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.email import webhook
from biri_youyaku.routes import config as config_routes
from biri_youyaku.routes import jobs as job_routes


@pytest.fixture
def email_job(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(db.settings, "knowledge_register_enabled", False)
    monkeypatch.setattr(db.settings, "email_enabled", False)
    monkeypatch.setattr(db.settings, "email_webhook_url", "https://worker.example")
    monkeypatch.setattr(db.settings, "email_webhook_token", "test-token")
    monkeypatch.setattr(db.settings, "email_default_recipient", "test@example.com")
    monkeypatch.setattr(db.settings, "llm_base_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(db.settings, "llm_base_url_allowed_hosts", "api.deepseek.com")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions(email_enabled=True))
    repo.set_transcript(job.id, [TranscriptItem(start=0, end=2, text="hello")])
    summary_path = tmp_path / "summary.md"
    summary_path.write_text("# Summary", encoding="utf-8")
    repo.set_summary_path(job.id, summary_path)
    repo.update_status(job.id, JobStatus.COMPLETED)
    repo.set_email_error(job.id, "previous delivery error")
    yield repo.get_job(job.id)
    runner._registry.reset_for_tests()


@pytest.mark.asyncio
async def test_disabled_sender_never_creates_http_client(monkeypatch, email_job):
    client = Mock()
    monkeypatch.setattr(webhook, "email_client", client)

    with pytest.raises(RuntimeError, match="邮件功能已关闭"):
        await webhook.send(video_meta_from_job(email_job), "# Summary", email_job.options)

    client.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_runtime_hides_email_even_with_complete_config(email_job):
    response = await config_routes.get_runtime_config()

    assert response["email_configured"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_resend_obeys_global_switch(monkeypatch, email_job, enabled):
    monkeypatch.setattr(db.settings, "email_enabled", enabled)
    send = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(job_routes, "send_email", send)
    monkeypatch.setattr(job_routes.event_bus, "publish", publish)

    if enabled:
        assert await job_routes.resend_email(None, email_job.id) == {"ok": True}
        send.assert_awaited_once()
        assert repo.get_job(email_job.id).email_error is None
        publish.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as exc:
            await job_routes.resend_email(None, email_job.id)
        assert exc.value.status_code == 409
        assert exc.value.detail == "邮件功能已关闭"
        send.assert_not_awaited()
        publish.assert_not_awaited()
        assert repo.get_job(email_job.id).email_error == "previous delivery error"

    assert repo.read_summary(repo.get_job(email_job.id)) == "# Summary"


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,job_enabled", [(False, True), (True, False), (True, True)])
async def test_resume_email_requires_both_switches(monkeypatch, email_job, enabled, job_enabled):
    monkeypatch.setattr(db.settings, "email_enabled", enabled)
    repo.update_options(email_job.id, JobOptions(email_enabled=job_enabled))
    repo.set_email_error(email_job.id, None)
    repo.update_status(email_job.id, JobStatus.TRANSCRIPT_READY)
    send = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(runner, "summarize", AsyncMock(return_value="# Summary"))
    monkeypatch.setattr(runner, "send_email", send)
    monkeypatch.setattr(runner.event_bus, "publish", publish)

    await runner.run_after_resume(email_job.id)

    completed = repo.get_job(email_job.id)
    assert completed.status == JobStatus.COMPLETED
    assert completed.email_error is None
    assert repo.read_summary(completed) == "# Summary"
    statuses = [
        call.args[2].get("status") for call in publish.await_args_list if call.args[1] == "status"
    ]
    if enabled and job_enabled:
        send.assert_awaited_once()
        assert JobStatus.EMAILING.value in statuses
    else:
        send.assert_not_awaited()
        assert JobStatus.EMAILING.value not in statuses


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "resummarize", "resume", "retry"])
async def test_task_requests_cannot_override_disabled_email(monkeypatch, email_job, action):
    monkeypatch.setattr(job_routes, "start_job", Mock())
    monkeypatch.setattr(job_routes, "resume_job", Mock())
    monkeypatch.setattr(job_routes, "retry_job", Mock())
    options = job_routes.JobOptionsPayload(email_enabled=True)

    if action == "create":
        from dataclasses import replace

        media = replace(video_meta_from_job(email_job), bvid="BV123", cid=1)
        monkeypatch.setattr(job_routes, "fetch_source_meta", AsyncMock(return_value=media))
        response = await job_routes.create_job(
            None, job_routes.CreateJobPayload(url=email_job.url, options=options, dedupe=False)
        )
        job_id = response["job_id"]
    elif action == "resummarize":
        response = await job_routes.resummarize(
            None, email_job.id, job_routes.ResummarizeJobPayload(options=options)
        )
        job_id = response["job_id"]
    else:
        job_id = email_job.id
        if action == "resume":
            repo.update_status(job_id, JobStatus.TRANSCRIPT_READY)
            await job_routes.resume(None, job_id, job_routes.ResumeJobPayload(options=options))
        else:
            repo.update_status(job_id, JobStatus.FAILED)
            await job_routes.retry(None, job_id, job_routes.RetryJobPayload(options=options))

    assert repo.get_job(job_id).options.email_enabled is False
