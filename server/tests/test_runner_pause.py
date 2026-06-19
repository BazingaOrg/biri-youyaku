import asyncio

import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


@pytest.mark.asyncio
async def test_runner_pauses_at_transcript_ready_then_resumes(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job(
        "https://www.bilibili.com/video/BV123",
        JobOptions(email_enabled=False),
    )

    async def fake_publish(job_id, event, data):
        return None

    async def fake_fetch_meta(url):
        return VideoMeta(
            url=url,
            bvid="BV123",
            cid=1,
            title="Title",
            author="Author",
            duration=10,
            subtitle_url="https://example.com/subtitle.json",
        )

    async def fake_fetch_platform_transcript(job, video_meta):
        repo.set_subtitle_source(job.id, "platform")
        return [TranscriptItem(start=0, end=2, text="hello")]

    async def fake_summarize(job, video_meta, items, *, llm_api_key=None, on_chunk=None, on_usage=None, on_segment=None):
        assert llm_api_key == "task-key"
        assert items[0].text == "hello"
        if on_chunk is not None:
            await on_chunk("summary")
        if on_usage is not None:
            await on_usage({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
        summary_path = tmp_path / f"{job.id}.md"
        summary_path.write_text("summary", encoding="utf-8")
        repo.set_summary_path(job.id, summary_path)
        return "summary"

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "fetch_meta", fake_fetch_meta)
    monkeypatch.setattr(runner, "fetch_platform_transcript", fake_fetch_platform_transcript)
    monkeypatch.setattr(runner, "summarize", fake_summarize)

    runner.start_job(job.id, llm_api_key="task-key")
    await runner._registry.tasks[job.id]
    await asyncio.sleep(0)

    paused = repo.get_job(job.id)
    assert paused is not None
    assert paused.status == JobStatus.TRANSCRIPT_READY
    assert job.id not in runner._registry.tasks

    runner.resume_job(job.id)
    await runner._registry.tasks[job.id]

    completed = repo.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert repo.read_summary(completed) == "summary"


@pytest.mark.asyncio
async def test_audio_only_job_clears_cached_llm_key(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job(
        "https://www.bilibili.com/video/BV123",
        JobOptions(task_type="audio"),
    )

    async def fake_publish(job_id, event, data):
        return None

    async def fake_fetch_meta(url):
        return VideoMeta(
            url=url,
            bvid="BV123",
            cid=1,
            title="Title",
            author="Author",
            duration=10,
        )

    async def fake_download_audio(job, video_meta, *, on_progress=None):
        if on_progress is not None:
            await on_progress({"status": "finished", "percent": 100})
        audio_path = tmp_path / f"{job.id}.wav"
        audio_path.write_text("audio", encoding="utf-8")
        repo.set_audio_path(job.id, audio_path)
        return audio_path

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "fetch_meta", fake_fetch_meta)
    monkeypatch.setattr(runner, "download_audio", fake_download_audio)

    runner.start_job(job.id, llm_api_key="task-key")
    await runner._registry.tasks[job.id]

    completed = repo.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert job.id not in runner._registry.llm_api_keys
