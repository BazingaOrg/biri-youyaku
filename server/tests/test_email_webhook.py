import httpx
import pytest

from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.email import webhook


class FakeAsyncClient:
    """模拟共享 email_client()。

    新版 webhook.send 走 `email_client()` 拿单例，测试直接 monkeypatch 它返回
    一个 FakeAsyncClient 实例。
    """

    last_request: dict | None = None
    response = httpx.Response(200, json={"ok": True})

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
    fake = FakeAsyncClient()
    monkeypatch.setattr(webhook, "email_client", lambda: fake)
    FakeAsyncClient.response = httpx.Response(200, json={"ok": True})

    # 安全契约：webhook.send 故意忽略 options.email_recipient，永远只发到
    # settings.email_default_recipient（防止借 Worker 给任意邮箱发垃圾邮件）。
    await webhook.send(video_meta, "# Summary", JobOptions(email_recipient="user@example.com"))

    assert FakeAsyncClient.last_request == {
        "url": "https://worker.example",
        "headers": {"Authorization": "Bearer secret"},
        "json": {
            "to": "default@example.com",
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
    fake = FakeAsyncClient()
    monkeypatch.setattr(webhook, "email_client", lambda: fake)
    FakeAsyncClient.response = httpx.Response(400, json={"ok": False, "error": "Missing required fields"})

    with pytest.raises(RuntimeError, match="Email webhook returned 400: Missing required fields"):
        await webhook.send(video_meta, "# Summary", JobOptions(email_recipient="user@example.com"))
