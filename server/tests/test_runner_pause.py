import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


async def _fake_summarize(job, video_meta, items, *, llm_api_key=None, on_chunk=None, on_usage=None, on_segment=None):
    assert llm_api_key == "task-key"
    assert items[0].text == "hello"
    if on_chunk is not None:
        await on_chunk("summary")
    if on_usage is not None:
        await on_usage({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
    return "summary"


async def _fake_generate_tags(job, summary_md, *, llm_api_key=None):
    return ["测试标签"]


@pytest.mark.asyncio
async def test_runner_auto_continues_transcript_to_completed(monkeypatch, tmp_path):
    """拿到字幕后服务端自动续跑总结，不依赖前端 /resume —— 单条 task 直达 COMPLETED。"""
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

    async def fake_summarize(job, video_meta, items, **kwargs):
        result = await _fake_summarize(job, video_meta, items, **kwargs)
        summary_path = tmp_path / f"{job.id}.md"
        summary_path.write_text("summary", encoding="utf-8")
        repo.set_summary_path(job.id, summary_path)
        return result

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "fetch_meta", fake_fetch_meta)
    monkeypatch.setattr(runner, "fetch_platform_transcript", fake_fetch_platform_transcript)
    monkeypatch.setattr(runner, "summarize", fake_summarize)
    monkeypatch.setattr(runner, "generate_tags", _fake_generate_tags)

    runner.start_job(job.id, llm_api_key="task-key")
    await runner._registry.tasks[job.id]

    completed = repo.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED  # 无需手动 resume
    assert repo.read_summary(completed) == "summary"
    assert completed.tags == ["测试标签"]
    assert job.id not in runner._registry.tasks


@pytest.mark.asyncio
async def test_resume_job_summarizes_transcript_ready(monkeypatch, tmp_path):
    """/resume 路径（force_asr 改选项 / 重启恢复用）：TRANSCRIPT_READY → 总结 → COMPLETED。"""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions(email_enabled=False))
    repo.set_transcript(job.id, [TranscriptItem(start=0, end=2, text="hello")])
    repo.update_status(job.id, JobStatus.TRANSCRIPT_READY)

    async def fake_publish(job_id, event, data):
        return None

    async def fake_summarize(job, video_meta, items, **kwargs):
        result = await _fake_summarize(job, video_meta, items, **kwargs)
        summary_path = tmp_path / f"{job.id}.md"
        summary_path.write_text("summary", encoding="utf-8")
        repo.set_summary_path(job.id, summary_path)
        return result

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "summarize", fake_summarize)
    monkeypatch.setattr(runner, "generate_tags", _fake_generate_tags)

    runner.resume_job(job.id, llm_api_key="task-key")
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
