"""B 站 WBI 签名。

`x/space/wbi/arc/search`（UP 投稿列表）等接口要求 WBI 签名：从 `x/web-interface/nav`
取一对每日轮换的 `img_key` / `sub_key`，按固定置换表推出 `mixin_key`，再对请求参数
（含时间戳 `wts`）排序后 md5 得到 `w_rid`。少了它接口会返回 -403 / -799。
"""

from __future__ import annotations

import time
import urllib.parse
from functools import reduce
from hashlib import md5

from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get

# B 站固定的混淆置换表（公开常量，各开源实现一致）。
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return reduce(lambda acc, i: acc + raw[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def _key_from_url(url: str) -> str:
    """从 wbi_img 的 url 取文件名主干：.../7cd084941338484aae1ad9425b84077c.png → 该 hex。"""
    return url.rsplit("/", 1)[-1].split(".", 1)[0]


@ttl_lru(maxsize=4, ttl_seconds=12 * 3600)
async def _fetch_wbi_keys(cookie_header: str) -> tuple[str, str]:
    """拉 nav 接口取 (img_key, sub_key)。每日轮换，缓存 12h。

    nav 未登录也会返回 wbi_img（外层 code 可能是 -101），所以只读 data.wbi_img，不校验 code。
    cookie 进缓存 key：配上 SESSDATA 后能立刻拿到登录态的 key。
    """
    headers = {"Cookie": cookie_header} if cookie_header else None
    response = await bili_get(
        bili_client(), "https://api.bilibili.com/x/web-interface/nav", headers=headers
    )
    wbi_img = ((response.json() or {}).get("data") or {}).get("wbi_img") or {}
    img_key = _key_from_url(str(wbi_img.get("img_url") or ""))
    sub_key = _key_from_url(str(wbi_img.get("sub_url") or ""))
    if not img_key or not sub_key:
        raise RuntimeError("无法获取 WBI 签名密钥（nav 接口未返回 wbi_img）")
    return img_key, sub_key


def _sanitize(value: object) -> str:
    # 签名前需从参数值里去掉 !'()* 这些字符（B 站算法约定）。
    return "".join(ch for ch in str(value) if ch not in "!'()*")


async def sign(params: dict[str, object], *, cookie_header: str = "") -> dict[str, str]:
    """给请求参数补上 wts + w_rid，返回**可直接用于请求**的参数字典。

    返回值里的普通参数已做与签名一致的字符过滤，确保服务端复算 w_rid 时能对上。
    """
    img_key, sub_key = await _fetch_wbi_keys(cookie_header)
    mixin_key = _mixin_key(img_key, sub_key)

    signed: dict[str, str] = {key: _sanitize(value) for key, value in params.items()}
    signed["wts"] = str(int(time.time()))
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = md5((query + mixin_key).encode("utf-8")).hexdigest()
    return signed
