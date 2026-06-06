"""SSE 用的事件总线。

设计要点：
- 每个 job_id 可以有多个订阅者（多 tab / 多窗口同步打开）。
- `summary_chunk` 是 LLM 流式产生的「累加文本」——每次 publish 都带「截至目前的全文」。
  如果消费端（前端 SSE）来不及消费，老的 chunk 完全没意义（被新 chunk 覆盖），不能让
  它们把 100 容量的 FIFO 队列灌满 → 阻塞 `publish` → 阻塞 LLM 流读循环 → 整个总结卡死。
  所以这里每个订阅者额外维护一个 latest_summary 槽，summary_chunk 走「最新值覆盖」
  语义：队列里只放一枚 sentinel，消费端读到 sentinel 就去取 latest_summary。
- 其它事件（status/meta/progress）走原始 FIFO，因为它们是离散事件不能丢。
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

# summary_chunk 用一个固定 sentinel 入队，消费端读到就去取 latest_summary_text
_SUMMARY_SENTINEL = {"_sentinel": "summary_chunk"}


class Subscriber:
    """每个 SSE 连接对应一个 Subscriber。

    `queue` 装离散事件 + summary 哨兵；`latest_summary_text` 装最新累加文本。
    """

    __slots__ = ("queue", "latest_summary_text", "_summary_pending")

    def __init__(self, maxsize: int = 100) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.latest_summary_text: str | None = None
        self._summary_pending = False

    async def push(self, event: str, data: dict[str, Any]) -> None:
        if event == "summary_chunk":
            # 累加文本：覆盖槽；队列里只保证有一枚哨兵
            self.latest_summary_text = str(data.get("text", "") or "")
            if not self._summary_pending:
                try:
                    self.queue.put_nowait(_SUMMARY_SENTINEL)
                    self._summary_pending = True
                except asyncio.QueueFull:
                    # 队列满了——离散事件堵着没消费。先不上哨兵，下次 publish 再试。
                    # latest_summary_text 已经记下来了，等下一次能入哨兵时会带出去。
                    logger.debug("event_bus: queue full, deferring summary sentinel")
            return
        # 离散事件不能丢，put 阻塞（背压）是符合预期的
        await self.queue.put({"event": event, "data": data})

    async def pop(self) -> dict[str, Any]:
        msg = await self.queue.get()
        if msg.get("_sentinel") == "summary_chunk":
            self._summary_pending = False
            return {"event": "summary_chunk", "data": {"text": self.latest_summary_text or ""}}
        return msg


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[Subscriber]] = defaultdict(set)

    @asynccontextmanager
    async def subscribe(self, job_id: str) -> AsyncIterator[Subscriber]:
        sub = Subscriber()
        self._subscribers[job_id].add(sub)
        try:
            yield sub
        finally:
            self._subscribers[job_id].discard(sub)
            if not self._subscribers[job_id]:
                self._subscribers.pop(job_id, None)

    async def publish(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        # 拷一份避免迭代中 finally 修改集合
        for sub in list(self._subscribers.get(job_id, ())):
            await sub.push(event, data)


event_bus = EventBus()
