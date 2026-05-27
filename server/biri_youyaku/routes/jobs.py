import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.events import event_bus
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.jobs.runner import cancel_job, clear_job_state, resume_job, start_job
from biri_youyaku.modules.email.webhook import send as send_email
from biri_youyaku.modules.bilibili.meta import VideoMeta

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class JobOptionsPayload(BaseModel):
    task_type: str | None = None
    language: str | None = None
    force_asr: bool | None = None
    summary_language: str | None = None
    email_enabled: bool | None = None
    email_recipient: str | None = None
    email_subject_template: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    prompt_template: str | None = None


class CreateJobPayload(BaseModel):
    url: str
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


class ResumeJobPayload(BaseModel):
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


def _has_audio(job: Job) -> bool:
    if job.audio_path is None:
        return False
    return Path(job.audio_path).is_file()


def serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "url": job.url,
        "bvid": job.bvid,
        "cid": job.cid,
        "title": job.title,
        "author": job.author,
        "duration": job.duration,
        "status": job.status.value,
        "error_stage": job.error_stage,
        "error_message": job.error_message,
        "subtitle_source": job.subtitle_source,
        "chapters": job.chapters or [],
        "transcript": job.transcript or [],
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
        "summary": repo.read_summary(job),
        "options": job.options.as_dict(),
        "option_overrides": job.option_overrides or {},
        "audio_available": _has_audio(job),
    }


def _video_meta_from_job(job: Job) -> VideoMeta:
    return VideoMeta(
        url=job.url,
        bvid=job.bvid or "",
        cid=job.cid,
        title=job.title or job.bvid or job.id,
        author=job.author or "",
        duration=job.duration or 0,
    )


@router.post("/jobs")
async def create_job(payload: CreateJobPayload) -> dict:
    option_overrides = payload.options.model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    options = JobOptions.from_overrides(
        option_overrides,
        settings,
    )
    job = repo.create_job(payload.url, options, option_overrides=option_overrides)
    start_job(job.id, llm_api_key=llm_api_key)
    return {"ok": True, "job_id": job.id}


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    jobs = repo.list_jobs(limit=limit, offset=offset)
    return {"ok": True, "jobs": [serialize_job(job) for job in jobs]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": serialize_job(job)}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    if repo.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def generator():
        job = repo.get_job(job_id)
        if job is not None:
            yield {"event": "status", "data": json.dumps({"status": job.status.value})}
        async with event_bus.subscribe(job_id) as queue:
            while True:
                message = await queue.get()
                yield {"event": message["event"], "data": json.dumps(message["data"], ensure_ascii=False)}

    return EventSourceResponse(generator())


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.TRANSCRIPT_READY:
        repo.update_status(job_id, JobStatus.CANCELED)
        clear_job_state(job_id)
        await event_bus.publish(job_id, "status", {"status": JobStatus.CANCELED.value})
        return {"ok": True}
    cancel_job(job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/resume")
async def resume(job_id: str, payload: ResumeJobPayload | None = None) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.TRANSCRIPT_READY:
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态 {job.status.value}，无法 resume",
        )
    option_overrides = (payload.options if payload else JobOptionsPayload()).model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    if option_overrides:
        options = JobOptions.from_overrides(option_overrides, settings)
        repo.update_options(job_id, options, option_overrides=option_overrides)
    resume_job(job_id, llm_api_key=llm_api_key)
    return {"ok": True}


@router.get("/jobs/{job_id}/audio")
async def download_audio(job_id: str):
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.audio_path is None:
        raise HTTPException(status_code=409, detail="该任务没有可下载音频")

    audio_path = Path(job.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=410, detail="音频文件已被清理")
    if not audio_path.is_file():
        raise HTTPException(status_code=409, detail="音频路径不可下载")

    stem = re.sub(r'[\\/:*?"<>|]+', "_", (job.title or job.bvid or job.id)).strip()
    filename = f"{stem or job.id}{audio_path.suffix or '.wav'}"
    return FileResponse(audio_path, filename=filename, media_type="audio/wav")


TERMINAL_DELETE_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.TRANSCRIPT_READY,
}


def _delete_job_files(job: Job) -> None:
    if job.audio_path:
        audio_path = Path(job.audio_path)
        try:
            if audio_path.is_file():
                audio_path.unlink()
            for sibling in audio_path.parent.glob(f"{job.id}*"):
                if sibling.is_file():
                    sibling.unlink()
        except OSError:
            pass
    if job.summary_path:
        summary_path = Path(job.summary_path)
        try:
            if summary_path.is_file():
                summary_path.unlink()
        except OSError:
            pass


@router.delete("/jobs")
async def delete_all() -> dict:
    skipped_count = repo.count_jobs_excluding_status(TERMINAL_DELETE_STATUSES)
    for job in repo.list_jobs_by_status(TERMINAL_DELETE_STATUSES):
        _delete_job_files(job)
        clear_job_state(job.id)
    deleted_count = repo.delete_jobs_by_status(TERMINAL_DELETE_STATUSES)
    return {"ok": True, "deleted_count": deleted_count, "skipped_count": skipped_count}


@router.delete("/jobs/{job_id}")
async def delete(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in TERMINAL_DELETE_STATUSES:
        raise HTTPException(status_code=409, detail="任务进行中，请先取消再删除")

    _delete_job_files(job)
    deleted = repo.delete_job(job_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    clear_job_state(job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/email")
async def resend_email(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    summary = repo.read_summary(job)
    if job.status != JobStatus.COMPLETED or not summary:
        raise HTTPException(status_code=409, detail="Only completed jobs with a summary can be emailed")
    await send_email(_video_meta_from_job(job), summary, job.options)
    return {"ok": True}
