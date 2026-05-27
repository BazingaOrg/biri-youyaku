from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobOptions
from biri_youyaku.modules.asr.base import TranscribeRequest
from biri_youyaku.modules.asr.sensevoice import SenseVoiceTranscriber
from biri_youyaku.modules.bilibili import audio, meta, subtitle
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.email import webhook
from biri_youyaku.modules.llm import client as llm_client
from biri_youyaku.modules.storage import audio as audio_storage
from biri_youyaku.modules.storage import summary as summary_storage


class CanceledError(Exception):
    pass


async def fetch_platform_transcript(job: Job, video_meta: VideoMeta) -> list[TranscriptItem]:
    items = await subtitle.download(video_meta.subtitle_url or "")
    repo.set_subtitle_source(job.id, "platform")
    return items


async def download_audio(job: Job, video_meta: VideoMeta) -> Path:
    audio_path = await audio.download(video_meta, audio_storage.path_for(job.id))
    repo.set_audio_path(job.id, audio_path)
    return audio_path


async def transcribe_audio(job: Job, audio_path: Path) -> list[TranscriptItem]:
    transcriber = SenseVoiceTranscriber()
    items = await transcriber.transcribe(
        TranscribeRequest(audio_path=audio_path, language=job.options.language or settings.asr_language_default)
    )
    repo.set_subtitle_source(job.id, "asr")
    return items


async def summarize(
    job: Job,
    video_meta: VideoMeta,
    items: list[TranscriptItem],
    *,
    llm_api_key: str | None = None,
) -> str:
    summary_md = await llm_client.summarize(
        items,
        video_meta,
        job.options,
        api_key=llm_api_key,
        subtitle_source=job.subtitle_source,
    )
    summary_path = summary_storage.save(job.id, summary_md)
    repo.set_summary_path(job.id, summary_path)
    return summary_md


async def send_email(video_meta: VideoMeta, summary_md: str, options: JobOptions) -> None:
    await webhook.send(video_meta, summary_md, options)


async def fetch_meta(url: str) -> VideoMeta:
    return await meta.fetch(url)
