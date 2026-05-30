import asyncio
import logging

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
_tasks: dict[str, asyncio.Task[None]] = {}
_cancel_requested: set[str] = set()
_job_llm_api_keys: dict[str, str] = {}
_stage_started_at: dict[str, tuple[str, int]] = {}
_io_semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
_summary_semaphore = asyncio.Semaphore(settings.max_concurrent_summaries)


class StageTimeoutError(RuntimeError):
    pass


async def _with_timeout(stage: JobStatus, timeout_seconds: float, awaitable):
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise StageTimeoutError(f"{stage.value} 超时") from exc


async def transition(job_id: str, status: JobStatus, **data) -> None:
    now = repo.now_ms()
    previous = _stage_started_at.get(job_id)
    if previous is not None and previous[0] != status.value:
        repo.add_stage_timing(job_id, previous[0], previous[1], now)
        _stage_started_at.pop(job_id, None)
    if status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TRANSCRIPT_READY}:
        _stage_started_at[job_id] = (status.value, now)
    repo.update_status(job_id, status)
    await event_bus.publish(job_id, "status", {"status": status.value, **data})


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


def start_job(job_id: str, *, llm_api_key: str | None = None) -> None:
    if job_id in _tasks:
        return
    if llm_api_key is not None and llm_api_key.strip():
        _job_llm_api_keys[job_id] = llm_api_key.strip()
    task = asyncio.create_task(run_until_transcript(job_id))
    _tasks[job_id] = task
    task.add_done_callback(lambda _: _tasks.pop(job_id, None))


def resume_job(job_id: str, *, llm_api_key: str | None = None) -> None:
    if job_id in _tasks:
        return
    if llm_api_key is not None and llm_api_key.strip():
        _job_llm_api_keys[job_id] = llm_api_key.strip()
    task = asyncio.create_task(run_after_resume(job_id))
    _tasks[job_id] = task
    task.add_done_callback(lambda _: _tasks.pop(job_id, None))


def cancel_job(job_id: str) -> None:
    _cancel_requested.add(job_id)
    task = _tasks.get(job_id)
    if task is not None:
        task.cancel()


def clear_job_state(job_id: str) -> None:
    _cancel_requested.discard(job_id)
    _job_llm_api_keys.pop(job_id, None)
    _stage_started_at.pop(job_id, None)


def _raise_if_canceled(job_id: str) -> None:
    if job_id in _cancel_requested:
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


async def run_until_transcript(job_id: str) -> None:
    current_stage = JobStatus.PENDING.value
    try:
        job = repo.get_job(job_id)
        if job is None:
            raise RuntimeError("Job not found")

        current_stage = JobStatus.FETCHING_META.value
        await transition(job_id, JobStatus.FETCHING_META)
        video_meta = await _with_timeout(JobStatus.FETCHING_META, 30, fetch_meta(job.url))
        repo.update_meta(
            job_id,
            bvid=video_meta.bvid,
            cid=video_meta.cid,
            title=video_meta.title,
            author=video_meta.author,
            duration=video_meta.duration,
        )
        repo.set_chapters(job_id, video_meta.chapters)
        await event_bus.publish(job_id, "meta", {"title": video_meta.title, "author": video_meta.author})
        _raise_if_canceled(job_id)

        fresh_job = repo.get_job(job_id)
        if fresh_job is None:
            raise RuntimeError("Job not found")

        if fresh_job.options.task_type == "audio":
            current_stage = JobStatus.DOWNLOADING_AUDIO.value
            await transition(job_id, JobStatus.DOWNLOADING_AUDIO)
            async with _io_semaphore:
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
            current_stage = JobStatus.DOWNLOADING_AUDIO.value
            await transition(job_id, JobStatus.DOWNLOADING_AUDIO)
            async with _io_semaphore:
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

            current_stage = JobStatus.TRANSCRIBING.value
            await transition(job_id, JobStatus.TRANSCRIBING)
            async def _on_transcribe_progress(progress: TranscribeProgress) -> None:
                event_bus.publish(
                    job_id,
                    "transcribe_progress",
                    {
                        "percent": progress.percent * 100,
                        "items_count": progress.items_count,
                        "preview": progress.preview,
                    },
                )

            async with _io_semaphore:
                # 1h+ 视频也要给余量，SenseVoice CPU 推理 1h 音频可能要 20-40min
                items = await _with_timeout(
                    JobStatus.TRANSCRIBING,
                    3600,
                    transcribe_audio(fresh_job, audio_path, on_progress=_on_transcribe_progress),
                )
        _raise_if_canceled(job_id)
        repo.set_transcript(job_id, items)
        await transition(job_id, JobStatus.TRANSCRIPT_READY)
    except (asyncio.CancelledError, CanceledError):
        await transition(job_id, JobStatus.CANCELED)
        _job_llm_api_keys.pop(job_id, None)
    except Exception as exc:
        logger.exception("Job %s failed at %s", job_id, current_stage)
        error_code = "STAGE_TIMEOUT" if isinstance(exc, StageTimeoutError) else None
        repo.set_error(job_id, current_stage, str(exc), error_code)
        await transition(job_id, JobStatus.FAILED, stage=current_stage, message=str(exc), error_code=error_code)
        _job_llm_api_keys.pop(job_id, None)
    finally:
        _cancel_requested.discard(job_id)
        _stage_started_at.pop(job_id, None)


