"""Parakeet TDT v3 MLX 后端（NVIDIA Parakeet, MLX 移植）。

- 英语 / 25 种欧语 WER 6.34%，超 Whisper-Large-v3（9.9%）
- M4 Pro 上 CoreML/MLX 端口 ~24-110× RTF
- 中文支持弱，**不要**用来跑中文视频；中文走 sensevoice / sensevoice-mlx

依赖：`uv sync --extra asr-mlx`（安装 parakeet-mlx）。
"""

from __future__ import annotations

import asyncio
import logging
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
from biri_youyaku.modules.transcript import TranscriptItem

logger = logging.getLogger(__name__)

# Parakeet 长音频原生支持 chunk + overlap；用比 sensevoice 更大的窗口（2 分钟 / 重叠 15s）
_PARAKEET_CHUNK_SECONDS = 120.0
_PARAKEET_OVERLAP_SECONDS = 15.0


@lru_cache(maxsize=1)
def _load_model() -> Any:
    try:
        from parakeet_mlx import from_pretrained
    except ImportError as exc:
        raise RuntimeError(
            "parakeet-mlx 未安装。在 server 目录执行：uv sync --extra asr-mlx"
        ) from exc
    # 允许通过 SENSEVOICE_MODEL_DIR 复用「自定义模型路径」语义，没必要再多加一个配置项
    model_id = settings.sensevoice_model_dir or "mlx-community/parakeet-tdt-0.6b-v3"
    logger.info("Loading Parakeet MLX model: %s", model_id)
    return from_pretrained(model_id)


def _items_from_result(result: Any) -> list[TranscriptItem]:
    """parakeet-mlx 返回的 result 对象上 `.sentences` 是带时间戳的句子列表。"""
    items: list[TranscriptItem] = []
    sentences = getattr(result, "sentences", None)
    if sentences:
        for s in sentences:
            text = (getattr(s, "text", "") or "").strip()
            if not text:
                continue
            start = float(getattr(s, "start", 0) or 0)
            end = float(getattr(s, "end", start) or start)
            items.append(TranscriptItem(start=start, end=end, text=text))
        return items
    # 兜底：只有整段 text
    text = (getattr(result, "text", "") or "").strip()
    if text:
        items.append(TranscriptItem(start=0.0, end=0.0, text=text))
    return items


def _transcribe_sync(audio_path: Path) -> Any:
    model = _load_model()
    # chunk_duration / overlap_duration 是 parakeet-mlx 自带的长音频处理
    try:
        return model.transcribe(
            str(audio_path),
            chunk_duration=_PARAKEET_CHUNK_SECONDS,
            overlap_duration=_PARAKEET_OVERLAP_SECONDS,
        )
    except TypeError:
        # 老版本可能不接受这些参数
        return model.transcribe(str(audio_path))


class ParakeetMLXTranscriber:
    """与 SenseVoiceTranscriber 接口一致；不接受 language 参数（Parakeet 自动检测）。"""

    @staticmethod
    def warmup() -> None:
        _load_model()

    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> list[TranscriptItem]:
        # 注意：language 参数被 Parakeet 忽略；如果调用方期望强制中文，应该路由到
        # sensevoice-mlx 后端（见 modules/asr/__init__.py::get_transcriber 的 auto 路由）。
        t0 = time.monotonic()
        result = await asyncio.to_thread(_transcribe_sync, request.audio_path)
        items = _items_from_result(result)
        elapsed = time.monotonic() - t0
        logger.info("Parakeet-MLX 完成：%d 段，耗时 %.1fs", len(items), elapsed)

        # Parakeet 内部已经做了 chunk，所以无法逐段回报进度；完成后回一次 100%
        if on_progress is not None:
            preview = items[-1].text[-200:] if items else ""
            try:
                await on_progress(TranscribeProgress(percent=1.0, items_count=len(items), preview=preview))
            except Exception:
                logger.exception("transcribe progress callback failed")
        return items
