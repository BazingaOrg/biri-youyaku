from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
import httpx
import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobStatus
from biri_youyaku.knowledge import lifecycle
from biri_youyaku.library.repo import get_document_content, list_library
from biri_youyaku.library.search import search_library
from biri_youyaku.routes import jobs, sources
from biri_youyaku.sources.model import MediaMeta


SRT = b"1\n00:00:00,000 --> 00:00:02,000\nDistributed computing concepts\n"


@pytest.fixture
def source_app(monkeypatch, tmp_path):
    for name, value in {
        "db_path": tmp_path / "app.db",
        "upload_storage_dir": tmp_path / "imports",
        "audio_storage_dir": tmp_path / "audio",
        "summary_storage_dir": tmp_path / "summaries",
        "knowledge_storage_dir": tmp_path / "knowledge",
        "upload_min_free_bytes": 0,
        "upload_max_bytes": 1024,
        "upload_storage_max_bytes": 4096,
        "api_token": "",
        "email_enabled": False,
        "job_url_allowed_hosts": "bilibili.com,b23.tv,youtube.com,youtu.be",
    }.items():
        monkeypatch.setattr(db.settings, name, value)
    db.init_db()
    runner._registry.reset_for_tests()
    monkeypatch.setattr(sources, "resume_job", lambda *a, **kw: None)
    monkeypatch.setattr(sources, "start_job", lambda *a, **kw: None)
    monkeypatch.setattr(jobs, "start_job", lambda *a, **kw: None)
    app = FastAPI()
    app.include_router(jobs.router)
    app.include_router(sources.router)
    return app


@pytest.mark.asyncio
async def test_subtitle_import_to_readable_searchable_document(source_app, monkeypatch):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/imports", params={"filename": "lecture.srt", "title": "Lecture"}, content=SRT
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]
        job = repo.get_job(job_id)
        assert job.status == JobStatus.TRANSCRIPT_READY
        assert job.source_provider == "upload"
        assert Path(job.input_path).is_file()

        async def summarize(job, media, items, **kwargs):
            assert media.provider == "upload"
            assert items[0].text == "Distributed computing concepts"
            path = db.settings.summary_storage_dir / f"{job.id}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Distributed computing\n\nA useful lecture.")
            repo.set_summary_path(job.id, path)
            return path.read_text()

        monkeypatch.setattr(runner, "summarize", summarize)
        await runner.run_after_resume(job_id)
        assert repo.get_job(job_id).status == JobStatus.COMPLETED
        listing = list_library()
        document_id = listing["items"][0]["document_id"]
        content = get_document_content(document_id)
        assert content["document"]["provider"] == "upload"
        assert content["document"]["subtitle_source"] == "uploaded"
        assert search_library(q="Distributed", scope="all")["groups"]
        again = await client.post("/v1/imports", params={"filename": "same.srt"}, content=SRT)
        assert again.json()["job_id"] == job_id
        assert again.json()["deduped"] is True
        assert len(list(db.settings.upload_storage_dir.iterdir())) == 1
        lifecycle.soft_delete(document_id)
        assert repo.find_reusable_source("upload", job.source_id, "") is None
        lifecycle.purge_permanent(document_id, confirm_title="Lecture")
        assert not Path(job.input_path).exists()
        assert repo.get_job(job.id).input_path is None


