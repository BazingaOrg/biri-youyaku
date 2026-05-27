import asyncio
import logging

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
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem

logger = logging.getLogger(__name__)
_tasks: dict[str, asyncio.Task[None]] = {}
_cancel_requested: set[str] = set()
_job_llm_api_keys: dict[str, str] = {}


async def transition(job_id: str, status: JobStatus, **data) -> None:
    repo.update_status(job_id, status)
    await event_bus.publish(job_id, "status", {"status": status.value, **data})


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


def _raise_if_canceled(job_id: str) -> None:
    if job_id in _cancel_requested:
        raise CanceledError()


def recover_unfinished_jobs() -> None:
    for job in repo.list_recoverable_jobs():
        logger.info("Recovering unfinished job %s from %s", job.id, job.status.value)
        start_job(job.id)


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
        video_meta = await fetch_meta(job.url)
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
            await download_audio(fresh_job, video_meta)
            await transition(job_id, JobStatus.COMPLETED)
            clear_job_state(job_id)
            return

        if video_meta.has_subtitle and not fresh_job.options.force_asr:
            items = await fetch_platform_transcript(fresh_job, video_meta)
        else:
            current_stage = JobStatus.DOWNLOADING_AUDIO.value
            await transition(job_id, JobStatus.DOWNLOADING_AUDIO)
            audio_path = await download_audio(fresh_job, video_meta)
            _raise_if_canceled(job_id)

            current_stage = JobStatus.TRANSCRIBING.value
            await transition(job_id, JobStatus.TRANSCRIBING)
            items = await transcribe_audio(fresh_job, audio_path)
        _raise_if_canceled(job_id)
        repo.set_transcript(job_id, items)
        await transition(job_id, JobStatus.TRANSCRIPT_READY)
    except (asyncio.CancelledError, CanceledError):
        await transition(job_id, JobStatus.CANCELED)
        _job_llm_api_keys.pop(job_id, None)
    except Exception as exc:
        logger.exception("Job %s failed at %s", job_id, current_stage)
        repo.set_error(job_id, current_stage, str(exc))
        await transition(job_id, JobStatus.FAILED, stage=current_stage, message=str(exc))
        _job_llm_api_keys.pop(job_id, None)
    finally:
        _cancel_requested.discard(job_id)


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
        summary_md = await summarize(
            fresh_job,
            video_meta,
            items,
            llm_api_key=_job_llm_api_keys.get(job_id),
        )
        await event_bus.publish(job_id, "summary_chunk", {"text": summary_md})
        _raise_if_canceled(job_id)

        if fresh_job.options.email_enabled:
            current_stage = JobStatus.EMAILING.value
            await transition(job_id, JobStatus.EMAILING)
            await send_email(video_meta, summary_md, fresh_job.options)

        await transition(job_id, JobStatus.COMPLETED, summary=summary_md)
    except (asyncio.CancelledError, CanceledError):
        await transition(job_id, JobStatus.CANCELED)
    except Exception as exc:
        logger.exception("Job %s failed at %s", job_id, current_stage)
        repo.set_error(job_id, current_stage, str(exc))
        await transition(job_id, JobStatus.FAILED, stage=current_stage, message=str(exc))
    finally:
        _cancel_requested.discard(job_id)
        _job_llm_api_keys.pop(job_id, None)
