"""UP 主动态时间线抓取。

走 `x/polymer/web-dynamic/v1/feed/space`（需要 WBI 签名 + cookie/buvid/w_webid 风控
热身，套路与 space.py 一致，共享能力提取在 `_guard.py`）。用于蒸馏语料里的动态素材来源。
"""

from __future__ import annotations

import asyncio
import time

from biri_youyaku.modules._cache import ttl_lru
from biri_youyaku.modules._http import bili_client, bili_get
from biri_youyaku.modules.bilibili import _guard
from biri_youyaku.modules.bilibili import meta as bili_meta
from biri_youyaku.modules.bilibili.wbi import sign

FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

_SECONDS_PER_DAY = 86400


class DynamicRateLimited(RuntimeError):
    """B 站对动态接口频控（code -799 / -352 / -509）。"""


class DynamicFetchError(RuntimeError):
    pass


def _raise_for_code(payload: dict) -> dict:
    code = payload.get("code")
    if code == 0:
        return payload.get("data") or {}
    message = str(payload.get("message") or "").strip()
    if _guard.is_rate_limited_code(code):
        raise DynamicRateLimited(message or "请求过于频繁，请稍后再试")
    raise DynamicFetchError(message or f"B 站动态接口返回失败（code={code}）")


def _text(value: object) -> str:
    return str(value).strip() if value else ""


def _summary_text(desc: dict) -> str:
    """摘要节点常见形态是 {"text": "..."}，这里只取纯文本，缺失容错为空串。"""
    if not isinstance(desc, dict):
        return ""
    return _text(desc.get("text"))


