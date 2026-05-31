import json
import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.events import event_bus
from biri_youyaku.jobs.cleanup import TERMINAL_DELETE_STATUSES, delete_job_files
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.jobs.runner import cancel_job, clear_job_state, resume_job, retry_job, start_job
from biri_youyaku.modules.email.webhook import send as send_email
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.rate_limit import limiter
from biri_youyaku.routes.config import _validate_llm_base_url

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


class RetryJobPayload(BaseModel):
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


class TranscriptItemPayload(BaseModel):
    start: float = 0
    end: float = 0
    text: str


class ReplaceTranscriptPayload(BaseModel):
    transcript: list[TranscriptItemPayload]
    source: str = "upload"


class PreviewJobPayload(BaseModel):
    url: str


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
        "error_code": job.error_code,
        "subtitle_source": job.subtitle_source,
        "chapters": job.chapters or [],
        "transcript": job.transcript or [],
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
        "stream_finished_at": job.stream_finished_at,
        "token_usage": job.token_usage,
        "stage_timings": job.stage_timings or [],
        "summary": repo.read_summary(job),
        "options": job.options.as_dict(),
        "option_overrides": job.option_overrides or {},
        "audio_available": _has_audio(job),
        "email_error": job.email_error,
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
@limiter.limit("10/minute")
async def create_job(request: Request, payload: CreateJobPayload) -> dict:
    option_overrides = payload.options.model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    options = JobOptions.from_overrides(
        option_overrides,
        settings,
    )
    # 防 SSRF：用户传入的 llm_base_url 必须过白名单（同 /v1/llm/models 规则）
    _validate_llm_base_url(options.llm_base_url)
    # 早失败：开了邮件却没有有效收件人 → 直接拒，别让任务跑完才在 EMAILING 阶段 fail。
    if options.email_enabled:
        effective_recipient = (settings.email_default_recipient or "").strip()
        if not effective_recipient or not settings.email_webhook_url:
            raise HTTPException(
                status_code=400,
                detail=(
                    "邮件已启用但未配置：请在 .env 设置 EMAIL_WEBHOOK_URL 与 "
                    "EMAIL_DEFAULT_RECIPIENT，或本次请求里把 email_enabled 设为 false。"
                ),
            )
    job = repo.create_job(payload.url, options, option_overrides=option_overrides)
    start_job(job.id, llm_api_key=llm_api_key)
    return {"ok": True, "job_id": job.id}


