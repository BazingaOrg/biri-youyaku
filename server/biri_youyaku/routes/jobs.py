import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.events import SubscriberClosed, event_bus
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.cleanup import (
    collect_job_file_cleanup_targets,
    delete_job_files,
    delete_job_file_targets_with_result,
    enqueue_pending_file_cleanup,
)
from biri_youyaku.jobs.model import (
    BULK_DELETE_JOB_STATUSES,
    Job,
    JobOptions,
    JobStatus,
    RETENTION_DELETE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    TERMINAL_JOB_STATUS_VALUES,
    video_meta_from_job,
)
from biri_youyaku.jobs.runner import (
    cancel_job,
    clear_job_state,
    resume_job,
    retry_job,
    start_job,
)
from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.modules.email.webhook import send as send_email
from biri_youyaku.llm_url import validate_llm_base_url
from biri_youyaku.rate_limit import limiter
from biri_youyaku.weekly import repo as weekly_summary_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


class JobOptionsPayload(BaseModel):
    task_type: Literal["summary", "audio", "distill"] | None = None
    language: str | None = None
    force_asr: bool | None = None
    summary_language: str | None = None
    email_enabled: bool | None = None
    email_subject_template: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    prompt_template: str | None = None


class CreateJobPayload(BaseModel):
    url: str
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)
    dedupe: bool = True


class ResumeJobPayload(BaseModel):
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


class RetryJobPayload(BaseModel):
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


class ResummarizeJobPayload(BaseModel):
    options: JobOptionsPayload = Field(default_factory=JobOptionsPayload)


