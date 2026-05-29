import asyncio

from biri_youyaku.config import settings
from biri_youyaku.modules.asr.base import (
    ProgressCallback,
    TranscribeProgress,
    TranscribeRequest,
)
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


def resolve_device() -> str:
    if settings.asr_device and settings.asr_device != "auto":
        return settings.asr_device
    return "auto"


def _run_sync(audio_path: str, language: str | None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper 依赖未安装，请安装 faster-whisper 后再设置 ASR_MODEL=faster-whisper"
        ) from exc
    model = WhisperModel(settings.sensevoice_model_dir or "small", device=resolve_device())
    segments, info = model.transcribe(audio_path, language=language)
    # 物化为列表，便于后面遍历两次（边推边算进度）
    return list(segments), info


class FasterWhisperTranscriber:
    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> list[TranscriptItem]:
        language = None if request.language == "auto" else request.language
        segments, info = await asyncio.to_thread(_run_sync, str(request.audio_path), language)
        items: list[TranscriptItem] = []
        total_duration = float(getattr(info, "duration", 0) or 0)
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            items.append(TranscriptItem(start=float(seg.start), end=float(seg.end), text=text))
            if on_progress and total_duration > 0:
                pct = min(1.0, float(seg.end) / total_duration)
                preview = text[-200:]
                try:
                    await on_progress(TranscribeProgress(percent=pct, items_count=len(items), preview=preview))
                except Exception:
                    pass
        if on_progress:
            try:
                await on_progress(TranscribeProgress(percent=1.0, items_count=len(items), preview=items[-1].text if items else ""))
            except Exception:
                pass
        return items