@pytest.mark.asyncio
async def test_import_validation_does_not_leave_files_or_jobs(source_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        for filename, data in [
            ("bad.srt", b"bad"),
            ("large.srt", b"x" * 1025),
            ("x.exe", b"binary"),
        ]:
            response = await client.post("/v1/imports", params={"filename": filename}, content=data)
            assert response.status_code == 400
        assert not list(db.settings.upload_storage_dir.iterdir())
        assert repo.list_jobs() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing",
    ["email_webhook_url", "email_webhook_token", "email_default_recipient"],
)
async def test_import_email_preflight_matches_job_creation(source_app, monkeypatch, missing):
    configured = {
        "email_webhook_url": "https://worker.example",
        "email_webhook_token": "secret",
        "email_default_recipient": "reader@example.com",
    }
    monkeypatch.setattr(db.settings, "email_enabled", True)
    for name, value in configured.items():
        monkeypatch.setattr(db.settings, name, "" if name == missing else value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        job_response = await client.post(
            "/v1/jobs", json={"url": "https://www.bilibili.com/video/BV123"}
        )
        import_response = await client.post(
            "/v1/imports", params={"filename": "lecture.srt"}, content=SRT
        )
    assert job_response.status_code == 400
    assert import_response.status_code == 400
    assert import_response.json() == job_response.json()
    assert not db.settings.upload_storage_dir.exists()
    assert repo.list_jobs() == []


@pytest.mark.asyncio
async def test_import_accepts_complete_email_config(source_app, monkeypatch):
    for name, value in {
        "email_enabled": True,
        "email_webhook_url": "https://worker.example",
        "email_webhook_token": "secret",
        "email_default_recipient": "reader@example.com",
    }.items():
        monkeypatch.setattr(db.settings, name, value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/imports", params={"filename": "lecture.srt"}, content=SRT
        )
    assert response.status_code == 200, response.text
    job = repo.get_job(response.json()["job_id"])
    assert job.options.email_enabled is True
    assert Path(job.input_path).is_file()


@pytest.mark.asyncio
async def test_import_requires_auth_before_consuming_upload(source_app, monkeypatch):
    monkeypatch.setattr(db.settings, "api_token", "test-only")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/imports", params={"filename": "lecture.srt"}, content=SRT)
    assert response.status_code in {401, 403}
    assert not db.settings.upload_storage_dir.exists()


@pytest.mark.asyncio
async def test_source_jobs_dedupe_by_part_and_task_type(source_app, monkeypatch):
    async def metadata(url):
        cid = 2 if "p=2" in url else 1
        return MediaMeta(
            url=url,
            bvid="BV123",
            cid=cid,
            title="Lecture",
            author="",
            duration=2,
            source_id="BV123",
            source_part=str(cid),
        )

    monkeypatch.setattr(jobs, "fetch_source_meta", metadata)
    monkeypatch.setattr(sources, "fetch_meta", metadata)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        first = (
            await client.post("/v1/jobs", json={"url": "https://www.bilibili.com/video/BV123?p=1"})
        ).json()
        repeat = (
            await client.post("/v1/jobs", json={"url": "https://www.bilibili.com/video/BV123?p=1"})
        ).json()
        second = (
            await client.post("/v1/jobs", json={"url": "https://www.bilibili.com/video/BV123?p=2"})
        ).json()
        audio = (
            await client.post(
                "/v1/jobs",
                json={
                    "url": "https://www.bilibili.com/video/BV123?p=1",
                    "options": {"task_type": "audio"},
                },
            )
        ).json()
        assert first["job_id"] == repeat["job_id"]
        assert len({first["job_id"], second["job_id"], audio["job_id"]}) == 3
        resolved = (
            await client.get(
                "/v1/sources/resolve", params={"url": "https://www.bilibili.com/video/BV123?p=2"}
            )
        ).json()
        assert resolved["source_part"] == "2"
        assert resolved["active_job_id"] == second["job_id"]


@pytest.mark.asyncio
async def test_media_pipeline_uses_uploaded_file_without_network(source_app, monkeypatch):
    monkeypatch.setattr(
        sources,
        "capabilities",
        lambda: {"ffmpeg": True, "ffprobe": True, "asr": {"installed": True}},
    )
    monkeypatch.setattr(sources.uploads, "probe_media", AsyncMock(return_value=2.0))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=source_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/imports", params={"filename": "recording.wav"}, content=b"test media"
        )
    assert response.status_code == 200, response.text
    job = repo.get_job(response.json()["job_id"])
    from biri_youyaku.jobs import pipeline
    from biri_youyaku.modules.transcript import TranscriptItem

    async def prepare(path, destination):
        assert path == Path(job.input_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"prepared")
        return destination

    monkeypatch.setattr(pipeline.uploads, "prepare_audio", prepare)
    monkeypatch.setattr(runner, "fetch_meta", AsyncMock(side_effect=AssertionError("network")))
    monkeypatch.setattr(
        runner, "transcribe_audio", AsyncMock(return_value=[TranscriptItem(0, 2, "recording")])
    )
    monkeypatch.setattr(
        runner, "summarize", AsyncMock(side_effect=RuntimeError("LLM temporarily unavailable"))
    )
    await runner.run_until_transcript(job.id)
    failed = repo.get_job(job.id)
    assert failed.status == JobStatus.FAILED
    assert failed.transcript[0]["text"] == "recording"
    assert Path(failed.input_path).is_file()
    resumed = []
    monkeypatch.setattr(runner, "resume_job", lambda job_id, **kwargs: resumed.append(job_id))
    runner.retry_job(job.id)
    assert resumed == [job.id]
    assert repo.get_job(job.id).status == JobStatus.TRANSCRIPT_READY


