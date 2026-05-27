from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TranscriptItem:
    start: float
    end: float
    text: str


async def download(subtitle_url: str) -> list[TranscriptItem]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(subtitle_url)
        response.raise_for_status()
        payload = response.json()

    items = []
    for row in payload.get("body", []):
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        items.append(
            TranscriptItem(
                start=float(row.get("from") or 0),
                end=float(row.get("to") or row.get("from") or 0),
                text=content,
            )
        )
    return items
