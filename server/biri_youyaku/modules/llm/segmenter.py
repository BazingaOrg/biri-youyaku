from biri_youyaku.modules.transcript import TranscriptItem
from biri_youyaku.modules.asr.formatter import transcript_to_text


def estimate_tokens(text: str) -> int:
    # 粗略代理：直接用字符数当 token 数。对中文约 1:1、英文偏高估，作为「是否分段」
    # 的阈值判断够用，不追求精确。配置项 LLM_CHUNK_TOKEN_THRESHOLD 因此实为字符数阈值。
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
