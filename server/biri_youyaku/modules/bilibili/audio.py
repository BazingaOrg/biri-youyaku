import asyncio
import logging
import tempfile
from pathlib import Path
from collections.abc import Awaitable, Callable

from biri_youyaku.config import settings
from biri_youyaku.modules._http import bili_client
from biri_youyaku.modules.bilibili import _guard
from biri_youyaku.modules.bilibili.meta import VideoMeta, canonical_video_url, extract_page_number

DownloadProgressCallback = Callable[[dict], Awaitable[None]]
logger = logging.getLogger(__name__)
_RATE_LIMIT_RETRY_DELAY_SECONDS = 2.0


class BiliRateLimitedError(RuntimeError):
    error_code = "BILI_RATE_LIMITED"


def _cookie_values() -> dict[str, str]:
    values = {}
    if settings.bili_sessdata:
        values["SESSDATA"] = settings.bili_sessdata
    if settings.bili_buvid3:
        values["buvid3"] = settings.bili_buvid3
    if settings.bili_bili_jct:
        values["bili_jct"] = settings.bili_bili_jct
    return values


def _write_cookie_file(values: dict[str, str] | None = None) -> Path | None:
    values = values if values is not None else _cookie_values()
    if not values:
        return None

    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="biri-youyaku-bili-", suffix=".cookies.txt", delete=False)
    with handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for name, value in values.items():
            handle.write(f".bilibili.com\tTRUE\t/\tFALSE\t2147483647\t{name}\t{value}\n")
    return Path(handle.name)


async def _prepare_cookie_values(*, refresh_buvid: bool = False) -> dict[str, str]:
    jar = bili_client().cookies
    try:
        if refresh_buvid:
            getattr(_guard.fetch_buvid, "cache_clear")()
            buvid3, buvid4 = await _guard.fetch_buvid()
            if buvid3:
                jar.set("buvid3", buvid3, domain=".bilibili.com")
            if buvid4:
                jar.set("buvid4", buvid4, domain=".bilibili.com")
        else:
            await _guard.prime_cookies()
    except Exception:
        logger.warning("Bilibili cookie warmup failed", exc_info=True)

    values = _cookie_values()
    for cookie in jar.jar:
        domain = (cookie.domain or "").lstrip(".")
        if domain == "bilibili.com" or domain.endswith(".bilibili.com"):
            values[cookie.name] = cookie.value
    return values


def _iter_error_chain(error: BaseException):
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        exc_info = getattr(current, "exc_info", None)
        if isinstance(exc_info, tuple) and len(exc_info) >= 2 and isinstance(exc_info[1], BaseException):
            pending.append(exc_info[1])
        for candidate in (
            getattr(current, "cause", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(candidate, BaseException):
                pending.append(candidate)


def _http_status(error: BaseException) -> int | None:
    for current in _iter_error_chain(error):
        status = getattr(current, "status", None)
        if isinstance(status, int):
            return status
        response = getattr(current, "response", None)
        response_status = getattr(response, "status", None)
        if isinstance(response_status, int):
            return response_status
    if "HTTP Error 412" in str(error):
        return 412
    return None


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
    loop = asyncio.get_running_loop()
    download_url = canonical_video_url(meta.bvid, extract_page_number(meta.url))

    def progress_hook(data: dict) -> None:
        if on_progress is None:
            return
        payload = _progress_payload(data)
        loop.call_soon_threadsafe(asyncio.create_task, on_progress(payload))

    def run_download(cookie_path: Path | None) -> None:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError("yt-dlp 未安装") from exc

        options = {
            "format": "bestaudio/best",
            "outtmpl": str(target),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "proxy": "",
            "sleep_interval_requests": 0.75,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
        }
        if cookie_path is not None:
            options["cookiefile"] = str(cookie_path)

        try:
            with YoutubeDL(options) as ydl:
                ydl.download([download_url])
        except Exception as exc:
            if _http_status(exc) == 412:
                raise BiliRateLimitedError(str(exc)) from exc
            raise RuntimeError(
                _format_download_error(str(exc), bool(settings.bili_sessdata))
            ) from exc

    for attempt in range(2):
        cookie_path = _write_cookie_file(
            await _prepare_cookie_values(refresh_buvid=attempt > 0)
        )
        try:
            await asyncio.to_thread(run_download, cookie_path)
            break
        except BiliRateLimitedError as exc:
            if attempt == 0:
                await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY_SECONDS)
                continue
            raise BiliRateLimitedError(
                "B 站暂时拒绝下载请求（HTTP 412 风控）。请停止连续重试，等待 10–30 分钟后再试；"
                "若持续失败，请更新 B 站 Cookie。"
            ) from exc
        finally:
            if cookie_path is not None:
                cookie_path.unlink(missing_ok=True)

    wav_path = output_path.with_suffix(".wav")
    if not wav_path.exists():
        matches = list(output_path.parent.glob(f"{output_path.stem}.*"))
        if not matches:
            raise RuntimeError("yt-dlp completed but no audio file was found")
        return matches[0]
    if on_progress is not None:
        await on_progress({"status": "finished", "percent": 100.0})
    return wav_path
