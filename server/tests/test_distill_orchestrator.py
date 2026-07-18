import asyncio

import pytest

from biri_youyaku import db
from biri_youyaku.distill import orchestrator
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.distill.model import DistillRunStatus
from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.modules.bilibili import space
from biri_youyaku.modules.storage import distill as distill_storage


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "distill.db")
    db.init_db()
    monkeypatch.setattr(distill_storage.settings, "distill_storage_dir", tmp_path / "distill")


def _up_video_page(mid: int, videos: list[space.UpVideo]) -> space.UpVideoPage:
    return space.UpVideoPage(
        mid=mid, author="蒸馏UP", total=len(videos), page=1, page_size=30, videos=videos
    )


@pytest.mark.asyncio
async def test_pipeline_happy_path_reuses_transcript_skips_existing_and_degrades_dynamics(
    monkeypatch, tmp_path
):
    """一次跑通三条 spec 要求的路径：
    - BV_OLD 已有 videos/BV_OLD.md（断点续跑）→ 完全跳过，不查 job、不调 LLM。
    - BV_NEW 没有 transcript，但有已完成 job 可复用 → 不新建 job（否则 start_job
      断言会失败），走观点提取写出新文件。
    - 动态接口失败 → dynamics_status 降级为 unavailable，整个 run 仍然 COMPLETED。
    """
    _setup(monkeypatch, tmp_path)
    run = await orchestrator.start_run(mid=42, video_limit=10)
    # start_run 内部已经 spawn 了后台 task；这里改成直接手动跑一遍 pipeline 更好控制，
    # 先取消掉后台 task 避免它和下面手动调用的 _run_pipeline 打架。
    bg_task = orchestrator._active_tasks.pop(run.id, None)
    if bg_task is not None:
        bg_task.cancel()

    distill_storage.save_video(42, "BV_OLD", "---\ntitle: 老视频\n---\n\n已有内容")

    videos = [
        space.UpVideo(bvid="BV_OLD", title="老视频", cover="", pubdate=100, duration=60, play=1),
        space.UpVideo(bvid="BV_NEW", title="新视频", cover="", pubdate=200, duration=90, play=2),
    ]

    async def fake_fetch_up_videos(mid, *, page=1, keyword="", order="pubdate"):
        assert mid == 42
        return _up_video_page(mid, videos)

    async def fake_fetch_all_dynamics(mid, **kwargs):
        raise RuntimeError("模拟频控/网络失败")

    reused_job = Job(
        id="reused-job",
        url="https://www.bilibili.com/video/BV_NEW",
        status=JobStatus.COMPLETED,
        options=JobOptions(),
        created_at=0,
        updated_at=0,
        transcript=[{"start": 0.0, "end": 1.0, "text": "这是可复用的转写文本"}],
    )

    def fake_find_completed_by_bvid(bvid, *, include_distill=False):
        assert bvid == "BV_NEW"  # BV_OLD 因为文件已存在，压根不该走到这里
        assert include_distill is True  # 编排器复用转写时应显式包含 distill job
        return reused_job

    def fail_if_start_job_called(job_id, *, llm_api_key=None):
        raise AssertionError("BV_NEW 应该复用已有 transcript，不应该新建 job")

    extract_calls = []

    async def fake_extract_video_viewpoints(title, transcript_text, language):
        extract_calls.append((title, transcript_text, language))
        return "## 观点与立场\n- 测试观点。原话：「示例」"

    monkeypatch.setattr(orchestrator.space_module, "fetch_up_videos", fake_fetch_up_videos)
    monkeypatch.setattr(orchestrator.dynamic_module, "fetch_all_dynamics", fake_fetch_all_dynamics)
    monkeypatch.setattr(
        orchestrator.job_repo, "find_completed_by_bvid", fake_find_completed_by_bvid
    )
    monkeypatch.setattr(orchestrator, "start_job", fail_if_start_job_called)
    monkeypatch.setattr(orchestrator, "extract_video_viewpoints", fake_extract_video_viewpoints)

    await orchestrator._run_pipeline(run.id)

    final = distill_repo.get_run(run.id)
    assert final is not None
    assert final.status == DistillRunStatus.COMPLETED
    assert final.dynamics_status == "unavailable"
    assert final.up_name == "蒸馏UP"
    assert final.counters["videos_total"] == 2
    assert final.counters["videos_transcribed"] == 2
    assert final.counters["videos_extracted"] == 2
    assert final.counters["videos_failed"] == 0

    # BV_OLD 原样保留，没被重新覆盖。
    assert distill_storage.read_video(42, "BV_OLD") == "---\ntitle: 老视频\n---\n\n已有内容"
    # BV_NEW 是新提取出来的，frontmatter 带上了列表接口给的元数据。
    new_content = distill_storage.read_video(42, "BV_NEW")
    assert new_content is not None
    assert "bvid: BV_NEW" in new_content
    assert "pubdate: 200" in new_content
    assert "play: 2" in new_content
    assert "测试观点" in new_content

    assert len(extract_calls) == 1
    assert extract_calls[0][0] == "新视频"
    assert extract_calls[0][1] == "这是可复用的转写文本"

    manifest = distill_storage.read_manifest(42)
    assert manifest is not None
    assert manifest["videos"]["extracted"] == 2
    corpus = distill_storage.read_corpus(42)
    assert corpus is not None
    assert corpus.index("已有内容") < corpus.index("测试观点")


