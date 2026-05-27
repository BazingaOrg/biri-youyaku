from pathlib import Path
import re

from biri_youyaku.modules.asr.base import TranscribeRequest
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


SENSEVOICE_TAG_RE = re.compile(r"<\|[^|>]+?\|>")
SENSEVOICE_MARKERS = str.maketrans("", "", "🎼😀😔😡😰🤢😮👏🤣😭🤧😷")


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


class SenseVoiceTranscriber:
    async def transcribe(self, request: TranscribeRequest) -> list[TranscriptItem]:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError("SenseVoice 依赖未安装，请安装 server[asr]") from exc

        model = AutoModel(model="iic/SenseVoiceSmall")
        result = model.generate(input=str(request.audio_path), language=request.language)
        text = "\n".join(
            clean_transcription_text(item.get("text", ""))
            for item in result
            if isinstance(item, dict)
        ).strip()
        return [TranscriptItem(start=0, end=0, text=text)] if text else []


async def transcribe(audio_path: str, language: str = "auto") -> list[TranscriptItem]:
    return await SenseVoiceTranscriber().transcribe(
        TranscribeRequest(audio_path=Path(audio_path), language=language)
    )
