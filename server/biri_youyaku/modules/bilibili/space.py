"""UP 主投稿列表抓取。

走 `x/space/wbi/arc/search`（需要 WBI 签名 + 最好带 SESSDATA）。B 站对这个接口有频控，
高频会返回 -799；这里按 (mid, page, keyword) 缓存一小段时间，并把频控映射成友好错误。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get
from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.modules.bilibili.wbi import sign

PAGE_SIZE = 30

# 一个像样的桌面 Chrome UA：风控对非浏览器 UA 更敏感。
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

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
    if code in (-799, -352, -509):
        raise SpaceRateLimited(message or "请求过于频繁，请稍后再试")
    if code == -404:
        raise SpaceFetchError("该 UP 主不存在或已注销")
    raise SpaceFetchError(message or f"B 站投稿列表接口返回失败（code={code}）")


@ttl_lru(maxsize=1, ttl_seconds=12 * 3600)
async def _fetch_buvid() -> tuple[str, str]:
    """从 SPI 接口拿匿名 buvid3 / buvid4。风控要求带 buvid3 cookie。"""
    response = await bili_get(bili_client(), "https://api.bilibili.com/x/frontend/finger/spi")
    data = (response.json() or {}).get("data") or {}
    return str(data.get("b_3") or ""), str(data.get("b_4") or "")


async def _effective_cookie() -> str:
    """已配置的 cookie（含 SESSDATA）+ 匿名 buvid。已自带 buvid3 就不再补。"""
    configured = bili_meta._cookie_header()
    if "buvid3=" in configured:
        return configured
    try:
        b3, b4 = await _fetch_buvid()
    except Exception:
        return configured
    parts = [configured] if configured else []
    if b3:
        parts.append(f"buvid3={b3}")
    if b4:
        parts.append(f"buvid4={b4}")
    return "; ".join(p for p in parts if p)


@ttl_lru(maxsize=64, ttl_seconds=3600)
async def _fetch_w_webid(mid: int, cookie_header: str) -> str:
    """从 UP 空间页 HTML 的 __RENDER_DATA__ 里取 access_id（即 w_webid）。

    风控要求投稿列表带 w_webid，否则 -352。空间页里这段是 URL 编码的 JSON。
    """
    headers = {"User-Agent": _BROWSER_UA, "Referer": "https://www.bilibili.com/"}
    if cookie_header:
        headers["Cookie"] = cookie_header
    response = await bili_get(bili_client(), f"https://space.bilibili.com/{mid}", headers=headers)
    match = re.search(
        r'<script id="__RENDER_DATA__"[^>]*>(.*?)</script>', response.text, re.S
    )
    if not match:
        return ""
    try:
        data = json.loads(unquote(match.group(1).strip()))
    except ValueError:
        return ""
    return str(data.get("access_id") or "")


@ttl_lru(maxsize=128, ttl_seconds=300)
async def _fetch_space_search(mid: int, page: int, keyword: str, cookie_header: str) -> dict:
    try:
        w_webid = await _fetch_w_webid(mid, cookie_header)
    except Exception:
        w_webid = ""
    params: dict[str, object] = {
        "mid": mid,
        "ps": PAGE_SIZE,
        "pn": page,
        "order": "pubdate",
        "platform": "web",
        "web_location": "1550101",
        **_DM_PARAMS,
    }
    if w_webid:
        params["w_webid"] = w_webid
    if keyword:
        params["keyword"] = keyword
    signed = await sign(params, cookie_header=cookie_header)
    headers = {
        "User-Agent": _BROWSER_UA,
        "Referer": f"https://space.bilibili.com/{mid}/video",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    response = await bili_get(
        bili_client(),
        "https://api.bilibili.com/x/space/wbi/arc/search",
        params=signed,
        headers=headers,
    )
    return _raise_for_code(response.json())


async def fetch_up_videos(mid: int, *, page: int = 1, keyword: str = "") -> UpVideoPage:
    cookie_header = await _effective_cookie()
    data = await _fetch_space_search(mid, max(1, page), keyword.strip(), cookie_header)

    vlist = ((data.get("list") or {}).get("vlist")) or []
    page_info = data.get("page") or {}
    videos = [
        UpVideo(
            bvid=str(item.get("bvid") or ""),
            title=str(item.get("title") or "").strip(),
            cover=_https(str(item.get("pic") or "")),
            pubdate=int(item.get("created") or 0),
            duration=_parse_length(str(item.get("length") or "")),
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
