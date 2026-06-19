"""ASR 后端工厂。

`get_transcriber(name)` 是 pipeline / warmup / 测试公共的入口；
按 `name` 路由到具体后端。新加后端只需在这里注册一次，pipeline 不用改 if 链。

支持的 name：
    sensevoice       —— funasr CPU 版（跨平台，包括 Linux Docker）
    sensevoice-mlx   —— Apple Silicon GPU/ANE 加速版（mlx-audio），M 系列 Mac 推荐
    parakeet-mlx     —— NVIDIA Parakeet TDT v3，英语 / 欧语 SOTA，仅 Apple Silicon
    faster-whisper   —— CTranslate2 优化版 whisper
    auto             —— 看 ASR_LANGUAGE_DEFAULT / 任务语言路由：CJK → sensevoice-mlx，其余 → parakeet-mlx
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from biri_youyaku.modules.asr.base import Transcriber

__all__ = [
    "SenseVoiceTranscriber",
    "SenseVoiceMLXTranscriber",
    "FasterWhisperTranscriber",
    "ParakeetMLXTranscriber",
    "AutoRouterTranscriber",
    "get_transcriber",
]


# CJK / 类东亚语 → 走 SenseVoice 系；其它（en/de/fr/es/it/pt/nl/ru/pl/...）走 Parakeet
_CJK_LANGUAGES = frozenset({"zh", "zh-cn", "zh-tw", "ja", "ko", "yue", "cn"})


@lru_cache(maxsize=8)
def get_transcriber(name: str) -> Transcriber:
    """根据 ASR_MODEL 名拿到 transcriber 单例。"""
    key = (name or "").strip().lower()

    if key in ("sensevoice-mlx", "sensevoice_mlx", "mlx-sensevoice"):
        from biri_youyaku.modules.asr.sensevoice_mlx import SenseVoiceMLXTranscriber

        return SenseVoiceMLXTranscriber()

    if key in ("parakeet-mlx", "parakeet_mlx", "parakeet"):
        from biri_youyaku.modules.asr.parakeet_mlx import ParakeetMLXTranscriber

        return ParakeetMLXTranscriber()

    if key == "faster-whisper":
        from biri_youyaku.modules.asr.whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber()

    if key == "auto":
        return AutoRouterTranscriber()

    # 默认 SenseVoice (funasr CPU)
    from biri_youyaku.modules.asr.sensevoice import SenseVoiceTranscriber

    return SenseVoiceTranscriber()


class AutoRouterTranscriber:
    """根据任务的 language 字段把请求转发到合适的后端。

    - CJK / auto / 空 → sensevoice-mlx（Apple Silicon）或 sensevoice（其它平台）
    - 其它语言 → parakeet-mlx；若 parakeet 不可用，降级到 sensevoice-mlx

    每次 transcribe 才决定路由；首次落点会触发对应后端的 lazy 模型加载。
    """

    @staticmethod
    def warmup() -> None:
        # auto 不预热具体后端：可能多语场景下两个都加载是浪费。等首次请求按需 lazy 加载。
        pass

    def _pick(self, language: str | None) -> Transcriber:
        lang = (language or "").strip().lower()
        if not lang or lang == "auto" or lang in _CJK_LANGUAGES:
            return _try_get(["sensevoice-mlx", "sensevoice"])
        return _try_get(["parakeet-mlx", "sensevoice-mlx", "sensevoice"])

    async def transcribe(self, request, *, on_progress=None):
        return await self._pick(request.language).transcribe(request, on_progress=on_progress)


def _try_get(candidates: list[str]) -> Transcriber:
    """按顺序试着加载后端，第一个 import 成功的就用。失败则把最后一个错误抛出去。"""
    last_exc: Exception | None = None
    for name in candidates:
        try:
            return get_transcriber(name)
        except Exception as exc:  # ImportError / RuntimeError（依赖缺失）
            last_exc = exc
            continue
    assert last_exc is not None
    raise last_exc


# 兼容旧 import 路径，外部 import SenseVoiceTranscriber / FasterWhisperTranscriber / 等
def __getattr__(name: str) -> Any:
    if name == "SenseVoiceTranscriber":
        from biri_youyaku.modules.asr.sensevoice import SenseVoiceTranscriber

        return SenseVoiceTranscriber
    if name == "SenseVoiceMLXTranscriber":
        from biri_youyaku.modules.asr.sensevoice_mlx import SenseVoiceMLXTranscriber

        return SenseVoiceMLXTranscriber
    if name == "FasterWhisperTranscriber":
        from biri_youyaku.modules.asr.whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber
    if name == "ParakeetMLXTranscriber":
        from biri_youyaku.modules.asr.parakeet_mlx import ParakeetMLXTranscriber

        return ParakeetMLXTranscriber
    raise AttributeError(name)
