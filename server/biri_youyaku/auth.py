from fastapi import Header, HTTPException, status

from biri_youyaku.config import settings


async def require_token(
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.api_token:
        return

    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
