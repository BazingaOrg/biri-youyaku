from biri_youyaku.modules._http import bili_client
from biri_youyaku.modules.transcript import TranscriptItem

__all__ = ["TranscriptItem", "download"]


async def download(subtitle_url: str) -> list[TranscriptItem]:
    # 走共享 client，复用 TCP / TLS 连接池
    response = await bili_client().get(subtitle_url)
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
