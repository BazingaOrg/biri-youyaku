import asyncio
from dataclasses import replace
from urllib.parse import urljoin, urlparse

import httpx

from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.sources import youtube
from biri_youyaku.sources.identity import SourceIdentity, identify_url
from biri_youyaku.sources.model import MediaMeta


async def resolve_url(url: str) -> SourceIdentity:
    identity = identify_url(url)
    if identity is not None:
        return identity
    async with httpx.AsyncClient(follow_redirects=False, timeout=10, trust_env=False) as client:
        for _ in range(5):
            parsed = urlparse(url)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"b23.tv", "b.23.tv"}
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 80, 443}
            ):
                raise ValueError("仅支持 B 站和 YouTube 的单个视频链接")
            async with client.stream("GET", url) as response:
                if response.status_code not in {301, 302, 303, 307, 308}:
                    raise ValueError("无法解析 B 站短链接，请使用视频页面链接")
                location = response.headers.get("location")
                if not location:
                    raise ValueError("视频短链接没有有效目标")
                url = urljoin(url, location)
            identity = identify_url(url)
            if identity is not None and identity.provider == "bilibili":
                return identity
    raise ValueError("视频短链接跳转过多")


async def fetch_meta(url: str) -> MediaMeta:
    identity = await resolve_url(url)
    if identity.provider == "youtube":
        return await youtube.fetch(identity.canonical_url)
    result = await asyncio.wait_for(bili_meta.fetch(identity.canonical_url), timeout=30)
    return replace(
        result,
        provider="bilibili",
        source_id=result.bvid,
        source_part=str(result.cid) if result.cid is not None else "",
        subtitle_source="platform",
    )
