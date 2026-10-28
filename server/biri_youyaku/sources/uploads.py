from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from biri_youyaku.modules.transcript import TranscriptItem


MEDIA_SUFFIXES = frozenset({".mp3", ".m4a", ".wav", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".webm"})
SUBTITLE_SUFFIXES = frozenset({".srt", ".vtt"})
ALLOWED_SUFFIXES = MEDIA_SUFFIXES | SUBTITLE_SUFFIXES
MAX_SUBTITLE_CUES = 20_000
MAX_SUBTITLE_TEXT_BYTES = 8 * 1024 * 1024
_PROCESS_TIMEOUT_SECONDS = 30
_PROCESS_OUTPUT_LIMIT = 64 * 1024
_INPUT_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,mp3,wav,flac,ogg"
_TIMESTAMP = re.compile(
    r"^\s*(?P<start>(?:\d{1,3}:)?\d{2}:\d{2}[,.]\d{1,3})\s+-->\s+"
    r"(?P<end>(?:\d{1,3}:)?\d{2}:\d{2}[,.]\d{1,3})(?:\s+.*)?$"
)
_TAG = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class UploadedSource:
    path: Path
    sha256: str
    filename: str
    kind: str


class UploadError(ValueError):
    pass


def _suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError("不支持的文件类型")
    return suffix


async def receive(request: Request, filename: str, *, root: Path, max_bytes: int) -> UploadedSource:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    suffix = _suffix(filename)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise UploadError("无效的 Content-Length") from exc
        if declared_size < 0:
            raise UploadError("无效的 Content-Length")
        if declared_size > max_bytes:
            raise UploadError("文件超过大小限制")

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / f"{uuid.uuid4().hex}{suffix}").resolve()
    if target.parent != root:
        raise UploadError("无效的上传路径")

    digest = hashlib.sha256()
    total = 0
    descriptor: int | None = None
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        async for chunk in request.stream():
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise UploadError("文件超过大小限制")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
        if total == 0:
            raise UploadError("文件为空")
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        target.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)

    return UploadedSource(
        path=target,
        sha256=digest.hexdigest(),
        filename=Path(filename).name or f"upload{suffix}",
        kind="subtitle" if suffix in SUBTITLE_SUFFIXES else "media",
    )


def _seconds(value: str) -> float:
    pieces = value.replace(",", ".").split(":")
    try:
        seconds = float(pieces[-1])
        minutes = int(pieces[-2])
        hours = int(pieces[-3]) if len(pieces) == 3 else 0
    except (IndexError, ValueError) as exc:
        raise UploadError("字幕时间戳无效") from exc
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        raise UploadError("字幕时间戳无效")
    result = hours * 3600 + minutes * 60 + seconds
    if not math.isfinite(result) or result < 0:
        raise UploadError("字幕时间戳无效")
    return result


def parse_subtitles(data: bytes, suffix: str) -> list[TranscriptItem]:
    suffix = suffix.lower()
    if suffix not in SUBTITLE_SUFFIXES:
        raise UploadError("不支持的字幕类型")
    if len(data) > MAX_SUBTITLE_TEXT_BYTES:
        raise UploadError("字幕文件过大")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("字幕必须是 UTF-8 编码") from exc
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if suffix == ".vtt" and lines and lines[0].strip().startswith("WEBVTT"):
        lines = lines[1:]

    items: list[TranscriptItem] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if suffix == ".vtt" and (
            line.startswith("NOTE") or line.startswith("STYLE") or line.startswith("REGION")
        ):
            index += 1
            while index < len(lines) and lines[index].strip():
                index += 1
            continue
        if "-->" not in line:
            if index + 1 < len(lines) and "-->" in lines[index + 1]:
                index += 1
                line = lines[index].strip()
            else:
                index += 1
                continue
        match = _TIMESTAMP.match(line)
        if match is None:
            raise UploadError("字幕时间轴格式无效")
        start = _seconds(match.group("start"))
        end = _seconds(match.group("end"))
        if end <= start:
            raise UploadError("字幕结束时间必须晚于开始时间")
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            content.append(lines[index].strip())
            index += 1
        value = html.unescape(_TAG.sub("", " ".join(content))).strip()
        if not value:
            raise UploadError("字幕片段没有文本")
        if len(value.encode("utf-8")) > 8_000:
            raise UploadError("字幕片段过长")
        if items and start < items[-1].start:
            raise UploadError("字幕时间轴顺序无效")
        items.append(TranscriptItem(start=start, end=end, text=value))
        if len(items) > MAX_SUBTITLE_CUES:
            raise UploadError("字幕片段过多")
    if not items:
        raise UploadError("没有可用的字幕片段")
    return items


def _local_media(path: Path) -> Path:
    path = path.resolve()
    if path.suffix.lower() not in MEDIA_SUFFIXES or not path.is_file():
        raise UploadError("无效的媒体文件")
    return path


def resolve_input(path: Path, root: Path) -> Path:
    root = root.resolve()
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise UploadError("媒体文件不在导入目录") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise UploadError("不允许符号链接媒体文件")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise UploadError("无效的媒体文件")
    return resolved


async def _read_limited(stream: asyncio.StreamReader) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > _PROCESS_OUTPUT_LIMIT:
            raise UploadError("媒体工具输出异常")
        chunks.append(chunk)


async def _run(args: list[str], *, timeout: float = _PROCESS_TIMEOUT_SECONDS) -> tuple[bytes, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_PROCESS_OUTPUT_LIMIT,
        )
    except FileNotFoundError as exc:
        raise UploadError(f"未安装 {args[0]}") from exc
    stdout_task = asyncio.create_task(_read_limited(process.stdout))
    stderr_task = asyncio.create_task(_read_limited(process.stderr))
    try:
        stdout, stderr, _ = await asyncio.wait_for(
            asyncio.gather(stdout_task, stderr_task, process.wait()), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise UploadError("媒体工具超时") from exc
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise
    if process.returncode != 0:
        raise UploadError("无法读取媒体文件")
    return stdout, stderr


async def probe_media(path: Path) -> float:
    media = _local_media(path)
    stdout, _ = await _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            _INPUT_FORMATS,
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(media),
        ]
    )
    try:
        payload = json.loads(stdout)
        duration = float(payload["format"]["duration"])
        streams = payload.get("streams") or []
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UploadError("媒体元数据无效") from exc
    if not math.isfinite(duration) or duration <= 0 or duration > 24 * 3600:
        raise UploadError("媒体时长无效")
    if not any(stream.get("codec_type") == "audio" for stream in streams if isinstance(stream, dict)):
        raise UploadError("媒体没有音轨")
    return duration


async def prepare_audio(path: Path, output_path: Path) -> Path:
    media = _local_media(path)
    output_path = output_path.resolve()
    if output_path == media or output_path.suffix.lower() != ".wav":
        raise UploadError("无效的音频输出路径")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    try:
        await _run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                _INPUT_FORMATS,
                "-i",
                str(media),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            timeout=300,
        )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise UploadError("音频转换没有生成文件")
        return output_path
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise
