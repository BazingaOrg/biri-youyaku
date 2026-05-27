import httpx
import pytest

from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.email import webhook


class FakeAsyncClient:
    last_request: dict | None = None
    response = httpx.Response(200, json={"ok": True})

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, **kwargs):
        self.__class__.last_request = {"url": url, **kwargs}
        return self.__class__.response


@pytest.fixture
def video_meta() -> VideoMeta:
    return VideoMeta(
        url="https://www.bilibili.com/video/BV123",
        bvid="BV123",
        cid=1,
        title="Test title",
        author="Test author",
        duration=123,
    )


@pytest.mark.asyncio
async def test_send_uses_worker_payload_contract(monkeypatch, video_meta):
    monkeypatch.setattr(webhook.settings, "email_webhook_url", "https://worker.example")
    monkeypatch.setattr(webhook.settings, "email_webhook_token", "secret")
    monkeypatch.setattr(webhook.settings, "email_default_recipient", "default@example.com")
    monkeypatch.setattr(webhook.settings, "email_subject_template", "[Biri-Youyaku] {{title}}")
    monkeypatch.setattr(webhook.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = httpx.Response(200, json={"ok": True})

    await webhook.send(video_meta, "# Summary", JobOptions(email_recipient="user@example.com"))

    assert FakeAsyncClient.last_request == {
        "url": "https://worker.example",
        "headers": {"Authorization": "Bearer secret"},
        "json": {
            "to": "user@example.com",
            "subject": "[Biri-Youyaku] Test title",
            "markdown": "# Summary",
            "videoMeta": {
                "title": "Test title",
                "url": "https://www.bilibili.com/video/BV123",
                "author": "Test author",
                "publishedAt": "",
            },
            "segmentsStats": {
                "total": 0,
                "success": 0,
                "failed": 0,
            },
        },
    }


@pytest.mark.asyncio
async def test_send_reports_webhook_error_body(monkeypatch, video_meta):
    monkeypatch.setattr(webhook.settings, "email_webhook_url", "https://worker.example")
    monkeypatch.setattr(webhook.settings, "email_webhook_token", "")
    monkeypatch.setattr(webhook.settings, "email_default_recipient", "default@example.com")
    monkeypatch.setattr(webhook.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = httpx.Response(400, json={"ok": False, "error": "Missing required fields"})

    with pytest.raises(RuntimeError, match="Email webhook returned 400: Missing required fields"):
        await webhook.send(video_meta, "# Summary", JobOptions(email_recipient="user@example.com"))
