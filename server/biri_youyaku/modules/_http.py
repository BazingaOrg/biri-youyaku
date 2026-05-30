"""共享的 HTTP / LLM 客户端工厂。

把进程内重复 new 的 httpx / openai client 收成单例，复用连接池。
所有客户端在 `aclose_all()` 中显式释放，由 FastAPI lifespan 调用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_BILI_TIMEOUT = 15.0
_EMAIL_TIMEOUT = 30.0

_bili_client: httpx.AsyncClient | None = None
_email_client: httpx.AsyncClient | None = None
_openai_clients: dict[tuple[str, str, float, int], AsyncOpenAI] = {}


def _bili_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 Biri-Youyaku/0.1",
        "Referer": "https://www.bilibili.com",
    }
    if extra:
        headers.update(extra)
    return headers


def bili_client() -> httpx.AsyncClient:
    """共享的 B 站 / b23 短链 client。

    - follow_redirects=True：短链解析直接拿最终 URL
    - 同一进程一份连接池，复用 TCP / TLS
    """
    global _bili_client
    if _bili_client is None or _bili_client.is_closed:
        _bili_client = httpx.AsyncClient(
            timeout=_BILI_TIMEOUT,
            follow_redirects=True,
            headers=_bili_headers(),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _bili_client


def email_client() -> httpx.AsyncClient:
    """共享的邮件 webhook client。"""
    global _email_client
    if _email_client is None or _email_client.is_closed:
        _email_client = httpx.AsyncClient(
            timeout=_EMAIL_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
        )
    return _email_client


def openai_client(*, api_key: str, base_url: str, timeout: float, max_retries: int) -> AsyncOpenAI:
    """按 (api_key, base_url, timeout, max_retries) 复用 AsyncOpenAI 实例。

    不缓存返回内容，只缓存连接池；切 API Key / base_url 会拿到不同 client，
    保证 token 不会在不同 key 之间串扰。
    """
    key = (api_key, base_url, float(timeout), int(max_retries))
    client = _openai_clients.get(key)
    if client is not None:
        return client
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    )
    _openai_clients[key] = client
    # 防止极端情况下 key 翻新过多内存涨爆。
    # close() 是 async 的；只有当前在 running loop 内时才 fire-and-forget；
    # 否则就让 Python GC 兜底（openai 内部用的是 httpx，析构时会清连接）。
    if len(_openai_clients) > 16:
        oldest_key = next(iter(_openai_clients))
        old = _openai_clients.pop(oldest_key)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(old.close())
    return client


async def aclose_all() -> None:
    """lifespan 关闭时统一释放。失败只 log，不阻塞退出。"""
    global _bili_client, _email_client
    for name, client in (("bili", _bili_client), ("email", _email_client)):
        if client is not None and not client.is_closed:
            try:
                await client.aclose()
            except Exception:
                logger.exception("close %s client failed", name)
    _bili_client = None
    _email_client = None
    for key, oc in list(_openai_clients.items()):
        try:
            await oc.close()
        except Exception:
            logger.exception("close openai client %s failed", key)
    _openai_clients.clear()


def _reset_for_tests() -> None:
    """测试钩子：清空所有缓存的 client，不做 aclose（同步函数）。

    生产代码不要调用。
    """
    global _bili_client, _email_client
    _bili_client = None
    _email_client = None
    _openai_clients.clear()


def request_with_retry_factory(
    *,
    retries: int = 3,
    base_backoff: float = 1.0,
) -> Any:
    """返回一个 async helper：GET 自动重试 + 指数退避。

    用法：
        get = request_with_retry_factory()
        response = await get(client, url, params=...)
    """

    async def get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                response = await client.get(url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < retries - 1:
                    await asyncio.sleep(base_backoff * (2 ** attempt - 1) if attempt > 0 else 0)
        assert last_exc is not None
        raise last_exc

    return get


# 一个全局 helper，所有模块都用同一个 get 重试策略
bili_get = request_with_retry_factory(retries=3, base_backoff=1.0)
