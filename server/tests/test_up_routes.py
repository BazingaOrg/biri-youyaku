import pytest
from fastapi import HTTPException

from biri_youyaku.modules.bilibili import space
from biri_youyaku.routes import up as up_route


@pytest.mark.asyncio
async def test_up_videos_merges_summary_status(monkeypatch):
    page_obj = space.UpVideoPage(
        mid=123,
        author="张三",
        total=2,
        page=1,
        page_size=30,
        videos=[
            space.UpVideo(bvid="BV1", title="已总结的", cover="https://x/a.jpg", pubdate=1, duration=60),
            space.UpVideo(bvid="BV2", title="没总结的", cover="https://x/b.jpg", pubdate=2, duration=120),
        ],
    )

    async def fetch(mid, *, page=1, keyword=""):
        assert mid == 123
        return page_obj

    monkeypatch.setattr(up_route.space, "fetch_up_videos", fetch)
    monkeypatch.setattr(
        up_route.repo,
        "summary_status_for_bvids",
        lambda bvids: {"BV1": {"status": "COMPLETED", "job_id": "job-1"}},
    )

    result = await up_route.up_videos(None, 123)

    assert result["author"] == "张三"
    assert result["total"] == 2
    by_bvid = {v["bvid"]: v for v in result["videos"]}
    assert by_bvid["BV1"]["status"] == "COMPLETED"
    assert by_bvid["BV1"]["job_id"] == "job-1"
    assert by_bvid["BV1"]["url"] == "https://www.bilibili.com/video/BV1"
    assert by_bvid["BV2"]["status"] is None
    assert by_bvid["BV2"]["job_id"] is None


@pytest.mark.asyncio
async def test_up_videos_maps_rate_limit_to_503_with_hint(monkeypatch):
    async def fetch(mid, *, page=1, keyword=""):
        raise space.SpaceRateLimited("风控校验失败")

    monkeypatch.setattr(up_route.space, "fetch_up_videos", fetch)

    with pytest.raises(HTTPException) as exc:
        await up_route.up_videos(None, 123)
    assert exc.value.status_code == 503
    assert "BILI_SESSDATA" in exc.value.detail


@pytest.mark.asyncio
async def test_resolve_up_maps_error_to_400(monkeypatch):
    async def resolve(raw):
        raise space.SpaceFetchError("无法识别")

    monkeypatch.setattr(up_route.space, "resolve_mid", resolve)

    with pytest.raises(HTTPException) as exc:
        await up_route.resolve_up(None, "garbage")
    assert exc.value.status_code == 400
