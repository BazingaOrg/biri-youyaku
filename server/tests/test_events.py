import asyncio

import pytest

from biri_youyaku.events import Subscriber, SubscriberClosed


@pytest.mark.asyncio
async def test_summary_segment_is_coalesced_when_queue_is_full():
    subscriber = Subscriber(maxsize=1)
    await subscriber.push("status", {"status": "SUMMARIZING"})

    await asyncio.wait_for(
        subscriber.push("summary_segment", {"done": 1, "total": 3}),
        timeout=0.05,
    )
    await asyncio.wait_for(
        subscriber.push("summary_segment", {"done": 2, "total": 3}),
        timeout=0.05,
    )

    assert await subscriber.pop() == {"event": "status", "data": {"status": "SUMMARIZING"}}

    await subscriber.push("summary_segment", {"done": 3, "total": 3})
    assert await subscriber.pop() == {
        "event": "summary_segment",
        "data": {"done": 3, "total": 3},
    }


@pytest.mark.asyncio
async def test_slow_subscriber_never_blocks_and_delivers_deferred_latest_event():
    subscriber = Subscriber(maxsize=1)
    await subscriber.push("meta", {"title": "queued"})

    await asyncio.wait_for(subscriber.push("summary_chunk", {"text": "first"}), timeout=0.05)
    await asyncio.wait_for(subscriber.push("summary_chunk", {"text": "final"}), timeout=0.05)

    assert await subscriber.pop() == {"event": "meta", "data": {"title": "queued"}}
    assert await subscriber.pop() == {"event": "summary_chunk", "data": {"text": "final"}}


@pytest.mark.asyncio
async def test_non_coalesced_overflow_closes_and_wakes_waiting_pop():
    subscriber = Subscriber(maxsize=1)
    await subscriber.push("meta", {"queued": True})
    await asyncio.wait_for(subscriber.push("meta", {"overflow": True}), timeout=0.05)
    with pytest.raises(SubscriberClosed):
        await subscriber.pop()

    subscriber = Subscriber(maxsize=1)
    waiter = asyncio.create_task(subscriber.pop())
    await asyncio.sleep(0)
    subscriber.close()
    with pytest.raises(SubscriberClosed):
        await asyncio.wait_for(waiter, timeout=0.05)

    await subscriber.push("meta", {"ignored": True})
    with pytest.raises(SubscriberClosed):
        await subscriber.pop()


@pytest.mark.asyncio
async def test_status_is_shallow_merged_while_pending():
    subscriber = Subscriber(maxsize=1)
    await subscriber.push("status", {"status": "DOWNLOADING", "queued": True})
    await subscriber.push("status", {"status": "DOWNLOADING", "queued": False})

    assert await subscriber.pop() == {
        "event": "status",
        "data": {"status": "DOWNLOADING", "queued": False},
    }


@pytest.mark.asyncio
async def test_status_replaces_data_when_stage_changes_while_pending():
    subscriber = Subscriber(maxsize=1)
    await subscriber.push(
        "status",
        {"status": "QUEUED", "queued": True, "preview": "stale", "error": "stale"},
    )
    await subscriber.push("status", {"status": "SUMMARIZING"})

    assert await subscriber.pop() == {
        "event": "status",
        "data": {"status": "SUMMARIZING"},
    }
