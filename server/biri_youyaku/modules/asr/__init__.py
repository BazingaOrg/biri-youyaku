"""ASR 后端工厂。

`get_transcriber(name)` 是 pipeline / warmup / 测试公共的入口；
按 `name` 路由到具体后端（"sensevoice" / "faster-whisper"）。

新加后端只需在这里注册一次，pipeline 不用改 if 链。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from biri_youyaku.modules.asr.base import Transcriber

__all__ = ["SenseVoiceTranscriber", "FasterWhisperTranscriber", "get_transcriber"]


# 工厂内部按 name 缓存实例，模块权重在 transcriber 自身（@lru_cache _load_model）。
@lru_cache(maxsize=4)
def get_transcriber(name: str) -> Transcriber:
    """根据 ASR_MODEL 名拿到 transcriber 单例。

    未知名字默认走 SenseVoice，与 pipeline 历史行为保持一致。
    """
    key = (name or "").strip().lower()
    if key == "faster-whisper":
        from biri_youyaku.modules.asr.whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber()
    # 默认 SenseVoice
    from biri_youyaku.modules.asr.sensevoice import SenseVoiceTranscriber

    return SenseVoiceTranscriber()


# 兼容旧 import 路径，外部 import SenseVoiceTranscriber / FasterWhisperTranscriber
def __getattr__(name: str) -> Any:
    if name == "SenseVoiceTranscriber":
        from biri_youyaku.modules.asr.sensevoice import SenseVoiceTranscriber

        return SenseVoiceTranscriber
    if name == "FasterWhisperTranscriber":
        from biri_youyaku.modules.asr.whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber
    raise AttributeError(name)
