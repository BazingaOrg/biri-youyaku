import httpx

from biri_youyaku.config import settings
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules._http import email_client
from biri_youyaku.modules.bilibili.meta import VideoMeta


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail") or payload.get("message")
        if detail:
            return f"Email webhook returned {response.status_code}: {detail}"

    text = response.text.strip()
    if text:
        return f"Email webhook returned {response.status_code}: {text[:500]}"
    return f"Email webhook returned {response.status_code}"


async def send(meta: VideoMeta, summary_md: str, options: JobOptions) -> None:
    if not settings.email_webhook_url:
        raise RuntimeError("EMAIL_WEBHOOK_URL 未配置")

    # 安全：忽略 options.email_recipient，永远只发到 .env 配置的默认收件人。
    # 防止拿到 API_TOKEN 的人借用 Worker 给任意邮箱发垃圾邮件，导致 Worker 域名进黑名单。
    # 多收件人 / 转发场景请改用邮件客户端规则，不要把分发逻辑放到这里。
    recipient = (settings.email_default_recipient or "").strip()
    if not recipient:
        raise RuntimeError("EMAIL_DEFAULT_RECIPIENT 未配置")

    subject_template = options.email_subject_template or settings.email_subject_template
    subject = (
        subject_template.replace("{{title}}", meta.title)
        .replace("{{author}}", meta.author)
        .replace("{{date}}", "")
    )
    headers = {}
    if settings.email_webhook_token:
        headers["Authorization"] = f"Bearer {settings.email_webhook_token}"

    # 共享 client，复用 keepalive
    response = await email_client().post(
        settings.email_webhook_url,
        headers=headers,
        json={
            "to": recipient,
            "subject": subject,
            "markdown": summary_md,
            "videoMeta": {
                "title": meta.title,
                "url": meta.url,
                "author": meta.author,
                "publishedAt": "",
            },
            "segmentsStats": {
                "total": 0,
                "success": 0,
                "failed": 0,
            },
        },
    )
    if response.is_error:
        raise RuntimeError(_response_error(response))
