from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


@dataclass(frozen=True)
class TranscribeRequest:
    audio_path: Path
    language: str = "auto"


@dataclass(frozen=True)
class TranscribeProgress:
    """每段完成后回报：百分比、累计段数、累计文本（截断到最近 200 字）"""
    percent: float
    items_count: int
    preview: str


ProgressCallback = Callable[[TranscribeProgress], Awaitable[None]]


class Transcriber(Protocol):
    async def transcribe(
        self,
        request: TranscribeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> list[TranscriptItem]:
        ...