class BulkDeleteFilterPayload(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    tag: str | None = Field(default=None, max_length=100)


class BulkDeleteExecutePayload(BaseModel):
    preview_token: str = Field(min_length=1, max_length=4096)


_BULK_DELETE_PREVIEW_TTL_MS = 5 * 60 * 1000
_bulk_delete_signing_secret = secrets.token_bytes(32)


def _normalize_bulk_delete_filters(payload: BulkDeleteFilterPayload) -> dict[str, str | None]:
    raw = {"query": payload.query, "author": payload.author, "tag": payload.tag}
    return {
        key: (value.strip() or None) if value is not None else None for key, value in raw.items()
    }


def _bulk_delete_candidate_hash(jobs: list[Job]) -> str:
    # The preview displays status counts.  Hash the status with each id so a
    # COMPLETED -> FAILED transition cannot execute against stale preview text.
    candidates = [f"{job.id}\x1f{job.status.value}" for job in jobs]
    return hashlib.sha256("\n".join(candidates).encode("utf-8")).hexdigest()


def _encode_bulk_delete_preview(
    filters: dict[str, str | None],
    jobs: list[Job],
    affected_week_starts: list[str],
    *,
    expires_at: int,
) -> str:
    payload = {
        "expires_at": expires_at,
        "filters": filters,
        "candidate_hash": _bulk_delete_candidate_hash(jobs),
        "affected_week_starts": affected_week_starts,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    signature = hmac.new(_bulk_delete_signing_secret, raw, hashlib.sha256).digest()
    return f"{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def _decode_bulk_delete_preview(token: str) -> dict:
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        raw = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
    except (ValueError, UnicodeEncodeError):
        raise HTTPException(status_code=400, detail="删除预览无效，请重新预览") from None
    expected = hmac.new(_bulk_delete_signing_secret, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="删除预览无效，请重新预览")
    try:
        payload = json.loads(raw)
        filters = payload["filters"]
        if not isinstance(filters, dict) or set(filters) != {"query", "author", "tag"}:
            raise ValueError
        if any(value is not None and not isinstance(value, str) for value in filters.values()):
            raise ValueError
        if not isinstance(payload["candidate_hash"], str) or not isinstance(
            payload["expires_at"], int
        ):
            raise ValueError
        week_starts = payload["affected_week_starts"]
        if not isinstance(week_starts, list) or week_starts != sorted(week_starts):
            raise ValueError
        if any(not isinstance(week_start, str) for week_start in week_starts):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="删除预览无效，请重新预览") from None
    if payload["expires_at"] < repo.now_ms():
        raise HTTPException(status_code=409, detail="删除预览已过期，请重新预览")
    return payload


def _bulk_delete_preview_response(filters: dict[str, str | None], jobs: list[Job]) -> dict:
    affected_week_starts = weekly_summary_repo.affected_week_starts_for_job_ids(
        [job.id for job in jobs]
    )
    expires_at = repo.now_ms() + _BULK_DELETE_PREVIEW_TTL_MS
    by_status = {
        status.value: 0
        for status in sorted(BULK_DELETE_JOB_STATUSES, key=lambda status: status.value)
    }
    for job in jobs:
        by_status[job.status.value] += 1
    sample = [
        {
            "id": job.id,
            "title": job.title or job.bvid or job.id,
            "author": job.author,
            "created_at": job.created_at,
            "status": job.status.value,
        }
        for job in jobs[:5]
    ]
    return {
        "ok": True,
        "matched_count": len(jobs),
        "by_status": by_status,
        "sample": sample,
        "sample_truncated_count": max(0, len(jobs) - len(sample)),
        "affected_weekly_summaries": len(affected_week_starts),
        "expires_at": expires_at,
        "preview_token": _encode_bulk_delete_preview(
            filters, jobs, affected_week_starts, expires_at=expires_at
        ),
    }


def _has_audio(job: Job) -> bool:
    if job.audio_path is None:
        return False
    return Path(job.audio_path).is_file()


def serialize_job(job: Job, *, lite: bool = False) -> dict:
    """把 Job 序列化成 API 响应。

    lite=True 给列表页用：不读 summary 磁盘文件、不带 transcript/chapters/stage_timings
    全文。详情页一条记录无所谓，但列表几百条都走 read_summary() 读盘 = 几百次磁盘读 +
    几兆 JSON。lite 投影下这些大字段已是 None，总结只用 summary_available 布尔标记替代。
    """
    payload = {
        "id": job.id,
        "url": job.url,
        "bvid": job.bvid,
        "cid": job.cid,
        "mid": job.mid,
        "title": job.title,
        "author": job.author,
        "duration": job.duration,
        "status": job.status.value,
        "error_stage": job.error_stage,
        "error_message": job.error_message,
        "error_code": job.error_code,
        "subtitle_source": job.subtitle_source,
        "chapters": [] if lite else (job.chapters or []),
        "transcript": [] if lite else (job.transcript or []),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
        "stream_finished_at": job.stream_finished_at,
        "token_usage": job.token_usage,
        "stage_timings": [] if lite else (job.stage_timings or []),
        "summary": None if lite else repo.read_summary(job),
        "options": job.options.as_dict(),
        "option_overrides": job.option_overrides or {},
        "audio_available": _has_audio(job),
        "email_error": job.email_error,
        "tags": job.tags or [],
    }
    if lite:
        payload["summary_available"] = job.summary_path is not None
    return payload


def _extract_option_overrides(options: JobOptionsPayload | None) -> tuple[dict, str | None]:
    option_overrides = (options or JobOptionsPayload()).model_dump(exclude_unset=True)
    llm_api_key = option_overrides.pop("llm_api_key", None)
    return option_overrides, llm_api_key


def _job_options_from_overrides(option_overrides: dict) -> JobOptions:
    options = JobOptions.from_overrides(option_overrides, settings)
    validate_llm_base_url(options.llm_base_url)
    return options


def _ensure_email_ready() -> None:
    webhook_url = (settings.email_webhook_url or "").strip()
    webhook_token = (settings.email_webhook_token or "").strip()
    effective_recipient = (settings.email_default_recipient or "").strip()
    if webhook_url and webhook_token and effective_recipient:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "邮件已启用但未配置：请在 .env 设置 EMAIL_WEBHOOK_URL、EMAIL_WEBHOOK_TOKEN 与 "
            "EMAIL_DEFAULT_RECIPIENT，或本次请求里把 email_enabled 设为 false。"
        ),
    )


