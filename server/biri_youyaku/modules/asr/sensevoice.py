import asyncio
import logging
import math
import re
import shutil
import subprocess
import tempfile
import time
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

# 60 秒一段：足够短能定时报进度，又不会让 funasr 单段开销过大。
CHUNK_SECONDS = 60.0


def _has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@lru_cache(maxsize=1)
def _load_model():
    """加载 SenseVoice。

    - 有 ffmpeg：我们自己切 chunk，模型可以不带 VAD（每段 60s，VAD 多此一举）。
    - 没 ffmpeg：模型必须带上 fsmn-vad，否则 funasr 会在 1h 整段上跑死。
    """
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise RuntimeError("SenseVoice 依赖未安装，请安装 server[asr]") from exc

    model_name = settings.sensevoice_model_dir or "iic/SenseVoiceSmall"
    use_vad = not _has_ffmpeg()
    if use_vad:
        logger.warning("未检测到 ffmpeg/ffprobe，SenseVoice 将启用内置 VAD 兜底（无逐段进度）")
        return AutoModel(
            model=model_name,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            disable_update=True,
        )
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
    """把 funasr 返回拍平成 TranscriptItem 列表。"""
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
    """用 ffprobe 读时长（秒）。失败返回 0。"""
    if not shutil.which("ffprobe"):
        return 0.0
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
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.warning("ffprobe 读不到时长 %s：%s", audio_path, exc)
        return 0.0


def _slice_audio(audio_path: Path, start: float, duration: float, out_path: Path) -> None:
    """ffmpeg 切一段单声道 16k WAV。"""
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
    return model.generate(input=str(audio_path), language=language, use_itn=True)


async def _emit(on_progress: ProgressCallback | None, items: list[TranscriptItem], pct: float) -> None:
    if on_progress is None:
        return
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

        ffmpeg_ok = _has_ffmpeg()
        duration = await asyncio.to_thread(_probe_duration, audio_path) if ffmpeg_ok else 0.0

        # 情况 A：拿不到时长或音频较短 → 单次推理（短视频 / 没有 ffmpeg 的回退）
        if duration <= CHUNK_SECONDS or not ffmpeg_ok:
            logger.info(
                "SenseVoice 单次推理（duration=%.1fs, ffmpeg=%s, vad-fallback=%s）",
                duration, ffmpeg_ok, not ffmpeg_ok,
            )
            t0 = time.monotonic()
            result = await asyncio.to_thread(_generate_sync, audio_path, language)
            items = _segments_from_result(result, 0.0)
            logger.info("SenseVoice 单次推理完成：%d 段，耗时 %.1fs", len(items), time.monotonic() - t0)
            await _emit(on_progress, items, 1.0)
            return items

        # 情况 B：长视频 + ffmpeg 可用 → 应用层切段，逐段推理 + 进度回传
        chunk_count = max(1, math.ceil(duration / CHUNK_SECONDS))
        logger.info(
            "SenseVoice 分段推理：duration=%.1fs → %d 段（%.0fs/段）",
            duration, chunk_count, CHUNK_SECONDS,
        )
        all_items: list[TranscriptItem] = []
        with tempfile.TemporaryDirectory(prefix="biri_asr_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            for idx in range(chunk_count):
                start = idx * CHUNK_SECONDS
                chunk_dur = min(CHUNK_SECONDS, duration - start)
                if chunk_dur <= 0.2:
                    continue
                chunk_path = tmpdir_path / f"chunk_{idx:04d}.wav"
                t0 = time.monotonic()
                try:
                    await asyncio.to_thread(_slice_audio, audio_path, start, chunk_dur, chunk_path)
                    result = await asyncio.to_thread(_generate_sync, chunk_path, language)
                except Exception:
                    logger.exception("第 %d/%d 段转写失败，跳过", idx + 1, chunk_count)
                    continue
                new_items = _segments_from_result(result, time_offset=start)
                all_items.extend(new_items)
                pct = (idx + 1) / chunk_count
                logger.info(
                    "段 %d/%d 完成：本段 %d 句，累计 %d 句，耗时 %.1fs（进度 %.0f%%）",
                    idx + 1, chunk_count, len(new_items), len(all_items),
                    time.monotonic() - t0, pct * 100,
                )
                await _emit(on_progress, all_items, pct)
                await asyncio.sleep(0)
        logger.info("SenseVoice 分段推理完成：共 %d 句", len(all_items))
        return all_items


async def transcribe(audio_path: str, language: str = "auto") -> list[TranscriptItem]:
    return await SenseVoiceTranscriber().transcribe(
        TranscribeRequest(audio_path=Path(audio_path), language=language)
    )
