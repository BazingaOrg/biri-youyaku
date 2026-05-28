from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.asr.formatter import transcript_to_text


def estimate_tokens(text: str) -> int:
    return len(text)


def split_transcript(items: list[TranscriptItem], max_tokens: int) -> list[list[TranscriptItem]]:
    chunks: list[list[TranscriptItem]] = []
    current: list[TranscriptItem] = []
    current_tokens = 0
    for item in items:
        item_tokens = max(1, estimate_tokens(item.text))
        if current and current_tokens + item_tokens > max_tokens:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(item)
        current_tokens += item_tokens
    if current:
        chunks.append(current)
    return chunks


def should_chunk(items: list[TranscriptItem], threshold_tokens: int) -> bool:
    return estimate_tokens(transcript_to_text(items)) > threshold_tokens
