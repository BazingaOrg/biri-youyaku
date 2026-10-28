from __future__ import annotations

import asyncio
import html
import json
import math
import os
import re
import shutil
import signal
import sys
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from biri_youyaku.modules.transcript import TranscriptItem
from biri_youyaku.config import settings
from biri_youyaku.sources.identity import SourceIdentity, identify_url
from biri_youyaku.sources.model import Chapter, MediaMeta


DownloadProgressCallback = Callable[[dict], Awaitable[None]]
_MAX_SUBTITLE_BYTES = 16 * 1024 * 1024
_MAX_PROCESS_OUTPUT_BYTES = 4 * 1024 * 1024
_MAX_SUBTITLE_EVENTS = 200_000
_SUBTITLE_TIMEOUT_SECONDS = 20
_METADATA_TIMEOUT_SECONDS = 30
_DOWNLOAD_TIMEOUT_SECONDS = 1_800
_PERCENT = re.compile(r"\[download\]\s+([\d.]+)%")
_active_work_dirs: set[Path] = set()


def active_work_dirs() -> set[Path]:
    return _active_work_dirs.copy()


def _identity(url: str) -> SourceIdentity:
    identity = identify_url(url)
    if identity is None or identity.provider != "youtube":
        raise ValueError("仅支持单个 YouTube 视频链接")
    return identity


def _safe_error(prefix: str) -> RuntimeError:
    return RuntimeError(prefix)


async def _stop_process(process) -> None:
    pid = getattr(process, "pid", None)
    process_group = os.name == "posix" and isinstance(pid, int)
    if process_group:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.returncode is None:
        process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except asyncio.TimeoutError:
        if not process_group:
            process.kill()
    if process_group:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        os.killpg(pid, signal.SIGKILL)
    if process.returncode is None:
        await process.wait()


async def _drain(reader, *, limit: int) -> tuple[bytes, bool]:
    content = bytearray()
    truncated = False
    while True:
        chunk = await reader.read(65_536)
        if not chunk:
            return bytes(content), truncated
        if len(content) + len(chunk) <= limit:
            content.extend(chunk)
        else:
            truncated = True


async def _stream_download_output(reader, on_progress: DownloadProgressCallback | None) -> bool:
    buffered = bytearray()
    total = 0
    truncated = False
    while True:
        chunk = await reader.read(65_536)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_PROCESS_OUTPUT_BYTES:
            truncated = True
        buffered.extend(chunk)
        while b"\n" in buffered:
            line, _, remaining = buffered.partition(b"\n")
            buffered = bytearray(remaining)
            match = _PERCENT.search(line.decode("utf-8", errors="replace"))
            if match is not None and on_progress is not None:
                await on_progress({"status": "downloading", "percent": float(match.group(1))})
        if len(buffered) > 65_536:
            truncated = True
            buffered.clear()
    if buffered:
        match = _PERCENT.search(buffered.decode("utf-8", errors="replace"))
        if match is not None and on_progress is not None:
            await on_progress({"status": "downloading", "percent": float(match.group(1))})
    return truncated


def _max_duration_seconds() -> float:
    return float(settings.max_video_duration_seconds)


async def _run(
    args: list[str], *, timeout_seconds: float = _METADATA_TIMEOUT_SECONDS
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr, _ = await asyncio.wait_for(
            asyncio.gather(
                _drain(process.stdout, limit=_MAX_PROCESS_OUTPUT_BYTES),
                _drain(process.stderr, limit=_MAX_PROCESS_OUTPUT_BYTES),
                process.wait(),
            ),
            timeout=timeout_seconds,
        )
    except BaseException:
        await _stop_process(process)
        raise
    stdout_bytes, stdout_truncated = stdout
    stderr_bytes, stderr_truncated = stderr
    if stdout_truncated or stderr_truncated:
        raise _safe_error("YouTube 工具输出超出限制")
    return (
        process.returncode or 0,
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


def _subtitle_details(info: dict) -> tuple[str | None, str | None, str | None]:
    for source, key in (("platform", "subtitles"), ("automatic", "automatic_captions")):
        candidates = info.get(key)
        if not isinstance(candidates, dict):
            continue
        languages = [
            item for item in ("zh-Hans", "zh-CN", "zh", "en", "en-US") if item in candidates
        ]
        languages.extend(item for item in candidates if item not in languages)
        for language in languages:
            formats = candidates.get(language)
            if not isinstance(formats, list):
                continue
            for item in formats:
                if (
                    isinstance(item, dict)
                    and item.get("ext") == "json3"
                    and isinstance(item.get("url"), str)
                ):
                    return item["url"], str(language), source
    return None, None, None


def _chapters(value: object) -> list[Chapter] | None:
    if not isinstance(value, list):
        return None
    items = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start = item.get("start_time")
        if (
            not isinstance(start, (float, int))
            or isinstance(start, bool)
            or not math.isfinite(start)
        ):
            continue
        end = item.get("end_time")
        items.append(
            Chapter(
                float(start),
                float(end) if isinstance(end, (float, int)) and math.isfinite(end) else None,
                str(item.get("title") or ""),
            )
        )
    return items or None


async def fetch(url: str) -> MediaMeta:
    identity = _identity(url)
    code, stdout, _stderr = await _run(
        ["--dump-single-json", "--no-playlist", "--no-warnings", identity.canonical_url]
    )
    if code != 0:
        raise _safe_error("无法获取 YouTube 视频信息")
    try:
        info = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise _safe_error("YouTube 返回了无效的视频信息") from exc
    if not isinstance(info, dict) or str(info.get("id") or "") != identity.source_id:
        raise _safe_error("无法确认 YouTube 视频身份")
    if info.get("is_live") or str(info.get("live_status") or "") in {"is_live", "is_upcoming"}:
        raise _safe_error("暂不支持直播或预告视频")
    duration = info.get("duration")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(duration)
        or duration <= 0
        or duration > _max_duration_seconds()
    ):
        raise _safe_error("视频时长不在支持范围内")
    subtitle_url, subtitle_language, subtitle_source = _subtitle_details(info)
    return MediaMeta(
        url=identity.canonical_url,
        bvid="",
        cid=None,
        title=str(info.get("title") or identity.source_id),
        author=str(info.get("uploader") or info.get("channel") or ""),
        duration=float(duration),
        subtitle_url=subtitle_url,
        chapters=_chapters(info.get("chapters")),
        provider="youtube",
        source_id=identity.source_id,
        source_part=identity.source_part,
        subtitle_language=subtitle_language,
        subtitle_source=subtitle_source,
    )


def _subtitle_request_url(value: str) -> str | None:
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.hostname != "www.youtube.com"
        or parsed.path != "/api/timedtext"
    ):
        return None
    try:
        return value if parsed.port in {None, 443} else None
    except ValueError:
        return None


