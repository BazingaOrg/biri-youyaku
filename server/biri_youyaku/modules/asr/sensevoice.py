import asyncio
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.modules.asr.base import TranscribeRequest
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


SENSEVOICE_TAG_RE = re.compile(r"<\|[^|>]+?\|>")
SENSEVOICE_MARKERS = str.maketrans("", "", "🎼😀😔😡😰🤢😮👏🤣😭🤧😷")


@lru_cache(maxsize=1)
def _load_model():
    """Build a SenseVoice model with VAD enabled so we can handle long videos.

    Without a VAD front-end, ``model.generate(input=<1h audio>)`` either OOMs
    or runs for hours synchronously. The fsmn-vad VAD segments the audio into
    <=30s chunks and SenseVoice processes them with bounded memory.
    """
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise RuntimeError("SenseVoice 依赖未安装，请安装 server[asr]") from exc

    model_name = settings.sensevoice_model_dir or "iic/SenseVoiceSmall"
    return AutoModel(
        model=model_name,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},  # 30s per chunk
        # 本地推理：留给 funasr 自动选择 cuda/cpu。
        disable_update=True,
    )


def clean_transcription_text(text: str) -> str:
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except ImportError:
        processed = text
    else:
        processed = rich_transcription_postprocess(text)

    processed = SENSEVOICE_TAG_RE.sub("", processed)
    processed = processed.translate(SENSEVOICE_MARKERS)
    return re.sub(r"\s+", " ", processed).strip()


def _segments_from_result(result: Any) -> list[TranscriptItem]:
    """Flatten funasr 的返回，尽量保留每段时间戳。

    funasr SenseVoice + VAD 通常返回 ``[{"text": "<|..|>...", "sentence_info": [...]}]``。
    sentence_info 形如 ``[{"text": "...", "start": 100, "end": 1500}, ...]`` —— 单位毫秒。
    没有 sentence_info 就退化成一整段，时间戳为 0。
    """
    items: list[TranscriptItem] = []
    if not isinstance(result, list):
        return items

    for entry in result:
        if not isinstance(entry, dict):
            continue
        sentences = entry.get("sentence_info")
        if isinstance(sentences, list) and sentences:
            for s in sentences:
                if not isinstance(s, dict):
                    continue
                raw_text = s.get("text") or ""
                cleaned = clean_transcription_text(raw_text)
                if not cleaned:
                    continue
                start_ms = float(s.get("start") or 0)
                end_ms = float(s.get("end") or start_ms)
                items.append(
                    TranscriptItem(
                        start=start_ms / 1000.0,
                        end=end_ms / 1000.0,
                        text=cleaned,
                    )
                )
            continue
        cleaned = clean_transcription_text(entry.get("text") or "")
        if cleaned:
            items.append(TranscriptItem(start=0.0, end=0.0, text=cleaned))
    return items


def _generate_sync(audio_path: Path, language: str) -> Any:
    model = _load_model()
    return model.generate(
        input=str(audio_path),
        language=language,
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )


class SenseVoiceTranscriber:
    async def transcribe(self, request: TranscribeRequest) -> list[TranscriptItem]:
        # 同步推理放到线程池，避免堵住 FastAPI event loop（否则 SSE/keepalive 全部停摆）
        result = await asyncio.to_thread(_generate_sync, request.audio_path, request.language)
        items = _segments_from_result(result)
        return items


async def transcribe(audio_path: str, language: str = "auto") -> list[TranscriptItem]:
    return await SenseVoiceTranscriber().transcribe(
        TranscribeRequest(audio_path=Path(audio_path), language=language)
    )
