from fastapi import Header, HTTPException, status

from biri_youyaku.config import settings


def _expected_token() -> str:
    # Strip whitespace defensively: an `.env` line like `API_TOKEN= ` (trailing
    # space) would otherwise be treated as a non-empty token and trigger 401s
    # even though the user clearly meant "no auth".
    return (settings.api_token or "").strip()


async def require_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = _expected_token()
    if not expected:
        return

    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