def parse_json3(value: bytes, *, duration: float | None = None) -> list[TranscriptItem]:
    try:
        payload = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("YouTube 字幕格式无效") from exc
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or len(events) > _MAX_SUBTITLE_EVENTS:
        raise ValueError("YouTube 字幕事件无效")
    items = []
    for event in events:
        if not isinstance(event, dict):
            continue
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs", 0)
        if (
            not isinstance(start_ms, int)
            or isinstance(start_ms, bool)
            or start_ms < 0
            or not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or duration_ms < 0
        ):
            raise ValueError("YouTube 字幕时间无效")
        start = start_ms / 1000
        end = start + duration_ms / 1000
        if duration is not None and (
            not math.isfinite(duration) or start > duration or end > duration + 1
        ):
            raise ValueError("YouTube 字幕时间超出视频范围")
        text = "".join(
            str(seg.get("utf8") or "") for seg in event.get("segs", []) if isinstance(seg, dict)
        )
        text = html.unescape(text).replace("\n", " ").strip()
        if text:
            items.append(TranscriptItem(start=start, end=end, text=text))
    if not items:
        raise ValueError("YouTube 字幕为空")
    return items


async def transcript(meta: MediaMeta) -> list[TranscriptItem]:
    if meta.provider != "youtube" or not meta.subtitle_url:
        raise ValueError("没有可用的 YouTube 字幕")
    subtitle_url = _subtitle_request_url(meta.subtitle_url)
    if subtitle_url is None:
        raise ValueError("YouTube 字幕地址无效")
    timeout = httpx.Timeout(_SUBTITLE_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream(
                "GET", subtitle_url, headers={"Accept": "application/json"}
            ) as response:
                if response.status_code != 200:
                    raise _safe_error("无法下载 YouTube 字幕")
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > _MAX_SUBTITLE_BYTES:
                            raise _safe_error("YouTube 字幕文件过大")
                    except ValueError as exc:
                        raise _safe_error("YouTube 字幕响应无效") from exc
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > _MAX_SUBTITLE_BYTES:
                        raise _safe_error("YouTube 字幕文件过大")
    except httpx.HTTPError as exc:
        raise _safe_error("无法下载 YouTube 字幕") from exc
    except ImportError as exc:
        raise _safe_error("当前网络代理缺少 SOCKS 支持，无法下载 YouTube 字幕") from exc
    return parse_json3(bytes(chunks), duration=meta.duration)


async def download(
    meta: MediaMeta, output_path: Path, *, on_progress: DownloadProgressCallback | None = None
) -> Path:
    if meta.provider != "youtube":
        raise ValueError("下载来源不是 YouTube")
    identity = _identity(meta.url)
    if identity.source_id != meta.source_id:
        raise ValueError("YouTube 视频身份不匹配")
    if (
        not math.isfinite(meta.duration)
        or meta.duration <= 0
        or meta.duration > _max_duration_seconds()
    ):
        raise ValueError("视频时长不在支持范围内")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="biri-youyaku-youtube-", dir=output_path.parent))
    _active_work_dirs.add(work_dir.resolve())
    target = work_dir / "audio.%(ext)s"
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-warnings",
            "--newline",
            "--max-filesize",
            "2G",
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "wav",
            "-o",
            str(target),
            identity.canonical_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
        try:
            stdout_truncated, stderr, code = await asyncio.wait_for(
                asyncio.gather(
                    _stream_download_output(process.stdout, on_progress),
                    _drain(process.stderr, limit=_MAX_PROCESS_OUTPUT_BYTES),
                    process.wait(),
                ),
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except BaseException:
            await _stop_process(process)
            raise
        if stdout_truncated or stderr[1]:
            raise _safe_error("YouTube 工具输出超出限制")
        if code != 0:
            raise _safe_error("无法下载 YouTube 音频")
        wav_path = work_dir / "audio.wav"
        if not wav_path.is_file() or wav_path.stat().st_size == 0:
            raise _safe_error("YouTube 下载完成后未找到有效音频")
        final_path = output_path.with_suffix(".wav")
        wav_path.replace(final_path)
        if on_progress is not None:
            await on_progress({"status": "finished", "percent": 100.0})
        return final_path
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        _active_work_dirs.discard(work_dir.resolve())
