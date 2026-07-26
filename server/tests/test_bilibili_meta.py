from biri_youyaku.modules.bilibili import meta
from biri_youyaku.modules.bilibili.meta import (
    canonical_video_url,
    chapters_from_description,
    chapters_from_pages,
    extract_page_number,
)


def test_extract_page_number_from_url():
    assert extract_page_number("https://www.bilibili.com/video/BV123?p=2") == 2
    assert extract_page_number("https://www.bilibili.com/video/BV123?p=nope") is None


def test_canonical_video_url_discards_untrusted_host_with_valid_bvid():
    assert canonical_video_url("BV1xx", 2) == "https://www.bilibili.com/video/BV1xx?p=2"


async def test_fetch_discards_untrusted_source_url_after_extracting_bvid(monkeypatch):
    async def fake_view(bvid, cookie):
        assert bvid == "BV1xx"
        return {
            "title": "title",
            "owner": {"name": "author"},
            "pages": [{"cid": 1, "duration": 10}, {"cid": 2, "duration": 20}],
        }

    async def fake_player(bvid, cid, cookie):
        return {}

    monkeypatch.setattr(meta, "_fetch_view_cached", fake_view)
    monkeypatch.setattr(meta, "_fetch_player_cached", fake_player)

    result = await meta.fetch("http://127.0.0.1:8000/video/BV1xx?p=2")

    assert result.url == "https://www.bilibili.com/video/BV1xx?p=2"


def test_chapters_from_description_parses_timestamps():
    chapters = chapters_from_description(
        """
        00:00 Intro
        01:20 Main topic
        Ending 02:30
        """,
        duration=200,
    )

    assert [(item.start, item.end, item.title) for item in chapters] == [
        (0, 80, "Intro"),
        (80, 150, "Main topic"),
        (150, 200, "Ending"),
    ]


def test_chapters_from_pages_uses_cumulative_duration():
    chapters = chapters_from_pages([
        {"part": "P1", "duration": 10},
        {"part": "P2", "duration": 20},
    ])

    assert [(item.start, item.end, item.title) for item in chapters] == [
        (0, 10, "P1"),
        (10, 30, "P2"),
    ]
