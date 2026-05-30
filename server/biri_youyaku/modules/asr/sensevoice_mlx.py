"""SenseVoice MLX 后端：通过 `mlx-audio` 在 Apple Silicon 上吃 GPU / ANE。

- 推理速度比 funasr CPU 后端预期快 15-30×（M4 Pro 上 27 分钟中文音频 ≈ 13s）。
- 模型权重与 funasr 后端一致（SenseVoice-Small），输出格式也同源，所以共用
  `sensevoice.clean_transcription_text` 做后处理。
- 仅 macOS Apple Silicon 可用；其它平台请用 `ASR_MODEL=sensevoice`（funasr）。

依赖：`uv sync --extra asr-mlx`（安装 mlx-audio）。
"""

from __future__ import annotations

import asyncio
import logging
import math
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
# 复用 funasr 后端的清洗规则（SenseVoice 模型本身的 tag / emoji 输出特性一致）
from biri_youyaku.modules.asr.sensevoice import (
    CHUNK_SECONDS,
    clean_transcription_text,
)
from biri_youyaku.modules.transcript import TranscriptItem

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model() -> Any:
    """Lazy 加载 mlx-audio 包下的 SenseVoice 模型。第一次调用约 5-10s。"""
    try:
        from mlx_audio.stt.utils import load
    except ImportError as exc:
        raise RuntimeError(
            "mlx-audio 未安装。在 server 目录执行：uv sync --extra asr-mlx"
        ) from exc
    model_id = settings.sensevoice_model_dir or "mlx-community/SenseVoiceSmall"
    logger.info("Loading SenseVoice MLX model: %s", model_id)
    return load(model_id)


def _has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _probe_duration(audio_path: Path) -> float:
    """读音频时长（秒）。失败返回 0。"""
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
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def _slice_audio(audio_path: Path, start: float, duration: float, out_path: Path) -> None:
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


def _items_from_result(result: Any, time_offset: float) -> list[TranscriptItem]:
    """兼容 mlx-audio 各版本：优先 segments/sentences 这种带时间戳的形式；
    否则当成整段文本兜底。
    """
    items: list[TranscriptItem] = []
    segments = getattr(result, "segments", None) or getattr(result, "sentences", None)
    if not segments and isinstance(result, dict):
        segments = result.get("segments") or result.get("sentences")
    if segments:
        for seg in segments:
            if hasattr(seg, "text"):
                text = seg.text
                start = float(getattr(seg, "start", 0) or 0)
                end = float(getattr(seg, "end", start) or start)
            elif isinstance(seg, dict):
                text = str(seg.get("text", ""))
                start = float(seg.get("start", 0) or 0)
                end = float(seg.get("end", start) or start)
            else:
                continue
            cleaned = clean_transcription_text(text)
            if cleaned:
                items.append(
                    TranscriptItem(
                        start=time_offset + start,
                        end=time_offset + end,
                        text=cleaned,
                    )
                )
        return items

    # 兜底：单段 text
    text = getattr(result, "text", None)
    if text is None and isinstance(result, str):
        text = result
    elif text is None and isinstance(result, dict):
        text = result.get("text", "")
    cleaned = clean_transcription_text(str(text or ""))
    if cleaned:
        items.append(TranscriptItem(start=time_offset, end=time_offset, text=cleaned))
    return items


def _generate_sync(audio_path: Path, language: str) -> Any:
    model = _load_model()
    # 不同版本 mlx-audio 的 generate 签名略不同；先尝试 language=，失败再回退
    try:
        return model.generate(audio=str(audio_path), language=language)
    except TypeError:
        return model.generate(audio=str(audio_path))


async def _emit(on_progress: ProgressCallback | None, items: list[TranscriptItem], pct: float) -> None:
    if on_progress is None:
        return
    last = items[-1].text if items else ""
    preview = last[-200:] if len(last) > 200 else last
    try:
        await on_progress(TranscribeProgress(percent=pct, items_count=len(items), preview=preview))
    except Exception:
        logger.exception("transcribe progress callback failed")


class SenseVoiceMLXTranscriber:
    """与 funasr 版 SenseVoiceTranscriber 接口一致，可被 pipeline 直接 swap。"""

    @staticmethod
    def warmup() -> None:
        _load_model()

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

        # 情况 A：短音频 / 没 ffmpeg → 单次推理
        if duration <= CHUNK_SECONDS or not ffmpeg_ok:
            t0 = time.monotonic()
            result = await asyncio.to_thread(_generate_sync, audio_path, language)
            items = _items_from_result(result, 0.0)
            logger.info(
                "SenseVoice-MLX 单次推理：%d 段，耗时 %.1fs",
                len(items), time.monotonic() - t0,
            )
            await _emit(on_progress, items, 1.0)
            return items

        # 情况 B：长音频 + ffmpeg → 应用层切段 + 逐段推理 + 进度回传
        chunk_count = max(1, math.ceil(duration / CHUNK_SECONDS))
        logger.info(
            "SenseVoice-MLX 分段推理：duration=%.1fs → %d 段（%.0fs/段）",
            duration, chunk_count, CHUNK_SECONDS,
        )
        all_items: list[TranscriptItem] = []
        with tempfile.TemporaryDirectory(prefix="biri_asr_mlx_") as tmpdir:
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
                new_items = _items_from_result(result, time_offset=start)
                all_items.extend(new_items)
                pct = (idx + 1) / chunk_count
                logger.info(
                    "段 %d/%d 完成：本段 %d 句，累计 %d 句，耗时 %.2fs（进度 %.0f%%）",
                    idx + 1, chunk_count, len(new_items), len(all_items),
                    time.monotonic() - t0, pct * 100,
                )
                await _emit(on_progress, all_items, pct)
                await asyncio.sleep(0)

        logger.info("SenseVoice-MLX 分段推理完成：共 %d 句", len(all_items))
        return all_items
