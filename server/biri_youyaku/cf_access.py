"""Cloudflare Access JWT 校验。

CF Access 把 SSO 后的身份签成一个短期 JWT，通过 `Cf-Access-Jwt-Assertion` header
注入到 backend（同时也会落在 `CF_Authorization` cookie 里，作为 SSE/直链场景的退路）。

本模块做三件事：
1. 缓存 JWKS（CF 的公钥集，每个 team domain 一份），按 TTL 失效后重拉。
2. 用 JWKS 验签、校验 aud / iss / exp。
3. 提供一个 FastAPI dependency `require_cf_access`：缺失或不合法 → 401。

设计取舍：
- JWKS 缓存放进程内，进程重启会重新拉一次（CF JWKS 几乎不变，问题不大）。
- 不做主动刷新——拉完就用直到 TTL 过期，没必要后台轮询。
- 校验失败时只返回通用「Invalid Cloudflare Access token」，详细原因写日志，避免给攻击者反馈调试信号。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from biri_youyaku.config import settings

_log = logging.getLogger("biri_youyaku.auth")

# JWKS 缓存 1 小时；CF 的密钥轮换周期远长于这个，但短缓存能让密钥被撤销时较快感知。
_JWKS_TTL_SECONDS = 3600

_jwks_client_cache: dict[str, tuple[PyJWKClient, float]] = {}


def _certs_url() -> str:
    return f"https://{settings.cf_access_team_domain}/cdn-cgi/access/certs"


def _issuer() -> str:
    return f"https://{settings.cf_access_team_domain}"


def _get_jwks_client() -> PyJWKClient:
    now = time.monotonic()
    cached = _jwks_client_cache.get(_certs_url())
    if cached is not None and now - cached[1] < _JWKS_TTL_SECONDS:
        return cached[0]
    # PyJWKClient 自带 lru_cache，但我们额外按 TTL 重建一次客户端，确保 JWKS 轮换被感知。
    client = PyJWKClient(_certs_url(), cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
    _jwks_client_cache[_certs_url()] = (client, now)
    return client


def cf_access_enabled() -> bool:
    """两项都填了才算启用。"""
    return bool(settings.cf_access_team_domain.strip() and settings.cf_access_aud.strip())


def _extract_token(request: Request) -> str | None:
    # 主路径：header（XHR / fetch / SSE EventSource 都能带）
    token = request.headers.get("cf-access-jwt-assertion")
    if token:
        return token.strip()
    # 退路：cookie（CF 同样会签发；EventSource 不能加 header 时有用）
    cookie = request.cookies.get("CF_Authorization")
    if cookie:
        return cookie.strip()
    return None


def verify_cf_access(request: Request) -> dict[str, Any]:
    """验签 + 校验 aud/iss/exp；返回 claims（含 email/sub）。失败 → HTTPException。"""
    token = _extract_token(request)
    if not token:
        _log.info("CF Access: missing Cf-Access-Jwt-Assertion header & CF_Authorization cookie")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Cloudflare Access token",
        )

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    except (jwt.PyJWKClientError, httpx.HTTPError) as exc:
        _log.warning("CF Access: JWKS lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudflare Access JWKS unavailable",
        ) from exc

    try:
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            audience=settings.cf_access_aud.strip(),
            issuer=_issuer(),
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.InvalidTokenError as exc:
        _log.info("CF Access: token rejected (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cloudflare Access token",
        ) from exc

    return claims
