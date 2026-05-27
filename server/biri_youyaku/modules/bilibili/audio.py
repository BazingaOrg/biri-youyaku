import asyncio
import sys
import tempfile
from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.modules.bilibili.meta import VideoMeta


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


async def download(meta: VideoMeta, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target = output_path.with_suffix(".%(ext)s")
    cookie_path = _write_cookie_file()
    try:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "bestaudio/best",
            "-o",
            str(target),
            "--extract-audio",
            "--audio-format",
            "wav",
            "--referer",
            "https://www.bilibili.com",
            "--user-agent",
            "Mozilla/5.0 Biri-Youyaku/0.1",
            "--no-playlist",
            *(["--cookies", str(cookie_path)] if cookie_path is not None else []),
            meta.url,
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(_format_download_error(stderr.decode("utf-8", errors="ignore"), cookie_path is not None))
        wav_path = output_path.with_suffix(".wav")
        if not wav_path.exists():
            matches = list(output_path.parent.glob(f"{output_path.stem}.*"))
            if not matches:
                raise RuntimeError("yt-dlp completed but no audio file was found")
            return matches[0]
        return wav_path
    finally:
        if cookie_path is not None:
            cookie_path.unlink(missing_ok=True)
