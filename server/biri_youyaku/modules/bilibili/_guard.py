"""B 站风控热身共享能力：cookie 注入 / buvid / w_webid 反爬指纹、频控码判定。

从 space.py 提取，供 space.py、dynamic.py 等业务接口模块复用。这里只放「怎么让请求
通过风控」本身；具体接口失败后「清哪些缓存、重试几次」的编排仍由各业务模块自己写，
因为要清的缓存（各自的搜索/翻页结果缓存）是模块私有的。
"""

from __future__ import annotations

import json
import re
from urllib.parse import unquote

from biri_youyaku.config import settings
from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get

# 一个像样的桌面 Chrome UA：风控对非浏览器 UA 更敏感。
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# B 站接口频控 / 风控校验失败的常见错误码：-799 请求过于频繁、-352 风控校验失败、
# -509 请求过于频繁（部分接口用这个码）。
RATE_LIMIT_CODES = frozenset({-799, -352, -509})


def is_rate_limited_code(code: object) -> bool:
    return code in RATE_LIMIT_CODES


def auth_fingerprint() -> str:
    """仅用于区分缓存身份（登录 vs 匿名），不放真实值。"""
    return "auth" if settings.bili_sessdata else "anon"


@ttl_lru(maxsize=1, ttl_seconds=12 * 3600)
async def fetch_buvid() -> tuple[str, str]:
    """从 SPI 接口拿匿名 buvid3 / buvid4。风控要求带 buvid3 cookie。"""
    response = await bili_get(bili_client(), "https://api.bilibili.com/x/frontend/finger/spi")
    data = (response.json() or {}).get("data") or {}
    return str(data.get("b_3") or ""), str(data.get("b_4") or "")


async def prime_cookies() -> None:
    """把鉴权 cookie 写进共享 client 的 cookie jar，之后各接口请求都靠 jar 带 cookie。

    关键点：不再用显式 Cookie header——那样会丢掉访问空间页时被 Set-Cookie 的
    b_nut / buvid4 / _uuid 等反风控 cookie。走 jar 则「已配置的 SESSDATA + 页面热身
    下发的 cookie」一起发出，风控通过率高得多。匿名时补一次 SPI buvid3/4。
    """
    jar = bili_client().cookies
    if settings.bili_sessdata:
        jar.set("SESSDATA", settings.bili_sessdata, domain=".bilibili.com")
    if settings.bili_bili_jct:
        jar.set("bili_jct", settings.bili_bili_jct, domain=".bilibili.com")
    if settings.bili_buvid3:
        jar.set("buvid3", settings.bili_buvid3, domain=".bilibili.com")
    elif jar.get("buvid3") is None:
        try:
            b3, b4 = await fetch_buvid()
        except Exception:
            b3 = b4 = ""
        if b3:
            jar.set("buvid3", b3, domain=".bilibili.com")
        if b4:
            jar.set("buvid4", b4, domain=".bilibili.com")


@ttl_lru(maxsize=64, ttl_seconds=3600)
async def fetch_w_webid(mid: int, auth_key: str) -> str:
    """从 UP 空间页 HTML 的 __RENDER_DATA__ 里取 access_id（即 w_webid）。

    风控要求投稿列表 / 动态等接口带 w_webid，否则 -352。空间页里这段是 URL 编码的 JSON。
    cookie 走 jar（prime_cookies 已注入），这里不传显式 Cookie header。
    """
    headers = {"User-Agent": BROWSER_UA, "Referer": "https://www.bilibili.com/"}
    response = await bili_get(bili_client(), f"https://space.bilibili.com/{mid}", headers=headers)
    match = re.search(r'<script id="__RENDER_DATA__"[^>]*>(.*?)</script>', response.text, re.S)
    if not match:
        return ""
    try:
        data = json.loads(unquote(match.group(1).strip()))
    except ValueError:
        return ""
    return str(data.get("access_id") or "")
