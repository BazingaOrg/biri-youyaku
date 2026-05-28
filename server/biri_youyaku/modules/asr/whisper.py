from biri_youyaku.config import settings
from biri_youyaku.modules.asr.base import TranscribeRequest
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


def resolve_device() -> str:
    if settings.asr_device and settings.asr_device != "auto":
        return settings.asr_device
    return "auto"


class FasterWhisperTranscriber:
    async def transcribe(self, request: TranscribeRequest) -> list[TranscriptItem]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper 依赖未安装，请安装 faster-whisper 后再设置 ASR_MODEL=faster-whisper") from exc

        model = WhisperModel(
            settings.sensevoice_model_dir or "small",
            device=resolve_device(),
        )
        language = None if request.language == "auto" else request.language
        segments, _ = model.transcribe(str(request.audio_path), language=language)
        return [
            TranscriptItem(start=float(segment.start), end=float(segment.end), text=segment.text.strip())
            for segment in segments
            if segment.text.strip()
        ]
