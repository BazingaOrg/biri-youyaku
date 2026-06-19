import asyncio
import logging
from contextlib import asynccontextmanager

from biri_youyaku.config import settings
from biri_youyaku.events import event_bus
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobStatus
from biri_youyaku.jobs.pipeline import (
    CanceledError,
    download_audio,
    fetch_meta,
    fetch_platform_transcript,
    send_email,
    summarize,
    transcribe_audio,
)
from biri_youyaku.modules.asr.base import TranscribeProgress
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 单进程内的 job 运行时态。
#
# 历史包袱：原来散在 4 个模块级 dict 里（_tasks / _cancel_requested /
# _job_llm_api_keys / _stage_started_at），每加一个状态都得在 5 处 pop 维护，
# 极易踩到「忘清一个就内存常驻」的坑。统一收成 _JobRegistry 之后，job 结束的
# 一次性清理走 `_registry.forget(job_id)`；外部公开 API（clear_job_state /
# cancel_job / start_job 等）保持向后兼容。
# ---------------------------------------------------------------------------


class _JobRegistry:
    JOB_KEY_LIMIT = 1024

    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.cancel_requested: set[str] = set()
        self.llm_api_keys: dict[str, str] = {}
        self.stage_started_at: dict[str, tuple[str, int]] = {}

    def remember_key(self, job_id: str, llm_api_key: str | None) -> None:
        if llm_api_key is None or not llm_api_key.strip():
            return
        self.llm_api_keys[job_id] = llm_api_key.strip()
        # 防御性上限：极端场景下 dict 不应该无限增长。每条 entry 在 job 结束时会
        # pop；这里做兜底，超过就丢最早的。
        while len(self.llm_api_keys) > self.JOB_KEY_LIMIT:
            oldest = next(iter(self.llm_api_keys))
            self.llm_api_keys.pop(oldest, None)
            logger.warning(
                "_job_llm_api_keys 超出上限 %d，丢弃最早 entry: %s",
                self.JOB_KEY_LIMIT,
                oldest,
            )

    def forget(self, job_id: str) -> None:
        """job 完成 / 失败 / 取消时一次性清掉所有状态。tasks 不在这里清——由
        `Task.add_done_callback` 自动 pop，避免重复管理。"""
        self.cancel_requested.discard(job_id)
        self.llm_api_keys.pop(job_id, None)
        self.stage_started_at.pop(job_id, None)

    def reset_for_tests(self) -> None:
        """测试 fixture 用：清空所有状态，但不取消已有 task。"""
        self.tasks.clear()
        self.cancel_requested.clear()
        self.llm_api_keys.clear()
        self.stage_started_at.clear()


_registry = _JobRegistry()


_io_semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
_summary_semaphore = asyncio.Semaphore(settings.max_concurrent_summaries)


class StageTimeoutError(RuntimeError):
    pass


@asynccontextmanager
async def _semaphore_with_queue_notice(
    job_id: str,
    stage: JobStatus,
    semaphore: asyncio.Semaphore,
):
    """获取并发槽位；如果立刻拿不到就先通知前端「排队中」，拿到后再通知一次解除。

    这样第 3+ 个任务在等待 `_io_semaphore` / `_summary_semaphore` 时 UI 不会显示
    一动不动的「下载音频 0%」/「正在生成总结」状态而摸不到头脑。
    """
    notified = False
    if semaphore.locked():
        await event_bus.publish(job_id, "status", {"status": stage.value, "queued": True})
        notified = True
    await semaphore.acquire()
    try:
        if notified:
            await event_bus.publish(job_id, "status", {"status": stage.value, "queued": False})
        yield
    finally:
        semaphore.release()


async def _with_timeout(stage: JobStatus, timeout_seconds: float, awaitable):
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise StageTimeoutError(f"{stage.value} 超时") from exc


async def transition(job_id: str, status: JobStatus, **data) -> None:
    now = repo.now_ms()
    previous = _registry.stage_started_at.get(job_id)
    if previous is not None and previous[0] != status.value:
        repo.add_stage_timing(job_id, previous[0], previous[1], now)
        _registry.stage_started_at.pop(job_id, None)
    if status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TRANSCRIPT_READY}:
        _registry.stage_started_at[job_id] = (status.value, now)
    repo.update_status(job_id, status)
    await event_bus.publish(job_id, "status", {"status": status.value, **data})


