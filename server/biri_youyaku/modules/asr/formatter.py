from biri_youyaku.modules.transcript import TranscriptItem


def transcript_to_text(items: list[TranscriptItem]) -> str:
    return "\n".join(item.text.strip() for item in items if item.text.strip())
