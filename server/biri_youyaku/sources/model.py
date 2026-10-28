from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    start: float
    end: float | None
    title: str


@dataclass(frozen=True)
class MediaMeta:
    url: str
    bvid: str
    cid: int | None
    title: str
    author: str
    duration: float
    subtitle_url: str | None = None
    chapters: list[Chapter] | None = None
    mid: int | None = None
    provider: str = "bilibili"
    source_id: str | None = None
    source_part: str | None = None
    subtitle_language: str | None = None
    subtitle_source: str | None = None

    @property
    def has_subtitle(self) -> bool:
        return self.subtitle_url is not None
