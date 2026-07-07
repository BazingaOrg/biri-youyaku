"""UP 主投稿列表抓取。

走 `x/space/wbi/arc/search`（需要 WBI 签名 + 最好带 SESSDATA）。B 站对这个接口有频控，
高频会返回 -799；这里按 (mid, page, keyword) 缓存一小段时间，并把频控映射成友好错误。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get
from biri_youyaku.modules.bilibili import _guard
from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.modules.bilibili.wbi import sign

PAGE_SIZE = 30

# B 站投稿列表支持的排序：pubdate=最新发布、click=最多播放、stow=最多收藏。
_VALID_ORDERS = {"pubdate", "click", "stow"}

# 风控热身能力（cookie 注入 / buvid / w_webid）提取到 _guard.py，这里保留同名别名，
# 使公开行为、既有测试（monkeypatch 这些名字）完全不变。
_BROWSER_UA = _guard.BROWSER_UA
_fetch_buvid = _guard.fetch_buvid
_prime_cookies = _guard.prime_cookies
_fetch_w_webid = _guard.fetch_w_webid
_auth_fingerprint = _guard.auth_fingerprint

# WebGL 指纹相关参数：缺了它们投稿列表接口会返回 -352「风控校验失败」。
# 这些是各开源实现通用的静态占位值，跟着请求一起被 WBI 签名。
_DM_PARAMS: dict[str, object] = {
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": (
        "QU5HTEUgKEludGVsLCBNZXNhIEludGVsKFIpIFVIRCBHcmFwaGljcyAoQ01MIEdUMiks"
        "IE9wZW5HTCA0LjYpR29vZ2xlIEluYy4gKEludGVsKQ"
    ),
    "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
}


class SpaceRateLimited(RuntimeError):
    """B 站对投稿列表接口频控（code -799 / -352 等）。"""


class SpaceFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpVideo:
    bvid: str
    title: str
    cover: str
    pubdate: int  # unix 秒
    duration: float  # 秒
    play: int = 0  # 播放量；蒸馏语料 frontmatter 要用，原列表接口不需要就留默认值


@dataclass(frozen=True)
class UpVideoPage:
    mid: int
    author: str
    total: int
    page: int
    page_size: int
    videos: list[UpVideo]

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


def _parse_length(value: str) -> float:
    """vlist.length 是 "MM:SS" 或 "HH:MM:SS"，转成秒。"""
    parts = value.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0.0
    if len(nums) == 2:
        return float(nums[0] * 60 + nums[1])
    if len(nums) == 3:
        return float(nums[0] * 3600 + nums[1] * 60 + nums[2])
    return 0.0


def _parse_play(value: object) -> int:
    """vlist.play 偶尔是 "--"（转码中/播放数隐藏），容错为 0，别让整页列表炸掉。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clean_title(raw: str) -> str:
    """搜索结果标题里命中关键词会被包成 <em class="keyword">…</em>，去掉所有标签并反转义实体。"""
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def _https(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


async def resolve_mid(raw: str) -> int:
    """把用户输入解析成 UP 的 mid。

    支持：纯数字 UID、space.bilibili.com/<uid>、b23 短链、或某个视频 URL/BV（取作者 mid）。
    """
    text = (raw or "").strip()
    if not text:
        raise SpaceFetchError("请输入 UP 主页链接或 UID")
    if text.isdigit():
        return int(text)

    url = await bili_meta.resolve_short_url(text) if "b23.tv" in text else text
    parsed = urlparse(url if "//" in url else f"//{url}")
    if "space.bilibili.com" in (parsed.netloc or ""):
        match = re.search(r"/(\d+)", parsed.path)
        if match:
            return int(match.group(1))
    # 视频链接 / BV 号 → 取作者 mid
    if re.search(r"BV[a-zA-Z0-9]+", url):
        info = await bili_meta.fetch(url)
        if info.mid is not None:
            return info.mid
    raise SpaceFetchError("无法从输入中识别 UP 主：请粘贴主页链接或 UID")


def _raise_for_code(payload: dict) -> dict:
    code = payload.get("code")
    if code == 0:
        return payload.get("data") or {}
    message = str(payload.get("message") or "").strip()
    if _guard.is_rate_limited_code(code):
        raise SpaceRateLimited(message or "请求过于频繁，请稍后再试")
    if code == -404:
        raise SpaceFetchError("该 UP 主不存在或已注销")
    raise SpaceFetchError(message or f"B 站投稿列表接口返回失败（code={code}）")


@ttl_lru(maxsize=128, ttl_seconds=300)
async def _fetch_space_search(mid: int, page: int, keyword: str, order: str, auth_key: str) -> dict:
    try:
        w_webid = await _fetch_w_webid(mid, auth_key)
    except Exception:
        w_webid = ""
    params: dict[str, object] = {
        "mid": mid,
        "ps": PAGE_SIZE,
        "pn": page,
        "order": order,
        "platform": "web",
        "web_location": "1550101",
        **_DM_PARAMS,
    }
    if w_webid:
        params["w_webid"] = w_webid
    if keyword:
        params["keyword"] = keyword
    # WBI 的 nav 取 key 仍用已配置 cookie（登录态拿到的 key 更稳）；请求本身走 jar。
    signed = await sign(params, cookie_header=bili_meta._cookie_header())
    headers = {
        "User-Agent": _BROWSER_UA,
        "Referer": f"https://space.bilibili.com/{mid}/video",
    }
    response = await bili_get(
        bili_client(),
        "https://api.bilibili.com/x/space/wbi/arc/search",
        params=signed,
        headers=headers,
    )
    return _raise_for_code(response.json())


async def fetch_up_videos(
    mid: int, *, page: int = 1, keyword: str = "", order: str = "pubdate"
) -> UpVideoPage:
    order = order if order in _VALID_ORDERS else "pubdate"
    page = max(1, page)
    keyword = keyword.strip()
    await _prime_cookies()
    auth = _auth_fingerprint()
    try:
        data = await _fetch_space_search(mid, page, keyword, order, auth)
    except SpaceRateLimited:
        # 触发风控时清缓存重新热身（再访问一次空间页拿新的反风控 cookie）后再试一次：
        # 冷请求经常能过，很多 -352 是上一次状态被标记导致的。
        _fetch_space_search.cache_clear()
        _fetch_w_webid.cache_clear()
        await _prime_cookies()
        data = await _fetch_space_search(mid, page, keyword, order, auth)

    vlist = ((data.get("list") or {}).get("vlist")) or []
    page_info = data.get("page") or {}
    videos = [
        UpVideo(
            bvid=str(item.get("bvid") or ""),
            title=_clean_title(str(item.get("title") or "")),
            cover=_https(str(item.get("pic") or "")),
            pubdate=int(item.get("created") or 0),
            duration=_parse_length(str(item.get("length") or "")),
            play=_parse_play(item.get("play")),
        )
        for item in vlist
        if item.get("bvid")
    ]
    author = next((str(item.get("author")).strip() for item in vlist if item.get("author")), "")
    return UpVideoPage(
        mid=mid,
        author=author,
        total=int(page_info.get("count") or 0),
        page=int(page_info.get("pn") or page),
        page_size=int(page_info.get("ps") or PAGE_SIZE),
        videos=videos,
    )