@pytest.mark.asyncio
async def test_start_run_rejects_duplicate_active_run(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)

    async def fake_fetch_all_dynamics(mid, **kwargs):
        # 让第一个 run 卡在 fetching_dynamics 的等待上，方便断言第二次启动被拒绝。
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator.dynamic_module, "fetch_all_dynamics", fake_fetch_all_dynamics)

    async def fake_fetch_up_videos(mid, *, page=1, keyword="", order="pubdate"):
        return _up_video_page(mid, [])

    monkeypatch.setattr(orchestrator.space_module, "fetch_up_videos", fake_fetch_up_videos)

    run = await orchestrator.start_run(mid=7, video_limit=5)

    with pytest.raises(RuntimeError):
        await orchestrator.start_run(mid=7, video_limit=5)

    task = orchestrator._active_tasks.get(run.id)
    if task is not None:
        await task


@pytest.mark.asyncio
async def test_cancel_run_marks_cancelled_and_pipeline_stops_between_steps(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    run = await orchestrator.start_run(mid=9, video_limit=5)
    bg_task = orchestrator._active_tasks.pop(run.id, None)
    if bg_task is not None:
        bg_task.cancel()

    async def fake_fetch_all_dynamics(mid, **kwargs):
        return []

    monkeypatch.setattr(orchestrator.dynamic_module, "fetch_all_dynamics", fake_fetch_all_dynamics)
    orchestrator.cancel_run(run.id)

    await orchestrator._run_pipeline(run.id)

    final = distill_repo.get_run(run.id)
    assert final is not None
    assert final.status == DistillRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_prepare_transcripts_fan_out_respects_concurrency_limit(monkeypatch, tmp_path):
    """`_do_prepare_transcripts` 用 settings.distill_transcript_concurrency 做 fan-out
    上限；用一个记录高水位的假 _obtain_transcript 验证从未超过配置的并发数。"""
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(orchestrator.settings, "distill_transcript_concurrency", 2)

    run = distill_repo.create_run(1, video_limit=5, dir_path=str(tmp_path))
    videos = [
        space.UpVideo(bvid=f"BV{i}", title=f"t{i}", cover="", pubdate=i, duration=10, play=1)
        for i in range(5)
    ]

    async def fake_fetch_up_videos_limited(mid, limit):
        return "UP", videos

    in_flight = 0
    high_water_mark = 0

    async def fake_obtain_transcript(run_id, bvid):
        nonlocal in_flight, high_water_mark
        in_flight += 1
        high_water_mark = max(high_water_mark, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return f"transcript-{bvid}"

    monkeypatch.setattr(orchestrator, "_fetch_up_videos_limited", fake_fetch_up_videos_limited)
    monkeypatch.setattr(orchestrator, "_obtain_transcript", fake_obtain_transcript)

    records = await orchestrator._do_prepare_transcripts(run.id)

    assert high_water_mark <= 2
    assert [r["bvid"] for r in records] == [v.bvid for v in videos]
    assert all(r["status"] == "pending_extract" for r in records)

    final = distill_repo.get_run(run.id)
    assert final is not None
    assert final.counters["videos_transcribed"] == 5


@pytest.mark.asyncio
async def test_prepare_transcripts_single_failure_does_not_abort_others(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=3, dir_path=str(tmp_path))
    videos = [
        space.UpVideo(bvid="BV_OK1", title="ok1", cover="", pubdate=1, duration=10, play=1),
        space.UpVideo(bvid="BV_FAIL", title="fail", cover="", pubdate=2, duration=10, play=1),
        space.UpVideo(bvid="BV_OK2", title="ok2", cover="", pubdate=3, duration=10, play=1),
    ]

    async def fake_fetch_up_videos_limited(mid, limit):
        return "UP", videos

    async def fake_obtain_transcript(run_id, bvid):
        if bvid == "BV_FAIL":
            return None
        return f"transcript-{bvid}"

    monkeypatch.setattr(orchestrator, "_fetch_up_videos_limited", fake_fetch_up_videos_limited)
    monkeypatch.setattr(orchestrator, "_obtain_transcript", fake_obtain_transcript)

    records = await orchestrator._do_prepare_transcripts(run.id)

    by_bvid = {r["bvid"]: r for r in records}
    assert by_bvid["BV_OK1"]["status"] == "pending_extract"
    assert by_bvid["BV_OK2"]["status"] == "pending_extract"
    assert by_bvid["BV_FAIL"]["status"] == "failed"

    final = distill_repo.get_run(run.id)
    assert final is not None
    assert final.counters["videos_transcribed"] == 2
    assert "BV_FAIL" in final.counters["failed_bvids"]


@pytest.mark.asyncio
async def test_prepare_transcripts_skips_video_exists_without_creating_job(
    monkeypatch, tmp_path
):
    _setup(monkeypatch, tmp_path)
    run = distill_repo.create_run(2, video_limit=2, dir_path=str(tmp_path))
    distill_storage.save_video(2, "BV_OLD", "---\ntitle: 老视频\n---\n\n已有内容")
    videos = [
        space.UpVideo(bvid="BV_OLD", title="old", cover="", pubdate=1, duration=10, play=1),
        space.UpVideo(bvid="BV_NEW", title="new", cover="", pubdate=2, duration=10, play=1),
    ]

    async def fake_fetch_up_videos_limited(mid, limit):
        return "UP", videos

    called_bvids = []

    async def fake_obtain_transcript(run_id, bvid):
        called_bvids.append(bvid)
        return f"transcript-{bvid}"

    monkeypatch.setattr(orchestrator, "_fetch_up_videos_limited", fake_fetch_up_videos_limited)
    monkeypatch.setattr(orchestrator, "_obtain_transcript", fake_obtain_transcript)

    records = await orchestrator._do_prepare_transcripts(run.id)

    assert called_bvids == ["BV_NEW"]
    by_bvid = {r["bvid"]: r for r in records}
    assert by_bvid["BV_OLD"]["status"] == "extracted"
    assert by_bvid["BV_NEW"]["status"] == "pending_extract"


@pytest.mark.asyncio
async def test_cancel_run_calls_cancel_job_for_spawned_jobs_and_stops_new_spawns(
    monkeypatch, tmp_path
):
    """cancel_run 应该对本 run 已经 spawn 的 job 调 runner.cancel_job；取消发生后，
    尚未处理的视频不应该再触发新的 job/转写获取。"""
    _setup(monkeypatch, tmp_path)
    run = distill_repo.create_run(3, video_limit=3, dir_path=str(tmp_path))
    videos = [
        space.UpVideo(bvid="BV_A", title="a", cover="", pubdate=1, duration=10, play=1),
        space.UpVideo(bvid="BV_B", title="b", cover="", pubdate=2, duration=10, play=1),
    ]

    async def fake_fetch_up_videos_limited(mid, limit):
        return "UP", videos

    cancelled_job_ids = []
    monkeypatch.setattr(orchestrator.runner, "cancel_job", lambda job_id: cancelled_job_ids.append(job_id))

    async def fake_obtain_transcript(run_id, bvid):
        job_id = f"job-{bvid}"
        orchestrator._run_job_ids.setdefault(run_id, set()).add(job_id)
        # 模拟第一个视频处理期间被取消。
        orchestrator.cancel_run(run_id)
        return f"transcript-{bvid}"

    monkeypatch.setattr(orchestrator, "_fetch_up_videos_limited", fake_fetch_up_videos_limited)
    monkeypatch.setattr(orchestrator, "_obtain_transcript", fake_obtain_transcript)

    await orchestrator._do_prepare_transcripts(run.id)

    # 只有第一个视频处理时触发了 cancel_run（注册并取消了它自己的 job）；第二个
    # 视频的协程拿到信号量前/后检查 _is_cancelled 应该短路，不再新建 job。
    assert cancelled_job_ids == ["job-BV_A"]
    final = distill_repo.get_run(run.id)
    assert final is not None
    assert final.status == DistillRunStatus.CANCELLED
