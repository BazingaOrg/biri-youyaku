import asyncio
from pathlib import Path
import shutil
from urllib.parse import urlparse

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from biri_youyaku.auth import require_token
from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.runner import resume_job, start_job
from biri_youyaku.rate_limit import limiter
from biri_youyaku.routes.jobs import _ensure_inflight_capacity, creation_lock
from biri_youyaku.sources.capabilities import capabilities
from biri_youyaku.sources.service import fetch_meta
from biri_youyaku.sources import uploads


router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
_upload_lock = asyncio.Lock()


@router.get("/sources/capabilities")
async def get_capabilities() -> dict:
    return capabilities()


@router.get("/sources/resolve")
@limiter.limit("20/minute")
async def resolve_source(request: Request, url: str = Query(max_length=2048)) -> dict:
    from biri_youyaku.routes.jobs import CreateJobPayload

    try:
        CreateJobPayload(url=url)
        media = await asyncio.wait_for(fetch_meta(url), timeout=35)
    except (ValueError, RuntimeError, TimeoutError, httpx.HTTPError):
        raise HTTPException(400, "无法识别内容，请检查链接或稍后重试") from None
    source_id = media.source_id or media.bvid
    part = (
        str(media.cid)
        if media.provider == "bilibili" and media.cid is not None
        else media.source_part or ""
    )
    with connect() as connection:
        doc = connection.execute(
            "SELECT id, title, updated_at, deleted_at FROM knowledge_documents WHERE provider=? AND source_id=? AND source_part=?",
            (media.provider, source_id, part),
        ).fetchone()
    existing = None
    trashed = None
    if doc is not None:
        if doc["deleted_at"] is not None:
            from biri_youyaku.config import KNOWLEDGE_SOFT_DELETE_DAYS

            remaining = (
                KNOWLEDGE_SOFT_DELETE_DAYS - (repo.now_ms() - doc["deleted_at"]) // 86_400_000
            )
            trashed = {
                "document_id": doc["id"],
                "title": doc["title"],
                "days_left": max(0, remaining),
            }
        else:
            existing = {
                "document_id": doc["id"],
                "title": doc["title"],
                "saved_at": doc["updated_at"],
            }
    active = repo.find_reusable_source(media.provider, source_id, part, task_type="summary")
    return {
        "provider": media.provider,
        "source_id": source_id,
        "source_part": part,
        "canonical_url": media.url,
        "existing": existing,
        "trashed": trashed,
        "active_job_id": active.id
        if active is not None
        and active.status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}
        else None,
    }


@router.post("/imports")
@limiter.limit("6/minute")
async def import_file(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    title: str = Query(default="", max_length=300),
    source_url: str = Query(default="", max_length=2048),
) -> dict:
    source_url = source_url.strip()
    if source_url:
        try:
            parsed = urlparse(source_url)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and parsed.port in {None, 80, 443}
            )
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(400, "来源链接必须是有效的 HTTP/HTTPS 页面地址")
    if _upload_lock.locked():
        raise HTTPException(429, "已有文件正在上传，请稍后重试")
    accepted = False
    uploaded = None
    job = None
    async with _upload_lock:
        _ensure_inflight_capacity()
        root = Path(settings.upload_storage_dir)
        root.mkdir(parents=True, exist_ok=True)
        size = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
        if size + settings.upload_max_bytes > settings.upload_storage_max_bytes:
            raise HTTPException(507, "导入目录空间不足，请清理旧任务后重试")
        if (
            shutil.disk_usage(root).free
            < settings.upload_min_free_bytes + settings.upload_max_bytes
        ):
            raise HTTPException(507, "服务器可用磁盘空间不足")
        try:
            suffix = Path(filename).suffix.lower()
            if suffix in uploads.MEDIA_SUFFIXES:
                available = capabilities()
                if not (
                    available["ffmpeg"] and available["ffprobe"] and available["asr"]["installed"]
                ):
                    raise HTTPException(
                        409, "后端尚未安装音频处理或转写依赖，可先导入 SRT/VTT 字幕"
                    )
            uploaded = await asyncio.wait_for(
                uploads.receive(request, filename, root=root, max_bytes=settings.upload_max_bytes),
                timeout=300,
            )
            items = None
            if uploaded.kind == "subtitle":
                items = uploads.parse_subtitles(uploaded.path.read_bytes(), uploaded.path.suffix)
                duration = max(item.end for item in items)
            else:
                duration = await uploads.probe_media(uploaded.path)
            if duration > settings.max_video_duration_seconds:
                raise HTTPException(400, "内容时长超过服务器上限")
            async with creation_lock:
                existing = repo.find_reusable_source(
                    "upload", uploaded.sha256, "", task_type="summary"
                )
                if existing is not None:
                    return {"ok": True, "job_id": existing.id, "deduped": True}
                _ensure_inflight_capacity()
                options = JobOptions.from_settings(settings)
                job = repo.create_job(
                    source_url or f"upload://{uploaded.sha256}",
                    options,
                    source_provider="upload",
                    source_id=uploaded.sha256,
                    input_path=str(uploaded.path.resolve()),
                    title=title.strip() or Path(uploaded.filename).stem,
                    duration=duration,
                )
                if items is not None:
                    repo.set_transcript(job.id, items)
                    repo.set_subtitle_source(job.id, "uploaded")
                    repo.update_status(job.id, JobStatus.TRANSCRIPT_READY)
                    resume_job(job.id)
                else:
                    start_job(job.id)
                accepted = True
            return {"ok": True, "job_id": job.id, "deduped": False}
        except uploads.UploadError as exc:
            raise HTTPException(400, str(exc)) from None
        except TimeoutError:
            raise HTTPException(408, "上传或校验超时，请重试") from None
        finally:
            if not accepted:
                if uploaded is not None:
                    uploaded.path.unlink(missing_ok=True)
                if job is not None:
                    repo.delete_job(job.id)