@router.post("/jobs/preview")
@limiter.limit("30/minute")
async def preview_job(request: Request, payload: PreviewJobPayload) -> dict:
    meta = await bili_meta.fetch(payload.url)
    if meta.duration and meta.duration > settings.max_video_duration_seconds:
        raise HTTPException(
            status_code=400,
            detail=(
                f"视频时长 {int(meta.duration // 60)} 分钟，超过上限 "
                f"{settings.max_video_duration_seconds // 60} 分钟。"
            ),
        )
    existing = repo.find_latest_by_video(meta.bvid, meta.cid)
    response = {
        "ok": True,
        "meta": {
            "url": meta.url,
            "bvid": meta.bvid,
            "cid": meta.cid,
            "title": meta.title,
            "author": meta.author,
            "duration": meta.duration,
            "has_subtitle": meta.has_subtitle,
        },
    }
    if existing is not None:
        response["dedup_job_id"] = existing.id
    return response


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    jobs = repo.list_jobs(limit=limit, offset=offset, cursor=cursor)
    next_cursor = jobs[-1].created_at if len(jobs) == limit else None
    return {"ok": True, "jobs": [serialize_job(job) for job in jobs], "next_cursor": next_cursor}


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
            yield {
                "event": "status",
                "data": json.dumps(
                    {
                        "status": job.status.value,
                        "summary": repo.read_summary(job),
                        "stage": job.error_stage,
                        "message": job.error_message,
                        "error_code": job.error_code,
                        "email_error": job.email_error,
                    },
                    ensure_ascii=False,
                ),
            }
            if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                return
        async with event_bus.subscribe(job_id) as queue:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                yield {"event": message["event"], "data": json.dumps(message["data"], ensure_ascii=False)}
                if message["event"] == "status" and message["data"].get("status") in {
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELED.value,
                }:
                    return

    return EventSourceResponse(generator(), ping=25)


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
@limiter.limit("30/minute")
async def resume(request: Request, job_id: str, payload: ResumeJobPayload | None = None) -> dict:
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

    # When force_asr is requested, restart the pipeline from scratch instead of
    # jumping straight to summarize.  We clear the existing transcript/subtitle so
    # run_until_transcript will re-download audio and re-transcribe.
    if option_overrides.get("force_asr"):
        options = JobOptions.from_overrides(option_overrides, settings)
        repo.update_options(job_id, options, option_overrides=option_overrides)
        repo.clear_transcript(job_id)
        repo.clear_error(job_id)
        repo.update_status(job_id, JobStatus.PENDING)
        await event_bus.publish(job_id, "status", {"status": JobStatus.PENDING.value})
        start_job(job_id, llm_api_key=llm_api_key)
        return {"ok": True}

    if option_overrides:
        options = JobOptions.from_overrides(option_overrides, settings)
        repo.update_options(job_id, options, option_overrides=option_overrides)
    resume_job(job_id, llm_api_key=llm_api_key)
    return {"ok": True}


@router.post("/jobs/{job_id}/retry")
@limiter.limit("30/minute")
async def retry(request: Request, job_id: str, payload: RetryJobPayload | None = None) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail=f"任务当前状态 {job.status.value}，无法 retry")
    option_overrides = (payload.options if payload else JobOptionsPayload()).model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    if option_overrides:
        options = JobOptions.from_overrides(option_overrides, settings)
        repo.update_options(job_id, options, option_overrides=option_overrides)
    try:
        retry_job(job_id, llm_api_key=llm_api_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/jobs/{job_id}/transcript")
async def replace_transcript(job_id: str, payload: ReplaceTranscriptPayload) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in TERMINAL_DELETE_STATUSES:
        raise HTTPException(status_code=409, detail="任务进行中，请先取消再覆盖字幕")
    items = [
        TranscriptItem(
            start=item.start,
            end=item.end,
            text=item.text.strip(),
        )
        for item in payload.transcript
        if item.text.strip()
    ]
    if not items:
        raise HTTPException(status_code=400, detail="字幕内容为空")
    repo.set_transcript(job_id, items)
    repo.set_subtitle_source(job_id, payload.source or "upload")
    repo.clear_summary_path(job_id)
    repo.clear_error(job_id)
    repo.update_status(job_id, JobStatus.TRANSCRIPT_READY)
    await event_bus.publish(job_id, "status", {"status": JobStatus.TRANSCRIPT_READY.value})
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


@router.delete("/jobs")
async def delete_all() -> dict:
    skipped_count = repo.count_jobs_excluding_status(TERMINAL_DELETE_STATUSES)
    for job in repo.list_jobs_by_status(TERMINAL_DELETE_STATUSES):
        delete_job_files(job)
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

    delete_job_files(job)
    deleted = repo.delete_job(job_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    clear_job_state(job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/email")
@limiter.limit("10/minute")
async def resend_email(request: Request, job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    summary = repo.read_summary(job)
    if job.status != JobStatus.COMPLETED or not summary:
        raise HTTPException(status_code=409, detail="Only completed jobs with a summary can be emailed")
    await send_email(_video_meta_from_job(job), summary, job.options)
    # 重发成功 → 把上次记下的 email_error 清掉
    repo.set_email_error(job_id, None)
    await event_bus.publish(job_id, "status", {"status": JobStatus.COMPLETED.value, "email_error": None})
    return {"ok": True}
