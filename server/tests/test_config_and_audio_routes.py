import pytest
from fastapi import HTTPException
import httpx

from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import VideoMeta
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
    monkeypatch.setattr(config_route.settings, "llm_api_key", "secret-key")
    monkeypatch.setattr(config_route.settings, "email_enabled", True)
    monkeypatch.setattr(config_route.settings, "email_webhook_url", "https://example.test/hook")
    monkeypatch.setattr(config_route.settings, "bili_sessdata", "sess")

    response = await config_route.get_runtime_config()

    assert response == {
        "ok": True,
        "llm_configured": True,
        "email_configured": True,
        "bilibili_cookie_configured": True,
    }


@pytest.mark.asyncio
async def test_usage_endpoint_sums_requested_range(monkeypatch):
    monkeypatch.setattr(config_route.repo, "now_ms", lambda: 10 * 24 * 60 * 60 * 1000)
    monkeypatch.setattr(
        config_route.repo,
        "usage_since",
        lambda since_ms: {"since_ms": since_ms, "total_tokens": 42},
    )

    response = await config_route.get_usage("7d")

    assert response == {
        "ok": True,
        "range": "7d",
        "usage": {"since_ms": 3 * 24 * 60 * 60 * 1000, "total_tokens": 42},
    }


class FakeAsyncClient:
    response = httpx.Response(
        200,
        json={"data": [{"id": "model-b"}, {"id": "model-a"}, {"id": "model-a"}]},
    )
    last_url: str | None = None
    last_headers: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers):
        self.__class__.last_url = url
        self.__class__.last_headers = headers
        return self.__class__.response


@pytest.mark.asyncio
async def test_discover_llm_models_uses_openai_compatible_models_endpoint(monkeypatch):
    monkeypatch.setattr(config_route.httpx, "AsyncClient", FakeAsyncClient)

    response = await config_route.discover_llm_models(
        config_route.ModelDiscoveryPayload(
            llm_base_url="https://llm.example",
            llm_api_key="task-key",
        )
    )

    assert response == {"ok": True, "models": ["model-a", "model-b"]}
    assert FakeAsyncClient.last_url == "https://llm.example/v1/models"
    assert FakeAsyncClient.last_headers == {
        "Authorization": "Bearer task-key",
        "Content-Type": "application/json",
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
        await jobs_route.resume("job-1")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_preview_job_returns_meta_and_dedup(monkeypatch):
    existing = Job(
        id="job-existing",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    async def fake_fetch(url):
        return VideoMeta(
            url=url,
            bvid="BV123",
            cid=456,
            title="视频标题",
            author="UP",
            duration=12,
            subtitle_url="https://subtitle.example",
        )

    monkeypatch.setattr(
        jobs_route.bili_meta,
        "fetch",
        fake_fetch,
    )
    monkeypatch.setattr(jobs_route.repo, "find_latest_by_video", lambda bvid, cid: existing)

    response = await jobs_route.preview_job(jobs_route.PreviewJobPayload(url="https://www.bilibili.com/video/BV123"))

    assert response["ok"] is True
    assert response["meta"]["bvid"] == "BV123"
    assert response["meta"]["has_subtitle"] is True
    assert response["dedup_job_id"] == "job-existing"


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
        await jobs_route.retry("job-1")

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
async def test_replace_transcript_rejects_in_flight_job(monkeypatch):
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
        await jobs_route.replace_transcript(
            "job-1",
            jobs_route.ReplaceTranscriptPayload(
                transcript=[jobs_route.TranscriptItemPayload(start=0, end=1, text="hello")]
            ),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_replace_transcript_sets_ready_status(monkeypatch):
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=1,
        updated_at=1,
    )
    calls = {}

    async def fake_publish(job_id, event, data):
        calls["event"] = (job_id, event, data)

    monkeypatch.setattr(jobs_route.repo, "get_job", lambda job_id: job)
    monkeypatch.setattr(jobs_route.repo, "set_transcript", lambda job_id, items: calls.update(transcript=(job_id, items)))
    monkeypatch.setattr(jobs_route.repo, "set_subtitle_source", lambda job_id, source: calls.update(source=(job_id, source)))
    monkeypatch.setattr(jobs_route.repo, "clear_summary_path", lambda job_id: calls.update(clear_summary=job_id))
    monkeypatch.setattr(jobs_route.repo, "clear_error", lambda job_id: calls.update(clear_error=job_id))
    monkeypatch.setattr(jobs_route.repo, "update_status", lambda job_id, status: calls.update(status=(job_id, status)))
    monkeypatch.setattr(jobs_route.event_bus, "publish", fake_publish)

    response = await jobs_route.replace_transcript(
        "job-1",
        jobs_route.ReplaceTranscriptPayload(
            transcript=[jobs_route.TranscriptItemPayload(start=0, end=1, text="hello")]
        ),
    )

    assert response == {"ok": True}
    assert calls["transcript"][0] == "job-1"
    assert calls["transcript"][1][0].text == "hello"
    assert calls["source"] == ("job-1", "upload")
    assert calls["clear_summary"] == "job-1"
    assert calls["clear_error"] == "job-1"
    assert calls["status"] == ("job-1", JobStatus.TRANSCRIPT_READY)
    assert calls["event"] == ("job-1", "status", {"status": JobStatus.TRANSCRIPT_READY.value})


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
