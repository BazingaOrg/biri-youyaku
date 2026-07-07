import pytest
from fastapi import HTTPException

from biri_youyaku.modules.bilibili import dynamic
from biri_youyaku.routes import up as up_route


async def _noop_prime() -> None:
    """替换 dynamic._guard.prime_cookies：测试里不碰 cookie jar / 网络。"""
    return None


async def _noop_sleep(*_args, **_kwargs) -> None:
    """替换 dynamic.asyncio.sleep：测试里不真的等待页间间隔。"""
    return None


def _item(dtype: str, *, id_str="1", pub_ts=1700000000, modules=None, orig=None) -> dict:
    base = {
        "id_str": id_str,
        "type": dtype,
        "modules": modules or {},
    }
    if orig is not None:
        base["orig"] = orig
    if pub_ts is not None:
        base["modules"] = {
            **base["modules"],
            "module_author": {"pub_ts": pub_ts, **(base["modules"].get("module_author") or {})},
        }
    return base


# ---------------------------------------------------------------------------
# parse_item：各 type 解析 + 字段缺失容错
# ---------------------------------------------------------------------------


def test_parse_item_video():
    item = _item(
        "DYNAMIC_TYPE_AV",
        modules={
            "module_dynamic": {
                "desc": {"text": "自己写的话"},
                "major": {
                    "archive": {"bvid": "BV1xx", "title": "标题", "desc": "视频简介"},
                },
            },
        },
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "video"
    assert parsed["bvid"] == "BV1xx"
    assert parsed["title"] == "标题"
    assert parsed["text"] == "自己写的话\n视频简介"
    assert parsed["ts"] == 1700000000
    assert parsed["id"] == "1"


def test_parse_item_word_uses_opus_summary_or_desc():
    item = _item(
        "DYNAMIC_TYPE_WORD",
        modules={
            "module_dynamic": {
                "desc": {"text": "兜底文本"},
                "major": {"opus": {"summary": {"text": "正文摘要"}}},
            },
        },
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "text"
    assert parsed["text"] == "正文摘要"

    # opus.summary 缺失时兜底到 desc.text
    item2 = _item(
        "DYNAMIC_TYPE_WORD",
        modules={"module_dynamic": {"desc": {"text": "兜底文本"}, "major": {}}},
    )
    parsed2 = dynamic.parse_item(item2)
    assert parsed2["text"] == "兜底文本"


def test_parse_item_draw_same_as_word():
    item = _item(
        "DYNAMIC_TYPE_DRAW",
        modules={
            "module_dynamic": {
                "desc": {"text": "配图文案"},
                "major": {"opus": {"summary": {"text": "图集正文"}}},
            },
        },
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "image"
    assert parsed["text"] == "图集正文"


def test_parse_item_article_prefers_major_article():
    item = _item(
        "DYNAMIC_TYPE_ARTICLE",
        modules={
            "module_dynamic": {
                "desc": {},
                "major": {"article": {"title": "文章标题", "desc": "文章摘要"}},
            },
        },
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "article"
    assert parsed["title"] == "文章标题"
    assert parsed["text"] == "文章摘要"


def test_parse_item_article_falls_back_to_opus():
    item = _item(
        "DYNAMIC_TYPE_ARTICLE",
        modules={
            "module_dynamic": {
                "desc": {},
                "major": {"opus": {"title": "opus 标题", "summary": {"text": "opus 摘要"}}},
            },
        },
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "article"
    assert parsed["title"] == "opus 标题"
    assert parsed["text"] == "opus 摘要"


def test_parse_item_forward_combines_own_and_orig():
    orig = {
        "type": "DYNAMIC_TYPE_AV",
        "modules": {
            "module_dynamic": {
                "desc": {"text": ""},
                "major": {"archive": {"bvid": "BV2yy", "title": "原视频", "desc": "原简介"}},
            },
        },
    }
    item = _item(
        "DYNAMIC_TYPE_FORWARD",
        modules={"module_dynamic": {"desc": {"text": "转发评语"}}},
        orig=orig,
    )
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "forward"
    assert parsed["text"] == "转发评语 // 转发：原简介"
    assert parsed["bvid"] == ""
    assert parsed["title"] == ""


def test_parse_item_unknown_type_maps_to_other():
    item = _item("DYNAMIC_TYPE_SOMETHING_NEW", modules={"module_dynamic": {"desc": {}}})
    parsed = dynamic.parse_item(item)
    assert parsed["type"] == "other"
    assert parsed["text"] == ""
    assert parsed["bvid"] == ""
    assert parsed["title"] == ""


def test_parse_item_missing_fields_do_not_raise():
    assert dynamic.parse_item({}) == {
        "id": "",
        "type": "other",
        "text": "",
        "bvid": "",
        "title": "",
        "ts": None,
    }
    # orig 缺失、modules 缺失的转发动态也不应该抛异常
    parsed = dynamic.parse_item({"type": "DYNAMIC_TYPE_FORWARD"})
    assert parsed["type"] == "forward"
    assert parsed["ts"] is None

    # pub_ts 是非法值时容错为 None
    bad_ts_item = {
        "type": "DYNAMIC_TYPE_WORD",
        "modules": {"module_author": {"pub_ts": "not-a-number"}},
    }
    assert dynamic.parse_item(bad_ts_item)["ts"] is None


# ---------------------------------------------------------------------------
# fetch_dynamics_page：-352 重试路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_dynamics_page_retries_once_on_rate_limit(monkeypatch):
    calls = {"n": 0}

    async def flaky(mid, offset):
        calls["n"] += 1
        if calls["n"] == 1:
            raise dynamic.DynamicRateLimited("风控校验失败")
        return {
            "has_more": True,
            "offset": "next",
            "items": [
                _item(
                    "DYNAMIC_TYPE_WORD",
                    modules={"module_dynamic": {"desc": {"text": "hi"}, "major": {}}},
                )
            ],
        }

    flaky.cache_clear = lambda: None
    monkeypatch.setattr(dynamic, "_fetch_feed_page", flaky)
    monkeypatch.setattr(dynamic._guard, "prime_cookies", _noop_prime)

    result = await dynamic.fetch_dynamics_page(123)
    assert calls["n"] == 2
    assert result["has_more"] is True
    assert result["offset"] == "next"
    assert result["items"][0]["text"] == "hi"


# ---------------------------------------------------------------------------
# fetch_all_dynamics：三个停止条件
# ---------------------------------------------------------------------------


def _text_item(id_str: str, ts: int) -> dict:
    return _item(
        "DYNAMIC_TYPE_WORD",
        id_str=id_str,
        pub_ts=ts,
        modules={"module_dynamic": {"desc": {"text": f"动态{id_str}"}, "major": {}}},
    )


@pytest.mark.asyncio
async def test_fetch_all_dynamics_stops_on_has_more_false(monkeypatch):
    async def fake_request(mid, offset):
        return {"has_more": False, "offset": "", "items": [_text_item("1", 1700000000)]}

    monkeypatch.setattr(dynamic, "_request_feed_page", fake_request)
    monkeypatch.setattr(dynamic._guard, "prime_cookies", _noop_prime)
    monkeypatch.setattr(dynamic.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(dynamic.time, "time", lambda: 1700000000.0)

    result = await dynamic.fetch_all_dynamics(1)
    assert [i["id"] for i in result] == ["1"]


@pytest.mark.asyncio
async def test_fetch_all_dynamics_stops_on_max_items(monkeypatch):
    pages = {"n": 0}

    async def fake_request(mid, offset):
        pages["n"] += 1
        return {
            "has_more": True,
            "offset": f"o{pages['n']}",
            "items": [_text_item(f"{pages['n']}-{i}", 1700000000) for i in range(3)],
        }

    monkeypatch.setattr(dynamic, "_request_feed_page", fake_request)
    monkeypatch.setattr(dynamic._guard, "prime_cookies", _noop_prime)
    monkeypatch.setattr(dynamic.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(dynamic.time, "time", lambda: 1700000000.0)

    result = await dynamic.fetch_all_dynamics(1, max_items=5)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_fetch_all_dynamics_stops_on_max_age(monkeypatch):
    now = 1700000000
    old_ts = now - 800 * 86400  # 早于默认 730 天

    async def fake_request(mid, offset):
        return {
            "has_more": True,
            "offset": "next",
            "items": [_text_item("recent", now), _text_item("old", old_ts)],
        }

    monkeypatch.setattr(dynamic, "_request_feed_page", fake_request)
    monkeypatch.setattr(dynamic._guard, "prime_cookies", _noop_prime)
    monkeypatch.setattr(dynamic.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(dynamic.time, "time", lambda: float(now))

    result = await dynamic.fetch_all_dynamics(1, max_age_days=730)
    assert [i["id"] for i in result] == ["recent"]


@pytest.mark.asyncio
async def test_fetch_all_dynamics_skips_old_pinned_without_stopping(monkeypatch):
    """旧置顶动态挂在第一页最前，应跳过它继续收集，而不是当成「已翻到旧内容」停止。"""
    now = 1700000000
    old_ts = now - 800 * 86400

    pinned = _item(
        "DYNAMIC_TYPE_WORD",
        id_str="pinned",
        pub_ts=old_ts,
        modules={
            "module_tag": {"text": "置顶"},
            "module_dynamic": {"desc": {"text": "很久以前的置顶"}, "major": {}},
        },
    )

    async def fake_request(mid, offset):
        return {
            "has_more": False,
            "offset": "",
            "items": [pinned, _text_item("recent", now)],
        }

    monkeypatch.setattr(dynamic, "_request_feed_page", fake_request)
    monkeypatch.setattr(dynamic._guard, "prime_cookies", _noop_prime)
    monkeypatch.setattr(dynamic.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(dynamic.time, "time", lambda: float(now))

    result = await dynamic.fetch_all_dynamics(1, max_age_days=730)
    assert [i["id"] for i in result] == ["recent"]


# ---------------------------------------------------------------------------
# 路由 happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_up_dynamics_route_happy_path(monkeypatch):
    async def fetch(mid, offset=""):
        assert mid == 123
        return {
            "items": [{"id": "1", "type": "text", "text": "hi", "bvid": "", "title": "", "ts": 1}],
            "has_more": False,
            "offset": "",
        }

    monkeypatch.setattr(up_route.dynamic, "fetch_dynamics_page", fetch)

    result = await up_route.up_dynamics(None, 123)
    assert result["ok"] is True
    assert result["mid"] == 123
    assert result["has_more"] is False
    assert result["items"][0]["text"] == "hi"


@pytest.mark.asyncio
async def test_up_dynamics_route_maps_rate_limit_to_503(monkeypatch):
    async def fetch(mid, offset=""):
        raise dynamic.DynamicRateLimited("风控校验失败")

    monkeypatch.setattr(up_route.dynamic, "fetch_dynamics_page", fetch)

    with pytest.raises(HTTPException) as exc:
        await up_route.up_dynamics(None, 123)
    assert exc.value.status_code == 503
    assert "BILI_SESSDATA" in exc.value.detail
