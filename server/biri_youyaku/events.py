"""SSE 用的事件总线。

设计要点：
- 每个 job_id 可以有多个订阅者（多 tab / 多窗口同步打开）。
- 部分事件是「最新值覆盖」语义——只关心最新一帧，旧帧被新帧覆盖后毫无意义：
    - `summary_chunk`：LLM 流式产生的「截至目前的累加全文」。
    - `download_progress` / `transcribe_progress` / `summary_segment`：阶段进度，只看最新百分比。
  这些事件如果走原始 FIFO，消费端（前端 SSE）一慢就会把 100 容量的队列灌满 →
  阻塞 `publish` → 阻塞 LLM 流读循环 / yt-dlp 进度回调 / ASR 循环 → 整条流水线卡死。
  所以每个订阅者为每类这种事件维护一个 latest 槽，走「最新值覆盖」语义：队列里
  每类至多一枚 sentinel，消费端读到 sentinel 就去取对应的 latest 值。
- 其它事件（status/meta 等）走原始 FIFO，因为它们是离散事件不能丢。
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

# 走「最新值覆盖 + 单哨兵」语义的高频事件。其余事件一律按离散 FIFO 处理。
_COALESCED_EVENTS = frozenset(
    {"status", "summary_chunk", "download_progress", "transcribe_progress", "summary_segment"}
)


class SubscriberClosed(Exception):
    """订阅者已关闭，SSE generator 可安静结束。"""


class Subscriber:
    """每个 SSE 连接对应一个 Subscriber。

    `queue` 装离散事件 + 各类合并事件的哨兵；`latest` 按事件名存最新一帧 data。
    """

    __slots__ = ("queue", "latest", "_pending", "_deferred", "_closed", "_closed_event")

    def __init__(self, maxsize: int = 100) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.latest: dict[str, dict[str, Any]] = {}
        self._pending: set[str] = set()
        self._deferred: set[str] = set()
        self._closed = False
        self._closed_event = asyncio.Event()

    async def push(self, event: str, data: dict[str, Any]) -> None:
        if self._closed:
            return
        if event in _COALESCED_EVENTS:
            # 覆盖槽；队列里这类事件只保证有一枚哨兵
            previous = self.latest.get(event)
            # 同一阶段的 status 可以补充/更新字段；切换阶段时必须整体替换，
            # 否则 queued/error/preview 等上一阶段字段会泄漏到新阶段。
            self.latest[event] = (
                {**previous, **data}
                if event == "status"
                and previous is not None
                and previous.get("status") == data.get("status")
                else data
            )
            if event not in self._pending:
                try:
                    self.queue.put_nowait({"_sentinel": event})
                    self._pending.add(event)
                except asyncio.QueueFull:
                    # 队列满了——离散事件堵着没消费。先不上哨兵，下次 publish 再试。
                    # latest[event] 已经记下来了，等下一次能入哨兵时会带出去。
                    self._deferred.add(event)
                    logger.debug("event_bus: queue full, deferring %s sentinel", event)
            return
        try:
            self.queue.put_nowait({"event": event, "data": data})
        except asyncio.QueueFull:
            # 一个慢 SSE 客户端绝不能阻塞 producer；离散事件又不可安全丢弃，关闭它。
            self.close()

    def close(self) -> None:
        """幂等关闭；event 让正在等待的 pop 即刻苏醒。"""
        if self._closed:
            return
        self._closed = True
        self._closed_event.set()
        try:
            self.queue.put_nowait({"_closed": True})
        except asyncio.QueueFull:
            # pop 同时等待 _closed_event，因此即使哨兵无位也能被唤醒。
            pass

    def _flush_deferred(self) -> None:
        while self._deferred and not self._closed and not self.queue.full():
            event = self._deferred.pop()
            if event in self._pending:
                continue
            self.queue.put_nowait({"_sentinel": event})
            self._pending.add(event)

    async def pop(self) -> dict[str, Any]:
        if self._closed:
            raise SubscriberClosed
        get_task = asyncio.create_task(self.queue.get())
        close_task = asyncio.create_task(self._closed_event.wait())
        done, _ = await asyncio.wait((get_task, close_task), return_when=asyncio.FIRST_COMPLETED)
        if close_task in done:
            if not get_task.done():
                get_task.cancel()
                await asyncio.gather(get_task, return_exceptions=True)
            raise SubscriberClosed
        close_task.cancel()
        await asyncio.gather(close_task, return_exceptions=True)
        msg = get_task.result()
        self._flush_deferred()
        if msg.get("_closed"):
            raise SubscriberClosed
        sentinel = msg.get("_sentinel")
        if sentinel is not None:
            self._pending.discard(sentinel)
            return {"event": sentinel, "data": self.latest.get(sentinel, {})}
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
            sub.close()
            self._subscribers[job_id].discard(sub)
            if not self._subscribers[job_id]:
                self._subscribers.pop(job_id, None)

    async def publish(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        # 拷一份避免迭代中 finally 修改集合
        for sub in list(self._subscribers.get(job_id, ())):
            await sub.push(event, data)


event_bus = EventBus()
