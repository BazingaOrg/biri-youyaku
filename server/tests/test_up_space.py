import hashlib

import pytest

from biri_youyaku.modules.bilibili import space, wbi


async def _noop_prime() -> None:
    """替换 space._prime_cookies：测试里不碰 cookie jar / 网络。"""
    return None


def test_mixin_key_is_32_chars_and_deterministic():
    key = wbi._mixin_key("7cd084941338484aae1ad9425b84077c", "4932caff0ff746eab6f01bf08b70ac45")
    assert len(key) == 32
    # 纯查表置换，必须可复现
    assert key == wbi._mixin_key("7cd084941338484aae1ad9425b84077c", "4932caff0ff746eab6f01bf08b70ac45")


def test_key_from_url_strips_path_and_ext():
    assert wbi._key_from_url("https://i0.hdslb.com/bfs/wbi/abc123.png") == "abc123"


@pytest.mark.asyncio
async def test_sign_appends_wts_and_correct_w_rid(monkeypatch):
    async def fake_keys(cookie_header):
        return ("img" * 11, "sub" * 11)  # 任意定长 key

    monkeypatch.setattr(wbi, "_fetch_wbi_keys", fake_keys)
    monkeypatch.setattr(wbi.time, "time", lambda: 1700000000.0)

    signed = await wbi.sign({"mid": 123, "pn": 1})

    assert signed["wts"] == "1700000000"
    assert signed["mid"] == "123"
    # w_rid 必须等于 md5(sorted_query + mixin_key)
    mixin = wbi._mixin_key("img" * 11, "sub" * 11)
    import urllib.parse

    query = urllib.parse.urlencode(sorted({"mid": "123", "pn": "1", "wts": "1700000000"}.items()))
    assert signed["w_rid"] == hashlib.md5((query + mixin).encode()).hexdigest()


def test_parse_length_handles_mm_ss_and_hh_mm_ss():
    assert space._parse_length("03:42") == 222.0
    assert space._parse_length("1:05:30") == 3930.0
    assert space._parse_length("bad") == 0.0


@pytest.mark.asyncio
async def test_resolve_mid_from_uid_and_space_url():
    assert await space.resolve_mid("123456") == 123456
    assert await space.resolve_mid("https://space.bilibili.com/789/video") == 789


def test_raise_for_code_maps_rate_limit_and_errors():
    assert space._raise_for_code({"code": 0, "data": {"x": 1}}) == {"x": 1}
    with pytest.raises(space.SpaceRateLimited):
        space._raise_for_code({"code": -799, "message": "频繁"})
    with pytest.raises(space.SpaceFetchError):
        space._raise_for_code({"code": -404, "message": "不存在"})


@pytest.mark.asyncio
async def test_fetch_up_videos_parses_vlist(monkeypatch):
    async def fake_search(mid, page, keyword, order, cookie_header):
        return {
            "list": {
                "vlist": [
                    {"bvid": "BV1", "title": '标题<em class="keyword">一</em> &amp; 二',
                     "pic": "http://i0.hdslb.com/a.jpg",
                     "created": 1700000000, "length": "10:00", "author": "张三"},
                    {"bvid": "", "title": "无 bvid 应被跳过", "created": 0, "length": "1:00"},
                ]
            },
            "page": {"count": 42, "pn": 1, "ps": 30},
        }

    monkeypatch.setattr(space, "_fetch_space_search", fake_search)
    monkeypatch.setattr(space, "_prime_cookies", _noop_prime)

    result = await space.fetch_up_videos(123, page=1)

    assert result.author == "张三"
    assert result.total == 42
    assert result.has_more is True  # 1*30 < 42
    assert [v.bvid for v in result.videos] == ["BV1"]
    assert result.videos[0].title == "标题一 & 二"  # <em> 去掉、&amp; 反转义
    assert result.videos[0].cover.startswith("https://")  # http -> https
    assert result.videos[0].duration == 600.0


@pytest.mark.asyncio
async def test_fetch_up_videos_retries_once_on_rate_limit(monkeypatch):
    calls = {"n": 0}

    async def flaky(mid, page, keyword, order, cookie_header):
        calls["n"] += 1
        if calls["n"] == 1:
            raise space.SpaceRateLimited("风控校验失败")
        return {
            "list": {"vlist": [{"bvid": "BV1", "title": "t", "pic": "", "created": 1, "length": "1:00"}]},
            "page": {"count": 1, "pn": 1, "ps": 30},
        }

    flaky.cache_clear = lambda: None  # 重试路径会调它
    monkeypatch.setattr(space, "_fetch_space_search", flaky)

    monkeypatch.setattr(space, "_prime_cookies", _noop_prime)

    result = await space.fetch_up_videos(123, page=1)
    assert calls["n"] == 2  # 第一次 -352，换身份后第二次成功
    assert [v.bvid for v in result.videos] == ["BV1"]


@pytest.mark.asyncio
async def test_fetch_up_videos_normalizes_bad_order(monkeypatch):
    captured = {}

    async def fake_search(mid, page, keyword, order, cookie_header):
        captured["order"] = order
        return {"list": {"vlist": []}, "page": {"count": 0, "pn": 1, "ps": 30}}

    monkeypatch.setattr(space, "_fetch_space_search", fake_search)

    monkeypatch.setattr(space, "_prime_cookies", _noop_prime)

    await space.fetch_up_videos(1, order="garbage")
    assert captured["order"] == "pubdate"  # 非法 order 归一到 pubdate
