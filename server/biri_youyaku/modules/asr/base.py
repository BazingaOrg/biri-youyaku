from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


@dataclass(frozen=True)
class TranscribeRequest:
    audio_path: Path
    language: str = "auto"


class Transcriber(Protocol):
    async def transcribe(self, request: TranscribeRequest) -> list[TranscriptItem]:
        ...
