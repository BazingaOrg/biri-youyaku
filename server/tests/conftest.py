"""测试夹具的全局配置。"""
import pytest

from biri_youyaku.rate_limit import limiter


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """禁用 slowapi 限流器。

    路由的单测直接调用被 `@limiter.limit(...)` 装饰的函数（如
    `await jobs_route.resume("job-1", ...)`），并不经过真实的 ASGI 请求。
    slowapi 的 wrapper 在 `self.enabled` 为真时会先要求第一个参数是
    `starlette.requests.Request`，否则抛
    "parameter `request` must be an instance of starlette.requests.Request"。
    限流是部署关注点、不是被测逻辑，这里整体关掉让 wrapper 直接透传到原函数。
    """
    previous = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = previous
