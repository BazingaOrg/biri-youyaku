from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.llm.segmenter import estimate_tokens, should_chunk, split_transcript


def test_estimate_tokens_counts_characters():
    assert estimate_tokens("abc中文") == 5


def test_split_transcript_keeps_order_and_budget():
    items = [
        TranscriptItem(start=0, end=1, text="aaa"),
        TranscriptItem(start=1, end=2, text="bbb"),
        TranscriptItem(start=2, end=3, text="cccc"),
    ]

    chunks = split_transcript(items, max_tokens=6)

    assert [[item.text for item in chunk] for chunk in chunks] == [["aaa", "bbb"], ["cccc"]]


def test_should_chunk_uses_full_transcript_text():
    items = [TranscriptItem(start=0, end=1, text="abc"), TranscriptItem(start=1, end=2, text="def")]

    assert should_chunk(items, threshold_tokens=5) is True
    assert should_chunk(items, threshold_tokens=10) is False