# ---------------------------------------------------------------------------
# 公开 API：start_job / resume_job / retry_job / cancel_job / clear_job_state
# ---------------------------------------------------------------------------


def retry_job(job_id: str, *, llm_api_key: str | None = None) -> None:
    job = repo.get_job(job_id)
    if job is None:
        raise RuntimeError("Job not found")
    if job.status != JobStatus.FAILED:
        raise RuntimeError(f"Job is {job.status.value}, cannot retry")
    repo.clear_error(job_id)
    if job.transcript:
        repo.update_status(job_id, JobStatus.TRANSCRIPT_READY)
        resume_job(job_id, llm_api_key=llm_api_key)
        return
    repo.update_status(job_id, JobStatus.PENDING)
    start_job(job_id, llm_api_key=llm_api_key)


def _spawn(job_id: str, coro_factory) -> None:
    """共用「注册 task + done_callback 自清」的模板。"""
    if job_id in _registry.tasks:
        return
    task = asyncio.create_task(coro_factory())
    _registry.tasks[job_id] = task
    task.add_done_callback(lambda _: _registry.tasks.pop(job_id, None))


def start_job(job_id: str, *, llm_api_key: str | None = None) -> None:
    if job_id in _registry.tasks:
        return
    _registry.remember_key(job_id, llm_api_key)
    _spawn(job_id, lambda: run_until_transcript(job_id))


def resume_job(job_id: str, *, llm_api_key: str | None = None) -> None:
    if job_id in _registry.tasks:
        return
    _registry.remember_key(job_id, llm_api_key)
    _spawn(job_id, lambda: run_after_resume(job_id))


def cancel_job(job_id: str) -> None:
    _registry.cancel_requested.add(job_id)
    task = _registry.tasks.get(job_id)
    if task is not None:
        task.cancel()


def clear_job_state(job_id: str) -> None:
    """对外暴露的一次性清理 hook（routes 删除 / 取消时调）。等价 `_registry.forget`。"""
    _registry.forget(job_id)


def _raise_if_canceled(job_id: str) -> None:
    if job_id in _registry.cancel_requested:
        raise CanceledError()


def recover_unfinished_jobs() -> None:
    for job in repo.list_recoverable_jobs():
        logger.info("Recovering unfinished job %s from %s", job.id, job.status.value)
        if job.status in {JobStatus.PENDING, JobStatus.FETCHING_META, JobStatus.DOWNLOADING_AUDIO}:
            start_job(job.id)
        else:
            repo.set_error(job.id, job.status.value, "服务重启时任务处于不可安全恢复的中间状态", "RECOVERY_UNSAFE")
            repo.update_status(job.id, JobStatus.FAILED)


def _meta_from_job(job) -> VideoMeta:
    return VideoMeta(
        url=job.url,
        bvid=job.bvid or "",
        cid=job.cid,
        title=job.title or job.bvid or job.id,
        author=job.author or "",
        duration=job.duration or 0,
    )


def _transcript_from_job(job) -> list[TranscriptItem]:
    return [
        TranscriptItem(
            start=float(item["start"]),
            end=float(item["end"]),
            text=str(item["text"]),
        )
        for item in job.transcript or []
        if str(item.get("text") or "").strip()
    ]


# ---------------------------------------------------------------------------
# Lifecycle：收敛 run_until_transcript / run_after_resume 共享的 try/except/finally。
# ---------------------------------------------------------------------------


class _RunStage:
    """`async with _job_lifecycle(...) as stage:` 里可变的「当前阶段」标记。
    异常分支会读它写错误的 stage 字段，所以必须是可变对象（不能用裸字符串）。"""

    __slots__ = ("value",)

    def __init__(self, initial: JobStatus) -> None:
        self.value: str = initial.value


