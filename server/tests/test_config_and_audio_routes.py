import pytest
from fastapi import HTTPException

from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.routes import config as config_route
from biri_youyaku.routes import jobs as jobs_route


@pytest.mark.asyncio
async def test_config_defaults_do_not_expose_secret_values(monkeypatch):
    monkeypatch.setattr(config_route.settings, "llm_api_key", "secret-key")
    monkeypatch.setattr(config_route.settings, "email_webhook_token", "secret-token")

    response = await config_route.get_config_defaults()

    defaults = response["defaults"]
    assert defaults["llm_api_key_configured"] is True
    assert "llm_api_key" not in defaults
    assert "email_webhook_token" not in defaults


@pytest.mark.asyncio
async def test_runtime_config_returns_only_booleans(monkeypatch):
    monkeypatch.setattr(config_route.settings, "api_token", "")
    monkeypatch.setattr(config_route.settings, "llm_api_key", "secret-key")
    monkeypatch.setattr(config_route.settings, "email_enabled", True)
    monkeypatch.setattr(config_route.settings, "email_webhook_url", "https://example.test/hook")
    monkeypatch.setattr(config_route.settings, "email_webhook_token", "secret-token")
    monkeypatch.setattr(config_route.settings, "email_default_recipient", "you@example.com")
    monkeypatch.setattr(config_route.settings, "bili_sessdata", "sess")

    response = await config_route.get_runtime_config()

    assert response == {
        "ok": True,
        "auth_mode": "none",
        "llm_configured": True,
        "email_configured": True,
        "bilibili_cookie_configured": True,
    }


