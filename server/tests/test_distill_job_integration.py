import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, runner
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


@pytest.mark.asyncio
async def test_distill_task_type_stops_at_completed_without_summary(monkeypatch, tmp_path):
    """task_type="distill" 的 job 走到 TRANSCRIPT_READY 该直接收尾：复用 COMPLETED
    终态（镜像 task_type=="audio" 的提前收尾写法），不总结、不生成标签、不发邮件。"""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job(
        "https://www.bilibili.com/video/BV123",
        JobOptions(task_type="distill", email_enabled=False),
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

    def fail_if_summarize_called(*args, **kwargs):
        raise AssertionError("distill 任务不应该走到 summarize")

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "fetch_meta", fake_fetch_meta)
    monkeypatch.setattr(runner, "fetch_platform_transcript", fake_fetch_platform_transcript)
    monkeypatch.setattr(runner, "summarize", fail_if_summarize_called)
    monkeypatch.setattr(runner, "generate_tags", fail_if_summarize_called)

    runner.start_job(job.id)
    await runner._registry.tasks[job.id]

    completed = repo.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert completed.summary_path is None
    assert completed.transcript == [{"start": 0.0, "end": 2.0, "text": "hello"}]
    assert job.id not in runner._registry.tasks


@pytest.mark.asyncio
async def test_run_after_resume_also_short_circuits_distill_job(monkeypatch, tmp_path):
    """崩溃窗口兜底：进程恰好死在 TRANSCRIPT_READY→COMPLETED 之间，重启后
    recover_unfinished_jobs() 会把它当普通 TRANSCRIPT_READY 任务走 resume_job()。
    这里直接测 run_after_resume 对 distill job 同样提前收尾，不误总结。"""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    runner._registry.reset_for_tests()
    db.init_db()
    job = repo.create_job(
        "https://www.bilibili.com/video/BV123",
        JobOptions(task_type="distill", email_enabled=False),
    )
    repo.set_transcript(job.id, [TranscriptItem(start=0, end=2, text="hello")])
    repo.update_status(job.id, JobStatus.TRANSCRIPT_READY)

    async def fake_publish(job_id, event, data):
        return None

    def fail_if_summarize_called(*args, **kwargs):
        raise AssertionError("distill 任务不应该走到 summarize")

    monkeypatch.setattr(runner.event_bus, "publish", fake_publish)
    monkeypatch.setattr(runner, "summarize", fail_if_summarize_called)
    monkeypatch.setattr(runner, "generate_tags", fail_if_summarize_called)

    runner.resume_job(job.id)
    await runner._registry.tasks[job.id]

    completed = repo.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert completed.summary_path is None


def test_list_jobs_excludes_distill_task_type_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    summary_job = repo.create_job(
        "https://www.bilibili.com/video/BV1", JobOptions(task_type="summary")
    )
    distill_job = repo.create_job(
        "https://www.bilibili.com/video/BV2", JobOptions(task_type="distill")
    )

    listed_ids = {job.id for job in repo.list_jobs(limit=50)}

    assert summary_job.id in listed_ids
    assert distill_job.id not in listed_ids
    # 但按 id 仍然可以直接查到（detail 接口不受影响）。
    assert repo.get_job(distill_job.id) is not None


def test_list_jobs_cursor_pagination_still_excludes_distill(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    repo.create_job("https://www.bilibili.com/video/BV1", JobOptions(task_type="summary"))
    distill_job = repo.create_job(
        "https://www.bilibili.com/video/BV2", JobOptions(task_type="distill")
    )

    first_page = repo.list_jobs(limit=50)
    cursor = first_page[-1].created_at + 1  # 往后翻一页，覆盖 cursor 分支
    next_page = repo.list_jobs(limit=50, cursor=cursor)

    assert distill_job.id not in {job.id for job in first_page}
    assert all(job.id != distill_job.id for job in next_page)


def test_bvid_dedup_queries_exclude_distill_jobs_by_default(monkeypatch, tmp_path):
    """distill job 是 COMPLETED 但只有转写没有总结：普通去重与 UP 页「已总结」标记
    都不该把它当成已有总结；蒸馏编排器复用转写时用 include_distill=True 仍能拿到。"""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    distill_job = repo.create_job(
        "https://www.bilibili.com/video/BV9", JobOptions(task_type="distill")
    )
    repo.update_meta(
        distill_job.id, bvid="BV9", cid=1, title="t", author="a", duration=10.0, mid=42
    )
    repo.update_status(distill_job.id, JobStatus.COMPLETED)

    # 普通创建流程的去重：默认查不到 distill job。
    assert repo.find_completed_by_bvid("BV9") is None
    # 蒸馏编排器复用转写：显式包含时能查到。
    reused = repo.find_completed_by_bvid("BV9", include_distill=True)
    assert reused is not None and reused.id == distill_job.id
    # UP 页「已总结」标记：distill job 不参与。
    assert "BV9" not in repo.summary_status_for_bvids(["BV9"])

    # 同 bvid 存在真正的总结任务时，标记回归正常。
    summary_job = repo.create_job(
        "https://www.bilibili.com/video/BV9", JobOptions(task_type="summary")
    )
    repo.update_meta(
        summary_job.id, bvid="BV9", cid=1, title="t", author="a", duration=10.0, mid=42
    )
    repo.update_status(summary_job.id, JobStatus.COMPLETED)
    status = repo.summary_status_for_bvids(["BV9"])
    assert status["BV9"]["job_id"] == summary_job.id
