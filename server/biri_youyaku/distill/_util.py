from __future__ import annotations

from datetime import datetime, timezone


def format_ts(ts: int | None) -> str:
    if not ts:
        return "未知日期"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