async def run_after_resume(job_id: str) -> None:
    current_stage = JobStatus.SUMMARIZING.value
    try:
        fresh_job = repo.get_job(job_id)
        if fresh_job is None:
            raise RuntimeError("Job not found")
        if fresh_job.status != JobStatus.TRANSCRIPT_READY:
            raise RuntimeError(f"Job is {fresh_job.status.value}, cannot resume")
        items = _transcript_from_job(fresh_job)
        if not items:
            raise RuntimeError("任务没有可总结的字幕")
        video_meta = _meta_from_job(fresh_job)
        current_stage = JobStatus.SUMMARIZING.value
        await transition(job_id, JobStatus.SUMMARIZING)
        async with _summary_semaphore:
            # 长视频字幕一次喂给 LLM 流式输出，5 分钟常常超；放宽到 20 分钟兜底
            summary_md = await _with_timeout(
                JobStatus.SUMMARIZING,
                1200,
                summarize(
                    fresh_job,
                    video_meta,
                    items,
                    llm_api_key=_job_llm_api_keys.get(job_id),
                    on_chunk=lambda text: event_bus.publish(job_id, "summary_chunk", {"text": text}),
                    on_usage=lambda usage: _record_token_usage(job_id, usage),
                ),
            )
        _raise_if_canceled(job_id)

        # 邮件失败（含 EMAILING 阶段 timeout = StageTimeoutError(RuntimeError)）一律
        # 不阻断 COMPLETED：summary 已经落盘，用户可手动 ↻ 重发。
        # - 与旧契约不同：之前任何邮件异常会把整个 job 置 FAILED。新契约把失败原因
        #   存到 email_error 字段，前端展示「邮件未送达 ↻ 重发邮件」提示。
        # - 取消（CancelledError / CanceledError）必须 re-raise，让外层 except 走
        #   CANCELED 分支；否则会被静默吞掉变成「completed + email_error=取消」。
        email_error: str | None = None
        if fresh_job.options.email_enabled:
            current_stage = JobStatus.EMAILING.value
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
    except (asyncio.CancelledError, CanceledError):
        await transition(job_id, JobStatus.CANCELED)
    except Exception as exc:
        logger.exception("Job %s failed at %s", job_id, current_stage)
        error_code = "STAGE_TIMEOUT" if isinstance(exc, StageTimeoutError) else None
        repo.set_error(job_id, current_stage, str(exc), error_code)
        await transition(job_id, JobStatus.FAILED, stage=current_stage, message=str(exc), error_code=error_code)
    finally:
        _cancel_requested.discard(job_id)
        _job_llm_api_keys.pop(job_id, None)
        _stage_started_at.pop(job_id, None)


async def _record_token_usage(job_id: str, usage: dict) -> None:
    repo.add_token_usage(job_id, usage)
