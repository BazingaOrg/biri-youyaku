import asyncio

import pytest

from biri_youyaku.events import Subscriber


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
