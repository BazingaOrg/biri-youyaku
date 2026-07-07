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
