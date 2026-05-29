import asyncio
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from biri_youyaku.config import settings

_BILI_TIMEOUT = 15.0
_BILI_RETRIES = 3


async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """GET with exponential backoff retry (3 attempts, 15 s timeout per request)."""
    last_exc: Exception | None = None
    for attempt in range(_BILI_RETRIES):
        try:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < _BILI_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # 0 s, 1 s, 2 s before each retry
    raise last_exc  # type: ignore[misc]


@dataclass(frozen=True)
class Chapter:
    start: float
    end: float | None
    title: str


@dataclass(frozen=True)
class VideoMeta:
    url: str
    bvid: str
    cid: int | None
    title: str
    author: str
    duration: float
    subtitle_url: str | None = None
    chapters: list[Chapter] | None = None

    @property
    def has_subtitle(self) -> bool:
        return self.subtitle_url is not None


def extract_bvid(url: str) -> str:
    match = re.search(r"(BV[a-zA-Z0-9]+)", url)
    if match is None:
        raise ValueError("未能从 URL 中识别 BV 号")
    return match.group(1)


_SHORT_HOSTS = ("b23.tv", "b.23.tv")


def _is_short_link(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in _SHORT_HOSTS)


async def resolve_short_url(url: str) -> str:
    """Follow b23.tv / b.23.tv redirects until we land on a bilibili.com URL.

    Falls back to the original URL on network failure so the caller still has a
    chance to surface a parsing error to the user.
    """
    if not _is_short_link(url):
        return url
    try:
        async with httpx.AsyncClient(
            timeout=_BILI_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Biri-Youyaku/0.1"},
        ) as client:
            response = await client.get(url)
            final_url = str(response.url)
            return final_url or url
    except (httpx.HTTPError, httpx.TransportError):
        return url


def extract_page_number(url: str) -> int | None:
    parsed = urlparse(url)
    value = parse_qs(parsed.query).get("p", [None])[0]
    if value is None:
        return None
    try:
        page = int(value)
    except ValueError:
        return None
    return page if page > 0 else None


def _parse_timestamp(value: str) -> float | None:
    parts = value.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        minutes, seconds = numbers
        return float(minutes * 60 + seconds)
    hours, minutes, seconds = numbers
    return float(hours * 3600 + minutes * 60 + seconds)


def chapters_from_description(description: str, duration: float) -> list[Chapter]:
    matches: list[tuple[float, str]] = []
    for raw_line in description.splitlines():
        line = raw_line.strip()
        match = re.match(r"^(?:[-*·•\s]*)?((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(.+)$", line)
        if match is None:
            match = re.match(r"^(.+?)\s+((?:\d{1,2}:)?\d{1,2}:\d{2})$", line)
        if match is None:
            continue
        if ":" in match.group(1):
            timestamp_text = match.group(1)
            title = match.group(2).strip(" -—:：")
        else:
            timestamp_text = match.group(2)
            title = match.group(1).strip(" -—:：")
        start = _parse_timestamp(timestamp_text)
        if start is None or start < 0 or (duration > 0 and start >= duration):
            continue
        if title:
            matches.append((start, title))

    matches = sorted(set(matches))
    chapters = []
    for index, (start, title) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else None
        chapters.append(Chapter(start=start, end=next_start or (duration or None), title=title))
    return chapters


def chapters_from_pages(pages: list[dict]) -> list[Chapter]:
    chapters = []
    offset = 0.0
    for index, page in enumerate(pages):
        duration = float(page.get("duration") or 0)
        title = str(page.get("part") or f"P{index + 1}").strip()
        chapters.append(
            Chapter(
                start=offset,
                end=offset + duration if duration > 0 else None,
                title=title,
            )
        )
        offset += duration
    return chapters


def _cookie_header() -> str:
    parts = []
    if settings.bili_sessdata:
        parts.append(f"SESSDATA={settings.bili_sessdata}")
    if settings.bili_buvid3:
        parts.append(f"buvid3={settings.bili_buvid3}")
    if settings.bili_bili_jct:
        parts.append(f"bili_jct={settings.bili_bili_jct}")
    return "; ".join(parts)


async def fetch(url: str) -> VideoMeta:
    # Short-link forms (b23.tv / b.23.tv) need to be expanded to a canonical
    # bilibili.com URL before we can pull a BV id out of the path.
    canonical_url = await resolve_short_url(url) if _is_short_link(url) else url
    bvid = extract_bvid(canonical_url)
    page_number = extract_page_number(canonical_url)
    headers = {
        "User-Agent": "Mozilla/5.0 Biri-Youyaku/0.1",
        "Referer": "https://www.bilibili.com",
    }
    cookie = _cookie_header()
    if cookie:
        headers["Cookie"] = cookie

    async with httpx.AsyncClient(timeout=_BILI_TIMEOUT, headers=headers) as client:
        view_response = await _get_with_retry(
            client,
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )
        payload = view_response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message") or "B 站元信息接口返回失败")
        data = payload["data"]
        pages = data.get("pages") or []
        selected_page = None
        if pages:
            selected_page = pages[min((page_number or 1) - 1, len(pages) - 1)]
        cid = selected_page.get("cid") if selected_page else data.get("cid")
        subtitle_url = None
        chapters = []
        for row in data.get("view_points") or []:
            title = str(row.get("content") or "").strip()
            if not title:
                continue
            chapters.append(
                Chapter(
                    start=float(row.get("from") or 0),
                    end=float(row.get("to")) if row.get("to") is not None else None,
                    title=title,
                )
            )
        duration_value = selected_page.get("duration") if selected_page else data.get("duration")
        duration = float(duration_value or 0)
        if not chapters:
            chapters = chapters_from_description(str(data.get("desc") or ""), duration)
        if not chapters and pages and page_number is None:
            chapters = chapters_from_pages(pages)

        if cid is not None:
            try:
                player_response = await _get_with_retry(
                    client,
                    "https://api.bilibili.com/x/player/wbi/v2",
                    params={"bvid": bvid, "cid": cid},
                )
                player_data = player_response.json().get("data") or {}
                subtitles = ((player_data.get("subtitle") or {}).get("subtitles") or [])
                if subtitles:
                    subtitle_url = subtitles[0].get("subtitle_url")
                    if subtitle_url and subtitle_url.startswith("//"):
                        subtitle_url = f"https:{subtitle_url}"
            except Exception:
                # Subtitle fetch failure should not block meta fetch; subtitle_url stays None
                pass

    base_title = data.get("title") or bvid
    if selected_page is not None and len(pages) > 1 and page_number is not None:
        part_title = str(selected_page.get("part") or "").strip()
        if part_title and part_title != base_title:
            base_title = f"{base_title} - {part_title}"
    return VideoMeta(
        url=url,
        bvid=bvid,
        cid=cid,
        title=base_title,
        author=(data.get("owner") or {}).get("name") or "",
        duration=duration,
        subtitle_url=subtitle_url,
        chapters=chapters,
    )