@asynccontextmanager
async def _job_lifecycle(job_id: str, initial_stage: JobStatus):
    """统一 run_* 主体的收尾：

    - 取消（`CancelledError` / `CanceledError`）→ 状态 CANCELED + 清 key；
    - 其它异常 → 写 error + 状态 FAILED（识别 StageTimeoutError 给 error_code）+ 清 key；
    - 无论成功 / 失败：finally 清 `cancel_requested` 与 `stage_started_at`。
    """
    stage = _RunStage(initial_stage)
    try:
        yield stage
    except (asyncio.CancelledError, CanceledError):
        await transition(job_id, JobStatus.CANCELED)
        _registry.llm_api_keys.pop(job_id, None)
    except Exception as exc:
        logger.exception("Job %s failed at %s", job_id, stage.value)
        error_code = "STAGE_TIMEOUT" if isinstance(exc, StageTimeoutError) else None
        repo.set_error(job_id, stage.value, str(exc), error_code)
        await transition(
            job_id,
            JobStatus.FAILED,
            stage=stage.value,
            message=str(exc),
            error_code=error_code,
        )
        _registry.llm_api_keys.pop(job_id, None)
    finally:
        _registry.cancel_requested.discard(job_id)
        _registry.stage_started_at.pop(job_id, None)


# ---------------------------------------------------------------------------
# 主体：抓 meta → 下音频/字幕 → 转写 → （pause）→ 总结 → 邮件
# ---------------------------------------------------------------------------


async def run_until_transcript(job_id: str) -> None:
    async with _job_lifecycle(job_id, JobStatus.PENDING) as stage:
        job = repo.get_job(job_id)
        if job is None:
            raise RuntimeError("Job not found")

        stage.value = JobStatus.FETCHING_META.value
        await transition(job_id, JobStatus.FETCHING_META)
        video_meta = await _with_timeout(JobStatus.FETCHING_META, 30, fetch_meta(job.url))
        # 防滥用：preview 阶段已经拦了一次，这里兜底（用户绕过 preview 直接 POST /v1/jobs 也能挡）
        if video_meta.duration and video_meta.duration > settings.max_video_duration_seconds:
            raise RuntimeError(
                f"视频时长 {int(video_meta.duration // 60)} 分钟超过上限 "
                f"{settings.max_video_duration_seconds // 60} 分钟"
            )
        repo.update_meta(
            job_id,
            bvid=video_meta.bvid,
            cid=video_meta.cid,
            title=video_meta.title,
            author=video_meta.author,
            duration=video_meta.duration,
        )
        repo.set_chapters(job_id, video_meta.chapters)
        # 顺手把 chapters 一起推到 meta event，前端不用再 refresh 就能拿到
        await event_bus.publish(
            job_id,
            "meta",
            {
                "title": video_meta.title,
                "author": video_meta.author,
                "duration": video_meta.duration,
                "chapters": [
                    {"start": ch.start, "end": ch.end, "title": ch.title}
                    for ch in (video_meta.chapters or [])
                ],
            },
        )
        _raise_if_canceled(job_id)

        fresh_job = repo.get_job(job_id)
        if fresh_job is None:
            raise RuntimeError("Job not found")

        if fresh_job.options.task_type == "audio":
            stage.value = JobStatus.DOWNLOADING_AUDIO.value
            await transition(job_id, JobStatus.DOWNLOADING_AUDIO)
            async with _semaphore_with_queue_notice(job_id, JobStatus.DOWNLOADING_AUDIO, _io_semaphore):
                await _with_timeout(
                    JobStatus.DOWNLOADING_AUDIO,
                    1800,
                    download_audio(
                        fresh_job,
                        video_meta,
                        on_progress=lambda payload: event_bus.publish(job_id, "download_progress", payload),
                    ),
                )
            await transition(job_id, JobStatus.COMPLETED)
            clear_job_state(job_id)
            return

        if video_meta.has_subtitle and not fresh_job.options.force_asr:
            items = await _with_timeout(JobStatus.DOWNLOADING_AUDIO, 120, fetch_platform_transcript(fresh_job, video_meta))
        else:
            stage.value = JobStatus.DOWNLOADING_AUDIO.value
            await transition(job_id, JobStatus.DOWNLOADING_AUDIO)
            async with _semaphore_with_queue_notice(job_id, JobStatus.DOWNLOADING_AUDIO, _io_semaphore):
                audio_path = await _with_timeout(
                    JobStatus.DOWNLOADING_AUDIO,
                    1800,
                    download_audio(
                        fresh_job,
                        video_meta,
                        on_progress=lambda payload: event_bus.publish(job_id, "download_progress", payload),
                    ),
                )
            _raise_if_canceled(job_id)

            stage.value = JobStatus.TRANSCRIBING.value
            await transition(job_id, JobStatus.TRANSCRIBING)

            async def _on_transcribe_progress(progress: TranscribeProgress) -> None:
                await event_bus.publish(
                    job_id,
                    "transcribe_progress",
                    {
                        "percent": progress.percent * 100,
                        "items_count": progress.items_count,
                        "preview": progress.preview,
                    },
                )

            async with _semaphore_with_queue_notice(job_id, JobStatus.TRANSCRIBING, _io_semaphore):
                # 1h+ 视频也要给余量，SenseVoice CPU 推理 1h 音频可能要 20-40min
                items = await _with_timeout(
                    JobStatus.TRANSCRIBING,
                    3600,
                    transcribe_audio(fresh_job, audio_path, on_progress=_on_transcribe_progress),
                )
        _raise_if_canceled(job_id)
        repo.set_transcript(job_id, items)
        # 带前 3 行 preview 一起发出去，前端不用等 refresh 就能渲染「字幕已就绪」预览
        transcript_preview = [
            {"start": float(item.start), "end": float(item.end), "text": item.text}
            for item in items[:3]
        ]
        await transition(
            job_id,
            JobStatus.TRANSCRIPT_READY,
            transcript_preview=transcript_preview,
            subtitle_source="platform" if (video_meta.has_subtitle and not fresh_job.options.force_asr) else "asr",
        )