def _ensure_inflight_capacity() -> None:
    # 容量保护：单 IP 限流挡不住多 IP 协同灌任务；这里看全局在飞总数兜底。
    # 注意这是「近似/软上限」——count 与下面的 create_job 不在同一事务里，并发请求
    # 可能都通过检查再各自 insert，短暂越过 max_inflight_jobs。单用户场景下足够；要硬
    # 上限需把 SELECT COUNT + INSERT 收进一个 BEGIN IMMEDIATE 事务。
    inflight = repo.count_jobs_excluding_status(TERMINAL_JOB_STATUSES)
    if inflight >= settings.max_inflight_jobs:
        raise HTTPException(
            status_code=503,
            detail=f"服务器忙不过来（在飞任务 {inflight}/{settings.max_inflight_jobs}），请稍后重试",
        )


@router.post("/jobs")
@limiter.limit("10/minute")
async def create_job(request: Request, payload: CreateJobPayload) -> dict:
    # 去重：粘到「已经总结完成」的同一个视频（按 BV 号）就直接复用旧结果，不重复烧 token。
    # BV 直接从 URL 提取（无需网络）；b23 短链等取不到 BV 的跳过去重照常建。
    try:
        bvid = bili_meta.extract_bvid(payload.url)
    except ValueError:
        bvid = None
    source_url = (
        bili_meta.canonical_video_url(bvid, bili_meta.extract_page_number(payload.url))
        if bvid
        else payload.url
    )
    if payload.dedupe and bvid:
        existing = repo.find_completed_by_bvid(bvid)
        if existing is not None:
            return {"ok": True, "job_id": existing.id, "deduped": True}

    _ensure_inflight_capacity()
    option_overrides, llm_api_key = _extract_option_overrides(payload.options)
    options = _job_options_from_overrides(option_overrides)
    # 早失败：开了邮件却没有有效收件人 → 直接拒，别让任务跑完才在 EMAILING 阶段 fail。
    if options.email_enabled:
        _ensure_email_ready()
    job = repo.create_job(source_url, options, option_overrides=option_overrides)
    start_job(job.id, llm_api_key=llm_api_key)
    return {"ok": True, "job_id": job.id}


@router.post("/jobs/{job_id}/resummarize")
@limiter.limit("10/minute")
async def resummarize(
    request: Request, job_id: str, payload: ResummarizeJobPayload | None = None
) -> dict:
    source = repo.get_job(job_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not source.transcript:
        raise HTTPException(status_code=409, detail="该任务没有可复用的字幕，无法重新总结")

    _ensure_inflight_capacity()
    option_overrides, llm_api_key = _extract_option_overrides(payload.options if payload else None)
    options = _job_options_from_overrides(option_overrides)
    if options.email_enabled:
        _ensure_email_ready()
    job = repo.create_resummary_job(source, options, option_overrides=option_overrides)
    resume_job(job.id, llm_api_key=llm_api_key)
    return {"ok": True, "job_id": job.id}


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None, max_length=200),
    query: str | None = Query(default=None, max_length=200),
    author: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=100),
    active_only: bool = Query(default=False),
    terminal_only: bool = Query(default=False),
) -> dict:
    if active_only and terminal_only:
        raise HTTPException(status_code=422, detail="active_only 与 terminal_only 不能同时使用")
    filters = {
        "query": query.strip() or None if query is not None else None,
        "author": author.strip() or None if author is not None else None,
        "tag": tag.strip() or None if tag is not None else None,
    }
    try:
        jobs = repo.list_jobs(
            limit=limit,
            offset=offset,
            cursor=cursor,
            active_only=active_only,
            terminal_only=terminal_only,
            **filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="历史游标无效") from exc
    if active_only or len(jobs) != limit:
        next_cursor = None
    elif terminal_only:
        next_cursor = repo.encode_history_cursor(jobs[-1], terminal_only=True)
    else:
        # Keep the original list endpoint contract for existing clients.
        next_cursor = jobs[-1].created_at
    return {
        "ok": True,
        "jobs": [serialize_job(job, lite=True) for job in jobs],
        "next_cursor": next_cursor,
    }


