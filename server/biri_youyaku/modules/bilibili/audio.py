import asyncio
import tempfile
from pathlib import Path
from collections.abc import Awaitable, Callable

from biri_youyaku.config import settings
from biri_youyaku.modules.bilibili.meta import VideoMeta

DownloadProgressCallback = Callable[[dict], Awaitable[None]]


def _cookie_values() -> dict[str, str]:
    values = {}
    if settings.bili_sessdata:
        values["SESSDATA"] = settings.bili_sessdata
    if settings.bili_buvid3:
        values["buvid3"] = settings.bili_buvid3
    if settings.bili_bili_jct:
        values["bili_jct"] = settings.bili_bili_jct
    return values


def _write_cookie_file() -> Path | None:
    values = _cookie_values()
    if not values:
        return None

    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="biri-youyaku-bili-", suffix=".cookies.txt", delete=False)
    with handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for name, value in values.items():
            handle.write(f".bilibili.com\tTRUE\t/\tFALSE\t2147483647\t{name}\t{value}\n")
    return Path(handle.name)


def _format_download_error(stderr: str, has_cookies: bool) -> str:
    message = stderr.strip() or "yt-dlp failed"
    if "No video formats found" in message:
        hint = "请确认 BILI_SESSDATA / BILI_BUVID3 / BILI_BILI_JCT 有效，并在后端运行环境中更新 yt-dlp。"
        if not has_cookies:
            hint = "该视频可能需要登录 Cookie，请配置 BILI_SESSDATA / BILI_BUVID3 / BILI_BILI_JCT。"
        return f"{message}\n{hint}"
    return message


def _progress_payload(data: dict) -> dict:
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes") or 0
    percent = None
    if total:
        percent = min(100.0, max(0.0, downloaded / total * 100))
    return {
        "status": data.get("status"),
        "downloaded_bytes": downloaded,
        "total_bytes": total,
        "percent": percent,
        "speed": data.get("speed"),
        "eta": data.get("eta"),
    }


async def download(
    meta: VideoMeta,
    output_path: Path,
    *,
    on_progress: DownloadProgressCallback | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target = output_path.with_suffix(".%(ext)s")
    cookie_path = _write_cookie_file()
    loop = asyncio.get_running_loop()

    def progress_hook(data: dict) -> None:
        if on_progress is None:
            return
        payload = _progress_payload(data)
        loop.call_soon_threadsafe(asyncio.create_task, on_progress(payload))

    def run_download() -> None:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError("yt-dlp 未安装") from exc

        options = {
            "format": "bestaudio/best",
            "outtmpl": str(target),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "http_headers": {
                "Referer": "https://www.bilibili.com",
                "User-Agent": "Mozilla/5.0 Biri-Youyaku/0.1",
            },
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
        }
        if cookie_path is not None:
            options["cookiefile"] = str(cookie_path)

        try:
            with YoutubeDL(options) as ydl:
                ydl.download([meta.url])
        except Exception as exc:
            raise RuntimeError(_format_download_error(str(exc), cookie_path is not None)) from exc

    try:
        await asyncio.to_thread(run_download)
        wav_path = output_path.with_suffix(".wav")
        if not wav_path.exists():
            matches = list(output_path.parent.glob(f"{output_path.stem}.*"))
            if not matches:
                raise RuntimeError("yt-dlp completed but no audio file was found")
            return matches[0]
        if on_progress is not None:
            await on_progress({"status": "finished", "percent": 100.0})
        return wav_path
    finally:
        if cookie_path is not None:
            cookie_path.unlink(missing_ok=True)
