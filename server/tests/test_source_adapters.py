import asyncio
import json
from pathlib import Path

import pytest

from biri_youyaku.sources.identity import identify_url
from biri_youyaku.sources.model import MediaMeta
from biri_youyaku.sources import youtube


@pytest.mark.parametrize(
    ("raw", "provider", "source_id", "part", "canonical"),
    [
        (
            "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
            "bilibili",
            "BV1xx411c7mD",
            "2",
            "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        ),
        (
            "https://youtu.be/dQw4w9WgXcQ",
            "youtube",
            "dQw4w9WgXcQ",
            "",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        (
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "youtube",
            "dQw4w9WgXcQ",
            "",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
    ],
)
def test_identify_supported_urls(raw, provider, source_id, part, canonical):
    identity = identify_url(raw)
    assert identity is not None
    assert (
        identity.provider,
        identity.source_id,
        identity.source_part,
        identity.canonical_url,
    ) == (provider, source_id, part, canonical)


@pytest.mark.parametrize(
    "raw",
    [
        "https://b23.tv/abc",
        "https://evil.example/video/BV1xx411c7mD",
        "https://www.youtube.com/watch?v=too-short",
        "https://user@www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com:444/watch?v=dQw4w9WgXcQ",
        "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_identify_rejects_untrusted_urls(raw):
    assert identify_url(raw) is None


def test_parse_json3_keeps_timing_and_text():
    items = youtube.parse_json3(
        json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 1250,
                        "dDurationMs": 750,
                        "segs": [{"utf8": "hello"}, {"utf8": " world"}],
                    }
                ]
            }
        ).encode()
    )
    assert items[0].start == 1.25
    assert items[0].end == 2.0
    assert items[0].text == "hello world"


def test_parse_json3_rejects_out_of_bounds_timing():
    with pytest.raises(ValueError, match="超出"):
        youtube.parse_json3(
            json.dumps(
                {"events": [{"tStartMs": 2000, "dDurationMs": 1, "segs": [{"utf8": "x"}]}]}
            ).encode(),
            duration=1,
        )


def test_subtitle_endpoint_is_exact_and_safe():
    assert youtube._subtitle_request_url("https://www.youtube.com/api/timedtext?v=x") is not None
    assert youtube._subtitle_request_url("https://evil.youtube.com/api/timedtext?v=x") is None
    assert youtube._subtitle_request_url("https://www.youtube.com/other?v=x") is None


@pytest.mark.asyncio
async def test_fetch_rejects_live_video(monkeypatch):
    async def fake_run(_args):
        return 0, json.dumps({"id": "dQw4w9WgXcQ", "duration": 30, "is_live": True}), ""

    monkeypatch.setattr(youtube, "_run", fake_run)
    with pytest.raises(RuntimeError, match="直播"):
        await youtube.fetch("https://youtu.be/dQw4w9WgXcQ")


@pytest.mark.asyncio
async def test_fetch_uses_configured_duration_limit(monkeypatch):
    async def fake_run(_args):
        return 0, json.dumps({"id": "dQw4w9WgXcQ", "duration": 3}), ""

    monkeypatch.setattr(youtube, "_run", fake_run)
    monkeypatch.setattr(youtube.settings, "max_video_duration_seconds", 2)
    with pytest.raises(RuntimeError, match="时长"):
        await youtube.fetch("https://youtu.be/dQw4w9WgXcQ")


@pytest.mark.asyncio
async def test_download_rejects_missing_output(monkeypatch, tmp_path: Path):
    class Stream:
        async def read(self, _size):
            return b""

    class Process:
        stdout = Stream()
        stderr = Stream()
        returncode = None

        async def wait(self):
            return 0

        def kill(self):
            return None

    async def fake_exec(*_args, **_kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    meta = MediaMeta(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "",
        None,
        "x",
        "",
        10,
        provider="youtube",
        source_id="dQw4w9WgXcQ",
    )
    with pytest.raises(RuntimeError, match="未找到有效音频"):
        await youtube.download(meta, tmp_path / "audio")


@pytest.mark.asyncio
async def test_download_reports_progress_before_process_exits(monkeypatch, tmp_path: Path):
    progressed = asyncio.Event()

    class Stream:
        def __init__(self, values):
            self.values = iter(values)

        async def read(self, _size):
            return next(self.values, b"")

    class Process:
        returncode = None

        def __init__(self):
            self.stdout = Stream([b"[download] 12.5% of 1MiB\\n"])
            self.stderr = Stream([])

        async def wait(self):
            await asyncio.wait_for(progressed.wait(), timeout=1)
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = -9

    async def fake_exec(*_args, **_kwargs):
        return Process()

    async def progress(payload):
        assert payload == {"status": "downloading", "percent": 12.5}
        progressed.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    meta = MediaMeta(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "",
        None,
        "x",
        "",
        10,
        provider="youtube",
        source_id="dQw4w9WgXcQ",
    )
    with pytest.raises(RuntimeError, match="未找到有效音频"):
        await youtube.download(meta, tmp_path / "audio", on_progress=progress)


@pytest.mark.asyncio
async def test_run_kills_and_reaps_when_cancelled(monkeypatch):
    class Process:
        returncode = None
        killed = False

        class Stream:
            async def read(self, _size):
                raise asyncio.CancelledError

        stdout = Stream()
        stderr = Stream()

        async def wait(self):
            self.waited = True
            return -9

        def kill(self):
            self.killed = True

    process = Process()

    async def fake_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(asyncio.CancelledError):
        await youtube._run(["--version"])
    assert process.killed
    assert process.waited