@router.get("/jobs/facets")
async def job_facets(search: str | None = Query(default=None, max_length=200)) -> dict:
    return {"ok": True, **repo.list_job_facets(search=search.strip() or None if search else None)}


@router.post("/jobs/bulk-delete/preview")
async def preview_bulk_delete(payload: BulkDeleteFilterPayload) -> dict:
    filters = _normalize_bulk_delete_filters(payload)
    jobs = repo.list_bulk_delete_candidates(**filters)
    return _bulk_delete_preview_response(filters, jobs)


@router.post("/jobs/bulk-delete/execute")
async def execute_bulk_delete(payload: BulkDeleteExecutePayload) -> dict:
    preview = _decode_bulk_delete_preview(payload.preview_token)
    filters = preview["filters"]
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        jobs = repo.list_bulk_delete_candidates(**filters, connection=connection)
        if _bulk_delete_candidate_hash(jobs) != preview["candidate_hash"]:
            connection.rollback()
            raise HTTPException(status_code=409, detail="删除范围已变化，请重新预览")
        job_ids = [job.id for job in jobs]
        if weekly_summary_repo.affected_week_starts_for_job_ids(
            job_ids, connection=connection
        ) != preview["affected_week_starts"]:
            connection.rollback()
            raise HTTPException(status_code=409, detail="删除范围已变化，请重新预览")
        cleanup_targets = [
            target for job in jobs for target in collect_job_file_cleanup_targets(job)
        ]
        affected_weekly_summaries = weekly_summary_repo.mark_stale_for_job_ids(
            job_ids, connection=connection
        )
        # A3: unlink knowledge job links inside the same transaction; never delete artifacts.
        from biri_youyaku.knowledge import unlink_jobs as knowledge_unlink_jobs

        knowledge_unlink_jobs(job_ids, connection=connection)
        deleted_count = repo.delete_jobs_by_ids(job_ids, connection=connection)
        if deleted_count != len(jobs):
            connection.rollback()
            raise HTTPException(status_code=409, detail="删除范围已变化，请重新预览")
        connection.commit()
    except HTTPException:
        raise
    except Exception:
        connection.rollback()
        raise

    cleanup_failures = delete_job_file_targets_with_result(cleanup_targets)
    if cleanup_failures:
        enqueue_pending_file_cleanup(cleanup_failures)
    for job in jobs:
        clear_job_state(job.id)
    return {
        "ok": True,
        "deleted_count": deleted_count,
        "affected_weekly_summaries": affected_weekly_summaries,
        "cleanup_pending_count": len(cleanup_failures),
        "cleanup_failures": [
            {
                "job_id": failure["job_id"],
                "file_type": "audio" if failure["file_type"] == "audio_siblings" else failure["file_type"],
            }
            for failure in cleanup_failures
        ],
        "cleanup_retry": "pending_file_cleanup" if cleanup_failures else None,
    }


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

    def _snapshot_payload(job: Job) -> str:
        return json.dumps(
            {
                "status": job.status.value,
                "summary": repo.read_summary(job),
                "stage": job.error_stage,
                "message": job.error_message,
                "error_code": job.error_code,
                "email_error": job.email_error,
            },
            ensure_ascii=False,
        )

    async def generator():
        # 关键时序：必须先 subscribe，再读 snapshot。
        # 反过来（先读 snapshot 再 subscribe）会留出一个窗口：snapshot 是非终态，
        # 但在 subscribe 之前任务已经完成、事件也已经 publish 了——订阅者收不到
        # 任何后续事件，前端会永远停在中间态。
        async with event_bus.subscribe(job_id) as subscriber:
            job = repo.get_job(job_id)
            if job is None:
                # 极端情况：从外层 get_job 到这里之间任务被删了。直接结束流。
                logger.info("stream_job: job %s vanished after handler entry", job_id)
                return
            yield {"event": "status", "data": _snapshot_payload(job)}
            # snapshot 已是终态：发完直接结束，不进 while loop 浪费连接。
            if job.status in TERMINAL_JOB_STATUSES:
                return

            while True:
                try:
                    message = await asyncio.wait_for(subscriber.pop(), timeout=25)
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                except SubscriberClosed:
                    return
                yield {
                    "event": message["event"],
                    "data": json.dumps(message["data"], ensure_ascii=False),
                }
                if (
                    message["event"] == "status"
                    and message["data"].get("status") in TERMINAL_JOB_STATUS_VALUES
                ):
                    return

    return EventSourceResponse(generator(), ping=25)


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # 标记取消 + 取消在跑的 task（现在 transcript→总结 是同一条连续 task，所以
    # 即便处于 TRANSCRIPT_READY 也通常有 task 在跑）。
    # idle CAS 由 runner 完成；只有它实际完成了终态切换才在此发布一次 SSE。
    if cancel_job(job_id):
        clear_job_state(job_id)
        await event_bus.publish(job_id, "status", {"status": JobStatus.CANCELED.value})
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
    option_overrides, llm_api_key = _extract_option_overrides(payload.options if payload else None)

    # When force_asr is requested, restart the pipeline from scratch instead of
    # jumping straight to summarize.  We clear the existing transcript/subtitle so
    # run_until_transcript will re-download audio and re-transcribe.
    if option_overrides.get("force_asr"):
        options = _job_options_from_overrides(option_overrides)
        repo.update_options(job_id, options, option_overrides=option_overrides)
        repo.clear_transcript(job_id)
        repo.clear_error(job_id)
        repo.update_status(job_id, JobStatus.PENDING)
        await event_bus.publish(job_id, "status", {"status": JobStatus.PENDING.value})
        start_job(job_id, llm_api_key=llm_api_key)
        return {"ok": True}

    if option_overrides:
        options = _job_options_from_overrides(option_overrides)
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
    option_overrides, llm_api_key = _extract_option_overrides(payload.options if payload else None)
    if option_overrides:
        options = _job_options_from_overrides(option_overrides)
        repo.update_options(job_id, options, option_overrides=option_overrides)
    try:
        retry_job(job_id, llm_api_key=llm_api_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    raise HTTPException(
        status_code=410,
        detail="批量删除已迁移到删除预览接口，请先调用 /v1/jobs/bulk-delete/preview",
    )


@router.delete("/jobs/{job_id}")
async def delete(job_id: str) -> dict:
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in RETENTION_DELETE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="任务进行中，请先取消再删除")

    weekly_summary_repo.mark_stale_for_job_ids([job.id])
    # A3: unlink knowledge job link; keep knowledge artifacts on disk/DB.
    try:
        from biri_youyaku.knowledge import unlink_job as knowledge_unlink_job

        knowledge_unlink_job(job_id)
    except Exception:
        # best-effort: never block job delete if knowledge unlink fails
        logger.warning("knowledge unlink failed for job %s", job_id, exc_info=True)
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
        raise HTTPException(
            status_code=409, detail="Only completed jobs with a summary can be emailed"
        )
    try:
        await send_email(video_meta_from_job(job), summary, job.options)
    except Exception as exc:
        # 重发失败：更新 email_error（别留旧消息），并把真实原因回给前端，而不是通用 500。
        message = str(exc) or "邮件发送失败"
        repo.set_email_error(job_id, message)
        await event_bus.publish(
            job_id, "status", {"status": JobStatus.COMPLETED.value, "email_error": message}
        )
        raise HTTPException(status_code=502, detail=message) from exc
    # 重发成功 → 把上次记下的 email_error 清掉
    repo.set_email_error(job_id, None)
    await event_bus.publish(
        job_id, "status", {"status": JobStatus.COMPLETED.value, "email_error": None}
    )
    return {"ok": True}