@pytest.mark.asyncio
async def test_youtube_subtitle_language_survives_registration_and_resummary(source_app, monkeypatch):
    from biri_youyaku.jobs import pipeline
    from biri_youyaku.jobs.model import JobOptions
    from biri_youyaku.modules.transcript import TranscriptItem

    media = MediaMeta(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", bvid="", cid=None,
        title="Lecture", author="Speaker", duration=2, provider="youtube",
        source_id="dQw4w9WgXcQ", source_part="", subtitle_url="unused",
        subtitle_source="automatic", subtitle_language="ja",
    )
    monkeypatch.setattr(runner, "fetch_meta", AsyncMock(return_value=media))
    monkeypatch.setattr(pipeline.youtube, "transcript", AsyncMock(return_value=[TranscriptItem(0, 2, "字幕")]))
    monkeypatch.setattr(runner, "download_audio", AsyncMock(side_effect=AssertionError("subtitle-first")))

    async def summarize(job, *args, **kwargs):
        path = db.settings.summary_storage_dir / f"{job.id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Note\n字幕")
        repo.set_summary_path(job.id, path)
        return path.read_text()

    monkeypatch.setattr(runner, "summarize", summarize)
    job = repo.create_job(media.url, JobOptions(email_enabled=False))
    await runner.run_until_transcript(job.id)
    completed = repo.get_job(job.id)
    assert completed.status == JobStatus.COMPLETED
    document_id = list_library()["items"][0]["document_id"]
    document = get_document_content(document_id)["document"]
    assert document["subtitle_source"] == "automatic"
    assert document["subtitle_language"] == "ja"
    clone = repo.create_resummary_job(completed, completed.options)
    assert clone.subtitle_language == "ja"
    assert clone.source_provider == "youtube"


@pytest.mark.asyncio
async def test_uploaded_media_reaches_asr_through_real_ffmpeg(source_app, monkeypatch):
    import io
    import shutil
    import wave
    from biri_youyaku.modules.transcript import TranscriptItem

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe required")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)
    monkeypatch.setattr(db.settings, "upload_max_bytes", 100_000)
    monkeypatch.setattr(db.settings, "upload_storage_max_bytes", 1_000_000)
    monkeypatch.setattr(sources, "capabilities", lambda: {"ffmpeg": True, "ffprobe": True, "asr": {"installed": True}})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=source_app), base_url="http://test") as client:
        response = await client.post("/v1/imports", params={"filename": "recording.wav"}, content=buffer.getvalue())
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    reached_asr = []

    async def transcribe(job, audio_path, **kwargs):
        with wave.open(str(audio_path), "rb") as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1
            assert audio.getnframes() > 0
        reached_asr.append(audio_path)
        return [TranscriptItem(0, 1, "Real media preparation")]

    async def summarize(job, *args, **kwargs):
        path = db.settings.summary_storage_dir / f"{job.id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Real media preparation")
        repo.set_summary_path(job.id, path)
        return path.read_text()

    monkeypatch.setattr(runner, "transcribe_audio", transcribe)
    monkeypatch.setattr(runner, "summarize", summarize)
    await runner.run_until_transcript(job_id)
    assert reached_asr
    assert repo.get_job(job_id).status == JobStatus.COMPLETED
    assert list_library()["items"][0]["provider"] == "upload"
