"""作者蒸馏语料的编排：抓动态 → 补齐转写 → 逐视频提取 → 组装。

一个 mid 同时只允许一个非终态 run（见 `repo.find_active_by_mid`，`start_run` 里检查）。
整条流程跑在一个后台 asyncio task 里（`_run_pipeline`）。

取消：没有像 `jobs/runner.py` 那样对正在跑的 task 做 `task.cancel()` 硬打断——蒸馏
这边没有需要立刻打断的长阻塞 IO（每一步都是"一批/一个视频处理完再检查一次"），
`repo.update_status(..., CANCELLED)` + 循环间隙检查已经足够及时，也更简单。

断点续跑：`recover_unfinished_runs()`（app 启动时调用）对每个非终态 run 重新跑一遍
`_run_pipeline`。三步都设计成幂等/可重入：
  - 动态：每次都重新抓 + 重新清洗（B 站接口本身有限流保护，浪费一点调用可接受，
    换来不用维护"抓到哪一页"这类额外状态）；
  - 转写：已有 `videos/<bvid>.md` 的视频直接跳过；否则先查有没有可复用的已完成
    job，没有才新建 job；
  - 提取：同样按 `videos/<bvid>.md` 是否存在跳过。
manifest.json 只在 assembling 步骤由 assembler.py 整体重写，不是运行时续跑依据——
续跑靠 `distill_runs` 表的行 + 上面这些文件是否存在。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from biri_youyaku.config import settings
from biri_youyaku.distill import assembler
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.distill.model import (
    DistillRun,
    DistillRunStatus,
    TERMINAL_DISTILL_RUN_STATUS_VALUES,
)
from biri_youyaku.events import event_bus
from biri_youyaku.jobs import repo as job_repo
from biri_youyaku.jobs import runner
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.runner import start_job
from biri_youyaku.modules.asr.formatter import transcript_to_text
from biri_youyaku.modules.bilibili import dynamic as dynamic_module
from biri_youyaku.modules.bilibili import space as space_module
from biri_youyaku.modules.llm.distill import clean_dynamics_batch, extract_video_viewpoints
from biri_youyaku.modules.storage import distill as distill_storage
from biri_youyaku.modules.transcript import TranscriptItem

logger = logging.getLogger(__name__)

_DYNAMICS_BATCH_SIZE = 50
_EXTRACT_CONCURRENCY = 2
_DISTILL_LANGUAGE = "中文简体"

_DYNAMIC_TYPE_LABELS = {
    "video": "视频",
    "text": "文字",
    "image": "图文",
    "article": "文章",
    "forward": "转发",
    "other": "其他",
}

# 单进程内正在跑的编排 task，key 为 run_id（镜像 jobs/runner.py 的 _registry.tasks，
# 但蒸馏没有取消 key / llm_api_key 这些额外状态，不需要一整个 registry 类）。
_active_tasks: dict[str, asyncio.Task] = {}

# run_id -> 该 run 已 spawn 的 job id 集合，仅内存态、不落库；用于 cancel_run 联动
# `runner.cancel_job()` 打断正在跑的转写 job（_obtain_transcript 里注册）。
_run_job_ids: dict[str, set[str]] = {}


class DistillRunCancelled(Exception):
    pass


async def start_run(mid: int, video_limit: int = 50) -> DistillRun:
    existing = distill_repo.find_active_by_mid(mid)
    if existing is not None:
        raise RuntimeError(f"UP {mid} 已有进行中的蒸馏任务（run_id={existing.id}）")
    dir_path = str(distill_storage.run_dir(mid))
    run = distill_repo.create_run(mid, video_limit=video_limit, dir_path=dir_path)
    _spawn(run.id)
    return run


def cancel_run(run_id: str) -> None:
    run = distill_repo.get_run(run_id)
    if run is None or run.status.value in TERMINAL_DISTILL_RUN_STATUS_VALUES:
        return
    distill_repo.update_status(run_id, DistillRunStatus.CANCELLED)
    for job_id in _run_job_ids.get(run_id, set()):
        runner.cancel_job(job_id)


def recover_unfinished_runs() -> None:
    for run in distill_repo.list_unfinished_runs():
        logger.info(
            "Recovering unfinished distill run %s (mid=%s, status=%s)",
            run.id,
            run.mid,
            run.status.value,
        )
        _spawn(run.id)


def has_active_task(run_id: str) -> bool:
    return run_id in _active_tasks


def _spawn(run_id: str) -> None:
    if run_id in _active_tasks:
        return
    task = asyncio.create_task(_run_pipeline(run_id))
    _active_tasks[run_id] = task
    task.add_done_callback(lambda _: _active_tasks.pop(run_id, None))


async def _publish(run_id: str, status: DistillRunStatus, **extra) -> None:
    await event_bus.publish(run_id, "status", {"status": status.value, **extra})


def _is_cancelled(run_id: str) -> bool:
    run = distill_repo.get_run(run_id)
    return run is None or run.status == DistillRunStatus.CANCELLED


def _raise_if_cancelled(run_id: str) -> None:
    if _is_cancelled(run_id):
        raise DistillRunCancelled()


def _format_ts(ts: int | None) -> str:
    if not ts:
        return "未知日期"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


async def _run_pipeline(run_id: str) -> None:
    try:
        # 每个阶段开始前都先检查一次取消：光在阶段之间检查不够——每个 _do_* 一进
        # 门就会无条件把 status 写成自己的阶段名，如果 run 在上一阶段结束、下一
        # 阶段开始前的空隙被取消，这一检查缺失就会把 CANCELLED 状态覆盖回运行中。
        _raise_if_cancelled(run_id)
        await _do_fetch_dynamics(run_id)
        _raise_if_cancelled(run_id)
        records = await _do_prepare_transcripts(run_id)
        _raise_if_cancelled(run_id)
        records = await _do_extract(run_id, records)
        _raise_if_cancelled(run_id)

        distill_repo.update_status(run_id, DistillRunStatus.ASSEMBLING)
        await _publish(run_id, DistillRunStatus.ASSEMBLING)
        run = distill_repo.get_run(run_id)
        if run is None:
            return
        assembler.assemble(run, records)

        distill_repo.update_status(run_id, DistillRunStatus.COMPLETED)
        await _publish(run_id, DistillRunStatus.COMPLETED)
    except DistillRunCancelled:
        distill_repo.update_status(run_id, DistillRunStatus.CANCELLED)
        await _publish(run_id, DistillRunStatus.CANCELLED)
    except Exception as exc:
        logger.exception("Distill run %s failed", run_id)
        distill_repo.update_status(run_id, DistillRunStatus.FAILED, error=str(exc))
        await _publish(run_id, DistillRunStatus.FAILED, error=str(exc))
    finally:
        # run 结束（无论成功/取消/失败）：清掉本 run 的 job id 追踪，避免内存常驻。
        _run_job_ids.pop(run_id, None)


# ---------------------------------------------------------------------------
# Step 1：动态
# ---------------------------------------------------------------------------


def _format_dynamic_line(item: dict) -> str:
    date = _format_ts(item.get("ts"))
    label = _DYNAMIC_TYPE_LABELS.get(item.get("type"), item.get("type") or "其他")
    text = (item.get("text") or "").replace("\n", " ").strip()
    return f"[{date}][{label}] {text}"


async def _do_fetch_dynamics(run_id: str) -> None:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise DistillRunCancelled()
    distill_repo.update_status(run_id, DistillRunStatus.FETCHING_DYNAMICS)
    await _publish(run_id, DistillRunStatus.FETCHING_DYNAMICS)

    try:
        dynamics = await dynamic_module.fetch_all_dynamics(run.mid)
    except Exception as exc:
        # 动态接口失败（含频控重试后仍失败）：降级，不中断整个 run。
        logger.warning(
            "Distill run %s: dynamics fetch failed, degrading to unavailable (%s)", run_id, exc
        )
        distill_repo.set_dynamics_status(run_id, "unavailable")
        await _publish(run_id, DistillRunStatus.FETCHING_DYNAMICS, dynamics_status="unavailable")
        return

    cleaned_batches: list[str] = []
    dynamics_count = 0
    for start in range(0, len(dynamics), _DYNAMICS_BATCH_SIZE):
        _raise_if_cancelled(run_id)
        batch = dynamics[start : start + _DYNAMICS_BATCH_SIZE]
        lines = [_format_dynamic_line(item) for item in batch]
        cleaned = (await clean_dynamics_batch(lines, _DISTILL_LANGUAGE)).strip()
        if cleaned and cleaned != "（本批无有效观点内容）":
            cleaned_batches.append(cleaned)
            dynamics_count += sum(
                1 for line in cleaned.splitlines() if line.strip().startswith("-")
            )

        content = "\n\n".join(cleaned_batches) if cleaned_batches else "（本次蒸馏无有效动态内容）"
        distill_storage.save_dynamics(run.mid, content)
        distill_repo.update_counters(run_id, dynamics_count=dynamics_count)
        await _publish(run_id, DistillRunStatus.FETCHING_DYNAMICS, dynamics_count=dynamics_count)

    distill_repo.set_dynamics_status(run_id, "ok")
    await _publish(
        run_id,
        DistillRunStatus.FETCHING_DYNAMICS,
        dynamics_status="ok",
        dynamics_count=dynamics_count,
    )


# ---------------------------------------------------------------------------
# Step 2：补齐转写
# ---------------------------------------------------------------------------


async def _fetch_up_videos_limited(mid: int, limit: int) -> tuple[str, list]:
    collected: list = []
    author = ""
    page = 1
    while len(collected) < limit:
        result = await space_module.fetch_up_videos(mid, page=page, order="pubdate")
        author = result.author or author
        collected.extend(result.videos)
        if not result.has_more:
            break
        page += 1
    return author, collected[:limit]


def _transcript_items_from_job(job) -> list[TranscriptItem]:
    return [
        TranscriptItem(start=float(item["start"]), end=float(item["end"]), text=str(item["text"]))
        for item in job.transcript or []
        if str(item.get("text") or "").strip()
    ]


async def _obtain_transcript(run_id: str, bvid: str) -> str | None:
    """先找有 transcript 的已完成 job 复用；没有就建 task_type="distill" 的 job
    走现有 runner 到 COMPLETED（等价 TRANSCRIPT_READY，见 runner.py 的提前收尾分支）
    即停，等待其完成信号。ASR 是成本大头，复用转写不复用总结。"""
    existing = job_repo.find_completed_by_bvid(bvid, include_distill=True)
    if existing is not None and existing.transcript:
        items = _transcript_items_from_job(existing)
        if items:
            return transcript_to_text(items)

    url = f"https://www.bilibili.com/video/{bvid}"
    options = JobOptions(task_type="distill", email_enabled=False)
    job = job_repo.create_job(url, options)
    _run_job_ids.setdefault(run_id, set()).add(job.id)
    start_job(job.id)

    final_status = await runner.await_job_completion(job.id)
    if final_status == JobStatus.COMPLETED:
        current = job_repo.get_job(job.id)
        if current is None:
            return None
        items = _transcript_items_from_job(current)
        return transcript_to_text(items) if items else None
    logger.warning(
        "Distill: transcript job %s for %s ended as %s, skipping video",
        job.id,
        bvid,
        final_status.value,
    )
    return None


async def _do_prepare_transcripts(run_id: str) -> list[dict]:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise DistillRunCancelled()
    distill_repo.update_status(run_id, DistillRunStatus.PREPARING_TRANSCRIPTS)
    await _publish(run_id, DistillRunStatus.PREPARING_TRANSCRIPTS)

    author, up_videos = await _fetch_up_videos_limited(run.mid, run.video_limit)
    if author:
        distill_repo.set_up_name(run_id, author)
    distill_repo.update_counters(run_id, videos_total=len(up_videos))
    await _publish(run_id, DistillRunStatus.PREPARING_TRANSCRIPTS, videos_total=len(up_videos))

    # 构造完整顺序的 records 列表（保留 up_videos 原始顺序），先同步过滤掉
    # video_exists 的（已提取过，断点续跑不重转写），剩下的再并发 fan-out 获取转写。
    records: list[dict] = []
    transcribed = 0
    pending_indices: list[int] = []
    for video in up_videos:
        _raise_if_cancelled(run_id)
        record = {
            "bvid": video.bvid,
            "title": video.title,
            "pubdate": video.pubdate,
            "duration": video.duration,
            "play": video.play,
        }
        if distill_storage.video_exists(run.mid, video.bvid):
            # 断点续跑：已经提取过，直接算完成，不重新转写/提取。
            record["status"] = "extracted"
            transcribed += 1
            distill_repo.update_counters(run_id, videos_transcribed=transcribed)
        else:
            pending_indices.append(len(records))
        records.append(record)

    semaphore = asyncio.Semaphore(settings.distill_transcript_concurrency)

    async def _obtain_one(video, record: dict) -> None:
        nonlocal transcribed
        if _is_cancelled(run_id):
            return
        async with semaphore:
            if _is_cancelled(run_id):
                return
            try:
                transcript_text = await _obtain_transcript(run_id, video.bvid)
            except Exception as exc:
                logger.warning(
                    "Distill run %s: obtain transcript failed for %s: %s",
                    run_id,
                    video.bvid,
                    exc,
                )
                transcript_text = None
            if transcript_text is None:
                record["status"] = "failed"
                distill_repo.add_failed_bvid(run_id, video.bvid)
                return
            record["status"] = "pending_extract"
            record["transcript_text"] = transcript_text
            # 计数自增与 update_counters 之间不得有 await——保证并发写计数安全。
            transcribed += 1
            distill_repo.update_counters(run_id, videos_transcribed=transcribed)
            await _publish(
                run_id, DistillRunStatus.PREPARING_TRANSCRIPTS, videos_transcribed=transcribed
            )

    await asyncio.gather(
        *(_obtain_one(up_videos[i], records[i]) for i in pending_indices)
    )

    return records


# ---------------------------------------------------------------------------
# Step 3：逐视频观点提取
# ---------------------------------------------------------------------------


def _render_video_markdown(record: dict, body: str) -> str:
    frontmatter = (
        "---\n"
        f"title: {record['title']}\n"
        f"bvid: {record['bvid']}\n"
        f"pubdate: {record['pubdate']}\n"
        f"duration: {record['duration']}\n"
        f"play: {record['play']}\n"
        "---\n\n"
    )
    return frontmatter + body.strip() + "\n"


async def _do_extract(run_id: str, records: list[dict]) -> list[dict]:
    run = distill_repo.get_run(run_id)
    if run is None:
        raise DistillRunCancelled()
    distill_repo.update_status(run_id, DistillRunStatus.EXTRACTING)
    await _publish(run_id, DistillRunStatus.EXTRACTING)

    semaphore = asyncio.Semaphore(_EXTRACT_CONCURRENCY)
    extracted_count = sum(1 for record in records if record["status"] == "extracted")

    async def _extract_one(record: dict) -> None:
        nonlocal extracted_count
        if _is_cancelled(run_id):
            return
        async with semaphore:
            if _is_cancelled(run_id):
                return
            try:
                body = await extract_video_viewpoints(
                    record["title"], record["transcript_text"], _DISTILL_LANGUAGE
                )
                content = _render_video_markdown(record, body)
                distill_storage.save_video(run.mid, record["bvid"], content)
                record["status"] = "extracted"
                extracted_count += 1
                distill_repo.update_counters(run_id, videos_extracted=extracted_count)
                await _publish(
                    run_id, DistillRunStatus.EXTRACTING, videos_extracted=extracted_count
                )
            except Exception as exc:
                # 单视频提取失败不中断其余视频（有别于 client._summarize_chunked
                # 对同一视频内分段的 fail-fast：这里每个视频相互独立）。
                logger.warning(
                    "Distill run %s: extract failed for %s: %s", run_id, record["bvid"], exc
                )
                record["status"] = "failed"
                distill_repo.add_failed_bvid(run_id, record["bvid"])

    pending = [record for record in records if record["status"] == "pending_extract"]
    await asyncio.gather(*(_extract_one(record) for record in pending))
    for record in records:
        record.pop("transcript_text", None)
    return records
