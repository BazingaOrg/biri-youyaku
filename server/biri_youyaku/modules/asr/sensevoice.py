import asyncio
import logging
import math
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.modules.asr.base import (
    ProgressCallback,
    TranscribeProgress,
    TranscribeRequest,
)
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


logger = logging.getLogger(__name__)

SENSEVOICE_TAG_RE = re.compile(r"<\|[^|>]+?\|>")
SENSEVOICE_MARKERS = str.maketrans("", "", "🎼😀😔😡😰🤢😮👏🤣😭🤧😷")

# 60 秒一段：足够短能定时报进度，又不会让 funasr 的开销过大。
CHUNK_SECONDS = 60.0


@lru_cache(maxsize=1)
def _load_model():
    """加载 SenseVoice。因为我们自己做了分段，模型不再装 VAD（chunk 已经够短）。"""
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise RuntimeError("SenseVoice 依赖未安装，请安装 server[asr]") from exc

    model_name = settings.sensevoice_model_dir or "iic/SenseVoiceSmall"
    return AutoModel(model=model_name, disable_update=True)


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


def _segments_from_result(result: Any, time_offset: float) -> list[TranscriptItem]:
    """把 funasr 返回拍平成 TranscriptItem 列表。

    funasr 返回形如 ``[{"text": "...", "sentence_info"?: [{"start"/"end" ms, "text"}]}]``。
    `time_offset` 是这段 chunk 在整段音频里的起始秒数，用来还原全局时间戳。
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
                cleaned = clean_transcription_text(s.get("text") or "")
                if not cleaned:
                    continue
                start_ms = float(s.get("start") or 0)
                end_ms = float(s.get("end") or start_ms)
                items.append(
                    TranscriptItem(
                        start=time_offset + start_ms / 1000.0,
                        end=time_offset + end_ms / 1000.0,
                        text=cleaned,
                    )
                )
            continue
        cleaned = clean_transcription_text(entry.get("text") or "")
        if cleaned:
            items.append(TranscriptItem(start=time_offset, end=time_offset, text=cleaned))
    return items


def _probe_duration(audio_path: Path) -> float:
    """用 ffprobe 读时长（秒）。失败回退到 0 表示无法分段。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return float(result.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        logger.warning("ffprobe 拿不到时长，将按整段推理：%s", audio_path)
        return 0.0


def _slice_audio(audio_path: Path, start: float, duration: float, out_path: Path) -> None:
    """ffmpeg 切一段单声道 16k WAV，喂给 funasr。"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
            "-i", str(audio_path),
            "-ac", "1", "-ar", "16000", "-f", "wav",
            str(out_path),
        ],
        check=True, timeout=120,
    )


def _generate_sync(audio_path: Path, language: str) -> Any:
    model = _load_model()
    return model.generate(
        input=str(audio_path),
        language=language,
        use_itn=True,
    )


async def _emit(on_progress: ProgressCallback | None, items: list[TranscriptItem], pct: float) -> None:
    if on_progress is None:
        return
    # preview: 最近一段的尾巴，方便前端展示「正在识别…<某句话>」
    last_text = items[-1].text if items else ""
    preview = last_text[-200:] if len(last_text) > 200 else last_text
    try:
        await on_progress(TranscribeProgress(percent=pct, items_count=len(items), preview=preview))
    except Exception:
        logger.exception("transcribe progress callback failed")


class SenseVoiceTranscriber:
    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> list[TranscriptItem]:
        audio_path = request.audio_path
        language = request.language
        duration = await asyncio.to_thread(_probe_duration, audio_path)

        # 拿不到时长 / 短音频：退回单次推理。仍然走 to_thread 释放 event loop。
        if duration <= CHUNK_SECONDS:
            result = await asyncio.to_thread(_generate_sync, audio_path, language)
            items = _segments_from_result(result, 0.0)
            await _emit(on_progress, items, 1.0)
            return items

        chunk_count = max(1, math.ceil(duration / CHUNK_SECONDS))
        all_items: list[TranscriptItem] = []
        logger.info("SenseVoice 分段：总时长 %.1fs → %d 段（%.0fs/段）", duration, chunk_count, CHUNK_SECONDS)

        with tempfile.TemporaryDirectory(prefix="biri_asr_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            for idx in range(chunk_count):
                start = idx * CHUNK_SECONDS
                chunk_dur = min(CHUNK_SECONDS, duration - start)
                if chunk_dur <= 0.2:
                    continue
                chunk_path = tmpdir_path / f"chunk_{idx:04d}.wav"
                try:
                    await asyncio.to_thread(_slice_audio, audio_path, start, chunk_dur, chunk_path)
                    result = await asyncio.to_thread(_generate_sync, chunk_path, language)
                except Exception:
                    logger.exception("第 %d 段转写失败，跳过", idx + 1)
                    continue
                all_items.extend(_segments_from_result(result, time_offset=start))
                pct = (idx + 1) / chunk_count
                await _emit(on_progress, all_items, pct)
                # 主动让步：避免 CPU 长时间占满影响其他协程
                await asyncio.sleep(0)
        return all_items


async def transcribe(audio_path: str, language: str = "auto") -> list[TranscriptItem]:
    return await SenseVoiceTranscriber().transcribe(
        TranscribeRequest(audio_path=Path(audio_path), language=language)
    )