async def run_after_resume(job_id: str) -> None:
    async with _job_lifecycle(job_id, JobStatus.SUMMARIZING) as stage:
        fresh_job = repo.get_job(job_id)
        if fresh_job is None:
            raise RuntimeError("Job not found")
        if fresh_job.status != JobStatus.TRANSCRIPT_READY:
            raise RuntimeError(f"Job is {fresh_job.status.value}, cannot resume")
        items = _transcript_from_job(fresh_job)
        if not items:
            raise RuntimeError("任务没有可总结的字幕")
        video_meta = _meta_from_job(fresh_job)
        stage.value = JobStatus.SUMMARIZING.value
        await transition(job_id, JobStatus.SUMMARIZING)
        async with _semaphore_with_queue_notice(job_id, JobStatus.SUMMARIZING, _summary_semaphore):
            # 长视频字幕一次喂给 LLM 流式输出，5 分钟常常超；放宽到 20 分钟兜底
            summary_md = await _with_timeout(
                JobStatus.SUMMARIZING,
                1200,
                summarize(
                    fresh_job,
                    video_meta,
                    items,
                    llm_api_key=_registry.llm_api_keys.get(job_id),
                    on_chunk=lambda text: event_bus.publish(job_id, "summary_chunk", {"text": text}),
                    on_usage=lambda usage: _record_token_usage(job_id, usage),
                    on_segment=lambda done, total: event_bus.publish(
                        job_id, "summary_segment", {"done": done, "total": total}
                    ),
                ),
            )
        _raise_if_canceled(job_id)

        # 邮件失败（含 EMAILING 阶段 timeout = StageTimeoutError(RuntimeError)）一律
        # 不阻断 COMPLETED：summary 已经落盘，用户可手动 ↻ 重发。
        # - 与旧契约不同：之前任何邮件异常会把整个 job 置 FAILED。新契约把失败原因
        #   存到 email_error 字段，前端展示「邮件未送达 ↻ 重发邮件」提示。
        # - 取消（CancelledError / CanceledError）必须 re-raise，让外层 lifecycle 走
        #   CANCELED 分支；否则会被静默吞掉变成「completed + email_error=取消」。
        email_error: str | None = None
        if fresh_job.options.email_enabled:
            stage.value = JobStatus.EMAILING.value
            await transition(job_id, JobStatus.EMAILING)
            try:
                await _with_timeout(JobStatus.EMAILING, 120, send_email(video_meta, summary_md, fresh_job.options))
            except (asyncio.CancelledError, CanceledError):
                raise
            except Exception as exc:
                email_error = str(exc) or "邮件发送失败"
                logger.warning("Job %s email send failed: %s", job_id, email_error)
                repo.set_email_error(job_id, email_error)

        await transition(
            job_id,
            JobStatus.COMPLETED,
            summary=summary_md,
            email_error=email_error,
        )


async def _record_token_usage(job_id: str, usage: dict) -> None:
    repo.add_token_usage(job_id, usage)
