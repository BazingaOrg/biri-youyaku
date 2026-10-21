from biri_youyaku.modules.transcript import TranscriptItem

_STAMP_INTERVAL_SEC = 30.0


def format_timestamp(start: float) -> str:
    total = max(0, int(start))
    minutes, seconds = divmod(total, 60)
    return f"{minutes:02d}:{seconds:02d}"


def transcript_to_text(items: list[TranscriptItem]) -> str:
    lines: list[str] = []
    last_stamp_at: float | None = None
    for item in items:
        text = (item.text or "").strip()
        if not text:
            continue
        start = getattr(item, "start", None)
        if start is not None:
            start_sec = float(start)
            if last_stamp_at is None or start_sec - last_stamp_at >= _STAMP_INTERVAL_SEC:
                lines.append(f"[{format_timestamp(start_sec)}]")
                last_stamp_at = start_sec
        lines.append(text)
    return "\n".join(lines)
