from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse


_BILIBILI_HOSTS = frozenset({"bilibili.com", "www.bilibili.com", "m.bilibili.com"})
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
_YOUTUBE_SHORT_HOST = "youtu.be"
_B23_HOSTS = frozenset({"b23.tv", "b.23.tv"})
_BVID = re.compile(r"^BV[a-zA-Z0-9]+$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class SourceIdentity:
    provider: str
    source_id: str
    source_part: str | None
    canonical_url: str


def _parsed_http_url(value: str):
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is not None and port not in {80, 443}:
        return None
    return parsed


def _page_number(query: dict[str, list[str]]) -> str:
    value = query.get("p", ["1"])[0]
    try:
        page = int(value)
    except (TypeError, ValueError):
        return "1"
    return str(page) if page > 0 else "1"


def identify_url(value: str) -> SourceIdentity | None:
    parsed = _parsed_http_url(value)
    if parsed is None:
        return None
    host = (parsed.hostname or "").lower()
    if host in _B23_HOSTS:
        return None
    if host in _BILIBILI_HOSTS:
        match = re.fullmatch(r"/video/(BV[a-zA-Z0-9]+)(?:/)?", parsed.path)
        if match is None or not _BVID.fullmatch(match.group(1)):
            return None
        source_id = match.group(1)
        part = _page_number(parse_qs(parsed.query))
        canonical_url = f"https://www.bilibili.com/video/{source_id}?{urlencode({'p': part})}"
        return SourceIdentity("bilibili", source_id, part, canonical_url)
    if host == _YOUTUBE_SHORT_HOST:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[0] if len(parts) == 1 else ""
    elif host in _YOUTUBE_HOSTS:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "embed"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        return None
    if not _YOUTUBE_ID.fullmatch(video_id):
        return None
    return SourceIdentity("youtube", video_id, "", f"https://www.youtube.com/watch?v={video_id}")