@pytest.mark.asyncio
async def test_download_audio_returns_conflict_when_job_has_no_audio(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.download_audio("job-1")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "该任务没有可下载音频"


@pytest.mark.asyncio
async def test_resume_rejects_non_transcript_ready_job(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.PENDING,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.resume(None, "job-1")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_runtime_config_requires_email_recipient(monkeypatch):
    monkeypatch.setattr(config_route.settings, "email_enabled", True)
    monkeypatch.setattr(config_route.settings, "email_webhook_url", "https://example.test/hook")
    monkeypatch.setattr(config_route.settings, "email_webhook_token", "secret-token")
    monkeypatch.setattr(config_route.settings, "email_default_recipient", "")

    response = await config_route.get_runtime_config()

    assert response["email_configured"] is False


@pytest.mark.asyncio
async def test_runtime_config_requires_email_token(monkeypatch):
    monkeypatch.setattr(config_route.settings, "email_enabled", True)
    monkeypatch.setattr(config_route.settings, "email_webhook_url", "https://example.test/hook")
    monkeypatch.setattr(config_route.settings, "email_webhook_token", "")
    monkeypatch.setattr(config_route.settings, "email_default_recipient", "you@example.com")

    response = await config_route.get_runtime_config()

    assert response["email_configured"] is False


@pytest.mark.asyncio
async def test_create_job_dedupes_completed_bvid(monkeypatch):
    existing = Job(
        id="job-existing",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    started = {}
    monkeypatch.setattr(jobs_route.repo, "find_completed_by_bvid", lambda bvid: existing if bvid == "BV123" else None)
    monkeypatch.setattr(jobs_route, "start_job", lambda job_id, llm_api_key=None: started.update(id=job_id))

    response = await jobs_route.create_job(
        None, jobs_route.CreateJobPayload(url="https://www.bilibili.com/video/BV123")
    )

    # 命中已完成 → 复用旧任务、不新建、不启动 runner。
    assert response == {"ok": True, "job_id": "job-existing", "deduped": True}
    assert "id" not in started


@pytest.mark.asyncio
async def test_create_job_can_bypass_dedupe(monkeypatch):
    existing = Job(
        id="job-existing",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    created = Job(
        id="job-new",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.PENDING,
        options=JobOptions(),
        created_at=2,
        updated_at=2,
    )
    calls = {}
    monkeypatch.setattr(jobs_route.repo, "find_completed_by_bvid", lambda bvid: existing if bvid == "BV123" else None)
    monkeypatch.setattr(jobs_route.repo, "count_jobs_excluding_status", lambda statuses: 0)
    monkeypatch.setattr(jobs_route.repo, "create_job", lambda url, options, option_overrides=None: created)
    monkeypatch.setattr(jobs_route, "start_job", lambda job_id, llm_api_key=None: calls.update(started=job_id))

    response = await jobs_route.create_job(
        None, jobs_route.CreateJobPayload(url="https://www.bilibili.com/video/BV123", dedupe=False)
    )

    assert response == {"ok": True, "job_id": "job-new"}
    assert calls == {"started": "job-new"}


@pytest.mark.asyncio
async def test_resummarize_creates_transcript_ready_job(monkeypatch):
    source = Job(
        id="job-source",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
        transcript=[{"start": 0, "end": 1, "text": "hello"}],
    )
    created = Job(
        id="job-new",
        url=source.url,
        status=JobStatus.TRANSCRIPT_READY,
        options=JobOptions(),
        created_at=2,
        updated_at=2,
        transcript=source.transcript,
    )
    calls = {}

    def create_resummary(job, options, option_overrides=None):
        calls["source"] = job
        return created

    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: source if job_id == "job-source" else None)
    monkeypatch.setattr(jobs_route.repo, "count_jobs_excluding_status", lambda statuses: 0)
    monkeypatch.setattr(jobs_route.repo, "create_resummary_job", create_resummary)
    monkeypatch.setattr(jobs_route, "resume_job", lambda job_id, llm_api_key=None: calls.update(resumed=job_id))

    response = await jobs_route.resummarize(
        None, "job-source", jobs_route.ResummarizeJobPayload(options=jobs_route.JobOptionsPayload(task_type="summary"))
    )

    assert response == {"ok": True, "job_id": "job-new"}
    assert calls["source"] is source
    assert calls["resumed"] == "job-new"


@pytest.mark.asyncio
async def test_resummarize_rejects_job_without_transcript(monkeypatch):
    source = Job(
        id="job-source",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: source)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.resummarize(None, "job-source")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_resume_updates_summary_options_before_start(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.TRANSCRIPT_READY,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    calls = {}
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(
        jobs_route.repo,
        "update_options",
        lambda job_id, options, option_overrides=None: calls.update(
            job_id=job_id,
            options=options,
            option_overrides=option_overrides,
        ),
    )
    monkeypatch.setattr(
        jobs_route,
        "resume_job",
        lambda job_id, llm_api_key=None: calls.update(started=job_id, llm_api_key=llm_api_key),
    )

    response = await jobs_route.resume(
        None,
        "job-1",
        jobs_route.ResumeJobPayload(
            options=jobs_route.JobOptionsPayload(
                llm_model="model-b",
                email_enabled=False,
                llm_api_key="task-key",
            )
        ),
    )

    assert response == {"ok": True}
    assert calls["job_id"] == "job-1"
    assert calls["options"].llm_model == "model-b"
    assert calls["options"].email_enabled is False
    assert calls["option_overrides"] == {
        "email_enabled": False,
        "llm_model": "model-b",
    }
    assert calls["started"] == "job-1"
    assert calls["llm_api_key"] == "task-key"


@pytest.mark.asyncio
async def test_resume_rejects_disallowed_llm_base_url(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.TRANSCRIPT_READY,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(jobs_route.settings, "llm_base_url_allowed_hosts", "api.deepseek.com")

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.resume(
            None,
            "job-1",
            jobs_route.ResumeJobPayload(
                options=jobs_route.JobOptionsPayload(llm_base_url="http://127.0.0.1:11434/v1")
            ),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_retry_rejects_non_failed_job(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.retry(None, "job-1")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_retry_updates_options_and_starts_runner(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.FAILED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    calls = {}
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(
        jobs_route.repo,
        "update_options",
        lambda job_id, options, option_overrides=None: calls.update(
            job_id=job_id,
            options=options,
            option_overrides=option_overrides,
        ),
    )
    monkeypatch.setattr(
        jobs_route,
        "retry_job",
        lambda job_id, llm_api_key=None: calls.update(started=job_id, llm_api_key=llm_api_key),
    )

    response = await jobs_route.retry(
        None,
        "job-1",
        jobs_route.RetryJobPayload(
            options=jobs_route.JobOptionsPayload(llm_model="model-b", llm_api_key="task-key")
        ),
    )

    assert response == {"ok": True}
    assert calls["job_id"] == "job-1"
    assert calls["options"].llm_model == "model-b"
    assert calls["option_overrides"] == {"llm_model": "model-b"}
    assert calls["started"] == "job-1"
    assert calls["llm_api_key"] == "task-key"


@pytest.mark.asyncio
async def test_retry_rejects_disallowed_llm_base_url(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.FAILED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(jobs_route.settings, "llm_base_url_allowed_hosts", "api.deepseek.com")

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.retry(
            None,
            "job-1",
            jobs_route.RetryJobPayload(
                options=jobs_route.JobOptionsPayload(llm_base_url="https://example.test/v1")
            ),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_rejects_in_flight_job(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.SUMMARIZING,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs_route.delete("job-1")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_all_reports_deleted_and_skipped_counts(monkeypatch):
    monkeypatch.setattr(jobs_route.repo, "count_jobs_excluding_status", lambda statuses: 2)
    monkeypatch.setattr(jobs_route.repo, "list_jobs_by_status", lambda statuses: [])
    monkeypatch.setattr(jobs_route.repo, "delete_jobs_by_status", lambda statuses: 3)

    response = await jobs_route.delete_all()

    assert response == {"ok": True, "deleted_count": 3, "skipped_count": 2}


@pytest.mark.asyncio
async def test_delete_removes_terminal_job_and_files(monkeypatch, tmp_path):
    audio_path = tmp_path / "job-1.wav"
    summary_path = tmp_path / "job-1.md"
    audio_path.write_text("audio", encoding="utf-8")
    summary_path.write_text("summary", encoding="utf-8")
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
        audio_path=str(audio_path),
        summary_path=str(summary_path),
    )
    calls = {}
    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(jobs_route.repo, "delete_job", lambda job_id: calls.setdefault("deleted", job_id) and 1)

    response = await jobs_route.delete("job-1")

    assert response == {"ok": True}
    assert calls["deleted"] == "job-1"
    assert not audio_path.exists()
    assert not summary_path.exists()
