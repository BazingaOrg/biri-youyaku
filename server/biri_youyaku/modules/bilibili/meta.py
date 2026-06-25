import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from biri_youyaku.config import settings
from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get


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
    mid: int | None = None

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


@ttl_lru(maxsize=1024, ttl_seconds=24 * 3600)
async def _resolve_short_url_cached(url: str) -> str:
    """实际的短链解析，被 LRU 包一层 TTL=24h。"""
    try:
        response = await bili_client().get(url)
        return str(response.url) or url
    except (httpx.HTTPError, httpx.TransportError):
        return url


async def resolve_short_url(url: str) -> str:
    """b23.tv / b.23.tv → 长 URL。非短链直接原样返回。

    解析结果走 24h LRU；同一短链不会反复打 302。
    """
    if not _is_short_link(url):
        return url
    return await _resolve_short_url_cached(url)


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


# 记录上一次 fetch 看到的 cookie；变化时主动清缓存，避免旧 cookie 的 entry 占
# 256 slot 永不淘汰（cookie 在 settings 里换是少见操作，但 lifespan/dev reload
# 改 .env 后我们希望立刻看到新数据）。
_last_cookie_seen: str | None = None


def _maybe_invalidate_on_cookie_change(cookie: str) -> None:
    global _last_cookie_seen
    if _last_cookie_seen is None:
        _last_cookie_seen = cookie
        return
    if cookie != _last_cookie_seen:
        # cookie 变化 → 之前所有按 cookie 缓存的元信息可能已过期/可能从「无权」变「有权」
        _fetch_view_cached.cache_clear()  # type: ignore[attr-defined]
        _fetch_player_cached.cache_clear()  # type: ignore[attr-defined]
        _last_cookie_seen = cookie


def _auth_headers() -> dict[str, str]:
    """每次构建本次请求的额外 header（带 Cookie）。

    Cookie 可能在运行期被改（settings 是单例，但 SESSDATA 等可用环境变量重启刷新），
    所以不在 client 初始化时固化进去。
    """
    cookie = _cookie_header()
    return {"Cookie": cookie} if cookie else {}


@ttl_lru(maxsize=256, ttl_seconds=3600)
async def _fetch_view_cached(bvid: str, cookie_header: str) -> dict:
    """`/x/web-interface/view` 结果按 (bvid, cookie) 缓存 1h。

    Cookie 进 key 是为了在「先无 Cookie 失败 → 用户配上 Cookie 后」能立刻拿到新结果。
    """
    headers = {"Cookie": cookie_header} if cookie_header else None
    response = await bili_get(bili_client(), "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}, headers=headers)
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("message") or "B 站元信息接口返回失败")
    return payload["data"]


@ttl_lru(maxsize=256, ttl_seconds=3600)
async def _fetch_player_cached(bvid: str, cid: int, cookie_header: str) -> dict:
    headers = {"Cookie": cookie_header} if cookie_header else None
    response = await bili_get(
        bili_client(),
        "https://api.bilibili.com/x/player/wbi/v2",
        params={"bvid": bvid, "cid": cid},
        headers=headers,
    )
    return response.json().get("data") or {}


async def fetch(url: str) -> VideoMeta:
    # 短链 → 长 URL（短链解析走 24h LRU）
    canonical_url = await resolve_short_url(url) if _is_short_link(url) else url
    bvid = extract_bvid(canonical_url)
    page_number = extract_page_number(canonical_url)

    cookie = _cookie_header()
    _maybe_invalidate_on_cookie_change(cookie)
    data = await _fetch_view_cached(bvid, cookie)

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
            player_data = await _fetch_player_cached(bvid, int(cid), cookie)
            subtitles = ((player_data.get("subtitle") or {}).get("subtitles") or [])
            if subtitles:
                subtitle_url = subtitles[0].get("subtitle_url")
                if subtitle_url and subtitle_url.startswith("//"):
                    subtitle_url = f"https:{subtitle_url}"
        except Exception:
            # 字幕拉取失败不阻断 meta 返回
            pass

    base_title = data.get("title") or bvid
    if selected_page is not None and len(pages) > 1 and page_number is not None:
        part_title = str(selected_page.get("part") or "").strip()
        if part_title and part_title != base_title:
            base_title = f"{base_title} - {part_title}"
    owner = data.get("owner") or {}
    owner_mid = owner.get("mid")
    return VideoMeta(
        url=url,
        bvid=bvid,
        cid=cid,
        title=base_title,
        author=owner.get("name") or "",
        duration=duration,
        subtitle_url=subtitle_url,
        chapters=chapters,
        mid=int(owner_mid) if owner_mid is not None else None,
    )
