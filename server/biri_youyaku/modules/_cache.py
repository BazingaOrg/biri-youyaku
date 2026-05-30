"""轻量异步 LRU + TTL 缓存装饰器。

只服务模块内部「确定性 IO 结果」的复用，比如 B 站元信息、b23 短链解析。
不缓存 LLM 响应、不缓存任何用户态相关的数据。
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")


def ttl_lru(maxsize: int, ttl_seconds: float):
    """异步函数的 LRU + TTL。

    - key 由所有位置参数与关键字参数拼成 (`hashable` 类型)；不支持 unhashable 参数。
    - TTL 到期或被踢出 LRU 后下次调用会重新执行。
    - 同 key 并发只会执行一次（用 per-key Lock 收敛）。

    实现要点：
    - 装饰器在 import 时不可能拿到 running loop，所以 per-key `asyncio.Lock` 必须**延迟到
      第一次调用时**在当前 loop 内创建，否则 lifespan / pytest fixture 等多 loop 场景会
      抛 "attached to a different loop"。
    - 维护 dict 用 `threading.Lock`（同步、与 loop 无关），保证多 loop 安全。
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        cache: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        # key → (asyncio.Lock, owning_loop)；loop 变化时丢弃旧锁重建
        locks: dict[Hashable, tuple[asyncio.Lock, asyncio.AbstractEventLoop]] = {}
        meta_lock = threading.Lock()

        def _make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Hashable:
            if not kwargs:
                return args
            return (args, tuple(sorted(kwargs.items())))

        def _get_lock(key: Hashable, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
            with meta_lock:
                existing = locks.get(key)
                if existing is not None and existing[1] is loop:
                    return existing[0]
                lock = asyncio.Lock()
                locks[key] = (lock, loop)
                return lock

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            key = _make_key(args, kwargs)
            now = time.monotonic()

            # 快路径：命中且未过期
            entry = cache.get(key)
            if entry is not None and now - entry[0] < ttl_seconds:
                cache.move_to_end(key)
                return entry[1]

            # 慢路径：进 per-key Lock 防止打雷（lazy 创建，绑定当前 loop）
            loop = asyncio.get_running_loop()
            lock = _get_lock(key, loop)
            async with lock:
                entry = cache.get(key)
                if entry is not None and time.monotonic() - entry[0] < ttl_seconds:
                    cache.move_to_end(key)
                    return entry[1]
                value = await func(*args, **kwargs)
                cache[key] = (time.monotonic(), value)
                cache.move_to_end(key)
                while len(cache) > maxsize:
                    evicted_key, _ = cache.popitem(last=False)
                    with meta_lock:
                        locks.pop(evicted_key, None)
                return value

        def _invalidate() -> None:
            cache.clear()
            with meta_lock:
                locks.clear()

        wrapper.cache_clear = _invalidate  # type: ignore[attr-defined]
        wrapper.cache_info = lambda: {"size": len(cache), "maxsize": maxsize, "ttl": ttl_seconds}  # type: ignore[attr-defined]
        return wrapper

    return decorator
