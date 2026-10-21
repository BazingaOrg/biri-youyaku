"""Shared helpers for library list/search."""

from __future__ import annotations

import base64
import json
from typing import Any

from biri_youyaku.config import KNOWLEDGE_SOFT_DELETE_DAYS
from biri_youyaku.jobs.repo import now_ms

_DAY_MS = 24 * 60 * 60 * 1000


class CursorError(ValueError):
    pass


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str | None) -> dict[str, Any] | None:
    if token is None or token == "":
        return None
    pad = "=" * (-len(token) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(token + pad).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CursorError("invalid cursor") from exc
    if not isinstance(data, dict):
        raise CursorError("invalid cursor")
    return data


def parse_tags(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if not isinstance(raw, str):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item)]


def like_contains(query: str) -> str:
    escaped = (query or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def bvid_lookup_key(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) >= 2 and text[:2].upper() == "BV":
        text = text[2:]
    return text.casefold()


def bvid_exact_match(query: str, stored: str | None) -> bool:
    q_key = bvid_lookup_key(query)
    s_key = bvid_lookup_key(stored)
    return bool(q_key) and q_key == s_key


def expires_at_ms(deleted_at: int | None) -> int | None:
    if deleted_at is None:
        return None
    return int(deleted_at) + int(KNOWLEDGE_SOFT_DELETE_DAYS) * _DAY_MS


def days_left(deleted_at: int | None, *, now: int | None = None) -> int | None:
    expires = expires_at_ms(deleted_at)
    if expires is None:
        return None
    remaining = expires - int(now if now is not None else now_ms())
    if remaining <= 0:
        return 0
    return (remaining + _DAY_MS - 1) // _DAY_MS


def etag_matches(header: str | None, content_hash: str | None) -> bool:
    if not header or not content_hash:
        return False
    if header.strip() == "*":
        return True
    wanted = content_hash.strip().strip('"')
    for part in header.split(","):
        token = part.strip()
        if token.startswith("W/"):
            token = token[2:].strip()
        if token.strip('"') == wanted:
            return True
    return False
