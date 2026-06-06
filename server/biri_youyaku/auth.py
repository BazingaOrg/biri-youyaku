"""路由鉴权 dependency。

两种模式互斥（CF Access 配置完整时优先）：
- Cloudflare Access：`CF_ACCESS_TEAM_DOMAIN` + `CF_ACCESS_AUD` 都非空 → 校验 JWT。
- 静态 Bearer Token：兜底模式，`API_TOKEN` 非空时校验 Authorization header。
- 两者都没配 → 不校验（本地 dev 模式）。
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from biri_youyaku.cf_access import cf_access_enabled, verify_cf_access
from biri_youyaku.config import settings


def _expected_token() -> str:
    # Strip whitespace defensively: an `.env` line like `API_TOKEN= ` (trailing
    # space) would otherwise be treated as a non-empty token and trigger 401s
    # even though the user clearly meant "no auth".
    return (settings.api_token or "").strip()


async def require_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    # CF Access 优先：完成 SSO 后浏览器会自动带 cookie / header，前端不用知道任何 token。
    if cf_access_enabled():
        # verify_cf_access 校验失败时自己抛 401；这里返回值（claims）暂不需要传给路由。
        verify_cf_access(request)
        return

    expected = _expected_token()
    if not expected:
        return

    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
