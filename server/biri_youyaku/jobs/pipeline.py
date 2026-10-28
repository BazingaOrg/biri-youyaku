from pathlib import Path
from collections.abc import Awaitable, Callable

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobOptions
from biri_youyaku.modules.asr import get_transcriber
from biri_youyaku.modules.asr.base import ProgressCallback, TranscribeRequest
from biri_youyaku.modules.bilibili import audio, subtitle
from biri_youyaku.sources.model import MediaMeta as VideoMeta
from biri_youyaku.sources import uploads, youtube
from biri_youyaku.sources.service import fetch_meta as fetch_source_meta
from biri_youyaku.modules.email import webhook
from biri_youyaku.modules.llm import client as llm_client
from biri_youyaku.modules.storage import audio as audio_storage
from biri_youyaku.modules.storage import summary as summary_storage
from biri_youyaku.modules.transcript import TranscriptItem


class CanceledError(Exception):
    pass


async def fetch_platform_transcript(job: Job, video_meta: VideoMeta) -> list[TranscriptItem]:
    if video_meta.provider == "youtube":
        items = await youtube.transcript(video_meta)
    elif video_meta.provider == "upload":
        path = uploads.resolve_input(Path(job.input_path or ""), settings.upload_storage_dir)
        items = uploads.parse_subtitles(path.read_bytes(), path.suffix)
    else:
        items = await subtitle.download(video_meta.subtitle_url or "")
    repo.set_subtitle_source(job.id, video_meta.subtitle_source or "platform")
    repo.set_subtitle_language(job.id, video_meta.subtitle_language)
    return items


async def download_audio(
    job: Job,
    video_meta: VideoMeta,
    *,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> Path:
    if video_meta.provider == "upload":
        path = uploads.resolve_input(Path(job.input_path or ""), settings.upload_storage_dir)
        audio_path = await uploads.prepare_audio(path, audio_storage.path_for(job.id).with_suffix(".wav"))
    elif video_meta.provider == "youtube":
        audio_path = await youtube.download(video_meta, audio_storage.path_for(job.id), on_progress=on_progress)
    else:
        audio_path = await audio.download(video_meta, audio_storage.path_for(job.id), on_progress=on_progress)
    repo.set_audio_path(job.id, audio_path)
    return audio_path


async def transcribe_audio(
    job: Job,
    audio_path: Path,
    *,
    on_progress: ProgressCallback | None = None,
) -> list[TranscriptItem]:
    transcriber = get_transcriber(settings.asr_model)
    items = await transcriber.transcribe(
        TranscribeRequest(audio_path=audio_path, language=job.options.language or settings.asr_language_default),
        on_progress=on_progress,
    )
    repo.set_subtitle_source(job.id, "asr")
    repo.set_subtitle_language(job.id, job.options.language if job.options.language != "auto" else None)
    return items


async def summarize(
    job: Job,
    video_meta: VideoMeta,
    items: list[TranscriptItem],
    *,
    llm_api_key: str | None = None,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_usage: Callable[[dict], Awaitable[None]] | None = None,
    on_segment: Callable[[int, int], Awaitable[None]] | None = None,
) -> str:
    summary_md = await llm_client.summarize(
        items,
        video_meta,
        job.options,
        api_key=llm_api_key,
        subtitle_source=job.subtitle_source,
        on_chunk=on_chunk,
        on_usage=on_usage,
        on_segment=on_segment,
        usage_job_id=job.id,
    )
    summary_path = summary_storage.save(job.id, summary_md)
    repo.set_summary_path(job.id, summary_path)
    return summary_md


async def send_email(video_meta: VideoMeta, summary_md: str, options: JobOptions) -> None:
    await webhook.send(video_meta, summary_md, options)


async def fetch_meta(url: str) -> VideoMeta:
    return await fetch_source_meta(url)


async def fetch_upload_meta(job: Job) -> VideoMeta:
    path = uploads.resolve_input(Path(job.input_path or ""), settings.upload_storage_dir)
    is_subtitle = path.suffix.lower() in uploads.SUBTITLE_SUFFIXES
    if is_subtitle:
        items = uploads.parse_subtitles(path.read_bytes(), path.suffix)
        duration = max(item.end for item in items)
    else:
        duration = await uploads.probe_media(path)
    return VideoMeta(
        url=job.url, bvid="", cid=None, title=job.title or "导入内容", author="",
        duration=duration, provider="upload", source_id=job.source_id,
        source_part="", subtitle_url="uploaded" if is_subtitle else None,
        subtitle_source="uploaded" if is_subtitle else None,
    )
