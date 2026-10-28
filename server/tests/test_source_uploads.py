import asyncio
from pathlib import Path

import pytest
from starlette.requests import Request

from biri_youyaku.sources.uploads import (
    UploadError,
    _PROCESS_OUTPUT_LIMIT,
    _read_limited,
    parse_subtitles,
    prepare_audio,
    probe_media,
    receive,
    resolve_input,
)


def request_for(chunks: list[bytes], headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    remaining = iter(chunks)

    async def body():
        try:
            return {"type": "http.request", "body": next(remaining), "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers or []}, body)


@pytest.mark.asyncio
async def test_receive_uses_generated_path_and_digest(tmp_path: Path):
    uploaded = await receive(request_for([b"abc", b"def"]), "../../voice.MP3", root=tmp_path, max_bytes=10)

    assert uploaded.path.parent == tmp_path.resolve()
    assert uploaded.path.suffix == ".mp3"
    assert uploaded.filename == "voice.MP3"
    assert uploaded.path.read_bytes() == b"abcdef"
    assert uploaded.sha256 == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"


@pytest.mark.asyncio
async def test_receive_removes_partial_file_when_limited(tmp_path: Path):
    with pytest.raises(UploadError, match="超过"):
        await receive(request_for([b"abcd", b"ef"]), "voice.wav", root=tmp_path, max_bytes=5)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_receive_rejects_disallowed_and_empty(tmp_path: Path):
    with pytest.raises(UploadError):
        await receive(request_for([b"x"]), "stream.m3u8", root=tmp_path, max_bytes=10)
    with pytest.raises(UploadError, match="为空"):
        await receive(request_for([]), "voice.wav", root=tmp_path, max_bytes=10)


def test_parse_vtt_and_srt():
    vtt = b"\xef\xbb\xbfWEBVTT\n\nNOTE ignored\nnot a cue\n\nSTYLE\n::cue { color: red; }\n\nintro\n00:00:01.200 --> 00:00:03.000 align:start\nhello <b>world</b> &amp; all\n\n"
    srt = b"1\n00:00:04,000 --> 00:00:05,500\nsecond line\n\n"

    first = parse_subtitles(vtt, ".vtt")
    second = parse_subtitles(srt, ".srt")

    assert first[0].text == "hello world & all"
    assert first[0].start == 1.2
    assert second[0].end == 5.5


@pytest.mark.parametrize(
    "content",
    [
        b"00:00:03 --> 00:00:01\nbad\n",
        b"00:99:01 --> 00:00:02\nbad\n",
        b"00:00:01 --> malformed\nbad\n",
        b"WEBVTT\n\n",
    ],
)
def test_parse_subtitles_rejects_invalid(content: bytes):
    with pytest.raises(UploadError):
        parse_subtitles(content, ".vtt")


@pytest.mark.asyncio
async def test_probe_and_prepare_audio_for_local_wav(tmp_path: Path):
    if not __import__("shutil").which("ffmpeg") or not __import__("shutil").which("ffprobe"):
        pytest.skip("ffmpeg unavailable")
    source = tmp_path / "input.wav"
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=0.1", str(source)
    )
    assert await process.wait() == 0
    duration = await probe_media(source)
    output = await prepare_audio(source, tmp_path / "audio.wav")
    assert duration > 0
    assert output.stat().st_size > 0


@pytest.mark.asyncio
async def test_probe_rejects_playlist_and_missing_file(tmp_path: Path):
    playlist = tmp_path / "source.m3u8"
    playlist.write_text("#EXTM3U\n", encoding="utf-8")
    with pytest.raises(UploadError):
        await probe_media(playlist)


@pytest.mark.asyncio
async def test_probe_rejects_disguised_playlist(tmp_path: Path):
    disguised = tmp_path / "source.wav"
    disguised.write_text("ffconcat version 1.0\nfile /etc/passwd\n", encoding="utf-8")
    with pytest.raises(UploadError):
        await probe_media(disguised)


def test_resolve_input_requires_non_symlink_under_root(tmp_path: Path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"data")
    assert resolve_input(source, tmp_path) == source.resolve()
    linked = tmp_path / "linked.wav"
    linked.symlink_to(source)
    with pytest.raises(UploadError):
        resolve_input(linked, tmp_path)
    with pytest.raises(UploadError):
        resolve_input(Path("/etc/hosts"), tmp_path)


@pytest.mark.asyncio
async def test_read_limited_rejects_large_process_output():
    class Stream:
        def __init__(self):
            self.calls = 0

        async def read(self, _: int) -> bytes:
            self.calls += 1
            return b"x" * (_PROCESS_OUTPUT_LIMIT + 1) if self.calls == 1 else b""

    with pytest.raises(UploadError, match="输出"):
        await _read_limited(Stream())
