from biri_youyaku.modules.bilibili.meta import (
    chapters_from_description,
    chapters_from_pages,
    extract_page_number,
)


def test_extract_page_number_from_url():
    assert extract_page_number("https://www.bilibili.com/video/BV123?p=2") == 2
    assert extract_page_number("https://www.bilibili.com/video/BV123?p=nope") is None


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