def _parse_ts(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_by_type(dtype: str, modules: dict) -> dict:
    """按动态类型解析出 {type, text, bvid, title}；不含 id/ts，供顶层与转发内嵌的
    orig 动态共用。任何字段缺失都容错为空串，不抛 KeyError。
    """
    modules = modules or {}
    module_dynamic = modules.get("module_dynamic") or {}
    major = module_dynamic.get("major") or {}
    own_desc_text = _summary_text(module_dynamic.get("desc") or {})

    bvid = ""
    title = ""
    text = own_desc_text
    kind = "other"

    if dtype == "DYNAMIC_TYPE_AV":
        kind = "video"
        archive = major.get("archive") or {}
        bvid = _text(archive.get("bvid"))
        title = _text(archive.get("title"))
        archive_desc = _text(archive.get("desc"))
        text = "\n".join(part for part in (own_desc_text, archive_desc) if part)
    elif dtype in ("DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW"):
        kind = "text" if dtype == "DYNAMIC_TYPE_WORD" else "image"
        opus_summary = _summary_text((major.get("opus") or {}).get("summary") or {})
        text = opus_summary or own_desc_text
    elif dtype == "DYNAMIC_TYPE_ARTICLE":
        kind = "article"
        article = major.get("article")
        if article:
            title = _text(article.get("title"))
            text = _text(article.get("desc")) or own_desc_text
        else:
            opus = major.get("opus") or {}
            title = _text(opus.get("title"))
            text = _summary_text(opus.get("summary") or {}) or own_desc_text

    return {"type": kind, "text": text or "", "bvid": bvid, "title": title}


def parse_item(item: dict) -> dict:
    """把一条动态原始 item 解析成统一结构 {id, type, text, bvid, title, ts}。

    字段缺失一律容错为空串 / None，不抛 KeyError。
    """
    item = item or {}
    modules = item.get("modules") or {}
    module_author = modules.get("module_author") or {}
    dtype = str(item.get("type") or "")
    id_str = _text(item.get("id_str"))
    ts = _parse_ts(module_author.get("pub_ts"))

    if dtype == "DYNAMIC_TYPE_FORWARD":
        own_desc_text = _summary_text((modules.get("module_dynamic") or {}).get("desc") or {})
        orig = item.get("orig") or {}
        orig_type = str(orig.get("type") or "")
        orig_parsed = _extract_by_type(orig_type, orig.get("modules") or {})
        parsed = {
            "type": "forward",
            "text": f"{own_desc_text} // 转发：{orig_parsed['text']}",
            "bvid": "",
            "title": "",
        }
    else:
        parsed = _extract_by_type(dtype, modules)

    return {
        "id": id_str,
        "type": parsed["type"],
        "text": parsed["text"],
        "bvid": parsed["bvid"],
        "title": parsed["title"],
        "ts": ts,
    }


def _is_pinned(item: dict) -> bool:
    """置顶动态常年挂在第一页最前，pub_ts 可能非常旧，
    不能当作「已翻到旧内容」的停止信号。"""
    tag = ((item or {}).get("modules") or {}).get("module_tag") or {}
    return _text(tag.get("text")) == "置顶"


def _to_page_result(data: dict) -> dict:
    raw_items = data.get("items") or []
    return {
        "items": [parse_item(item) for item in raw_items],
        "has_more": bool(data.get("has_more")),
        "offset": _text(data.get("offset")),
    }


async def _request_feed_page(mid: int, offset: str) -> dict:
    """实际发起一次翻页请求（未缓存）。"""
    try:
        w_webid = await _guard.fetch_w_webid(mid, _guard.auth_fingerprint())
    except Exception:
        w_webid = ""
    params: dict[str, object] = {
        "host_mid": mid,
        "offset": offset,
        "features": "itemOpusStyle",
    }
    if w_webid:
        params["w_webid"] = w_webid
    signed = await sign(params, cookie_header=bili_meta._cookie_header())
    headers = {
        "User-Agent": _guard.BROWSER_UA,
        "Referer": f"https://space.bilibili.com/{mid}/dynamic",
    }
    response = await bili_get(bili_client(), FEED_URL, params=signed, headers=headers)
    return _raise_for_code(response.json())


@ttl_lru(maxsize=256, ttl_seconds=300)
async def _fetch_feed_page(mid: int, offset: str) -> dict:
    return await _request_feed_page(mid, offset)


async def fetch_dynamics_page(mid: int, offset: str = "") -> dict:
    """抓一页动态，返回 {items, has_more, offset}。ttl_lru 缓存 300s（key 含 mid+offset）。"""
    offset = offset or ""
    await _guard.prime_cookies()
    try:
        data = await _fetch_feed_page(mid, offset)
    except DynamicRateLimited:
        # 触发风控时清缓存重新热身再试一次，套路与 space.py 一致。
        _fetch_feed_page.cache_clear()
        _guard.fetch_w_webid.cache_clear()
        await _guard.prime_cookies()
        data = await _fetch_feed_page(mid, offset)
    return _to_page_result(data)


async def fetch_all_dynamics(
    mid: int,
    *,
    max_items: int = 1000,
    max_age_days: int = 730,
    page_delay_s: float = 1.5,
) -> list[dict]:
    """串行翻页抓全部动态（不走缓存，供蒸馏批量用）。

    三个停止条件（先触发者为准）：某条 pub_ts 早于 max_age_days；凑满 max_items；
    某页 has_more=False。页间 sleep(page_delay_s) 避免触发频控。
    """
    cutoff_ts = time.time() - max_age_days * _SECONDS_PER_DAY
    collected: list[dict] = []
    offset = ""
    is_first_page = True
    await _guard.prime_cookies()
    while True:
        if not is_first_page:
            await asyncio.sleep(page_delay_s)
        is_first_page = False

        try:
            data = await _request_feed_page(mid, offset)
        except DynamicRateLimited:
            await _guard.prime_cookies()
            data = await _request_feed_page(mid, offset)

        raw_items = data.get("items") or []
        stop = False
        for raw in raw_items:
            parsed = parse_item(raw)
            ts = parsed.get("ts")
            if ts is not None and ts < cutoff_ts:
                if _is_pinned(raw):
                    # 旧置顶：跳过这一条继续往下，不停止翻页。
                    continue
                stop = True
                break
            collected.append(parsed)
            if len(collected) >= max_items:
                stop = True
                break

        if stop or not bool(data.get("has_more")):
            break
        offset = _text(data.get("offset"))
        if not offset:
            break

    return collected
