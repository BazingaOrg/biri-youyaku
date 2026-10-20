import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from biri_youyaku.modules.bilibili import audio
from biri_youyaku.modules.bilibili.meta import VideoMeta


def _video_meta() -> VideoMeta:
    return VideoMeta(
        url="https://www.bilibili.com/video/BV1xx?p=2",
        bvid="BV1xx",
        cid=None,
        title="title",
        author="author",
        duration=0,
    )


def test_write_cookie_file_uses_netscape_cookie_format(monkeypatch):
    monkeypatch.setattr(audio.settings, "bili_sessdata", "sess")
    monkeypatch.setattr(audio.settings, "bili_buvid3", "buvid")
    monkeypatch.setattr(audio.settings, "bili_bili_jct", "jct")

    path = audio._write_cookie_file()
    assert path is not None
    try:
        content = path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)

    assert "# Netscape HTTP Cookie File" in content
    assert ".bilibili.com\tTRUE\t/\tFALSE\t2147483647\tSESSDATA\tsess" in content
    assert ".bilibili.com\tTRUE\t/\tFALSE\t2147483647\tbuvid3\tbuvid" in content
    assert ".bilibili.com\tTRUE\t/\tFALSE\t2147483647\tbili_jct\tjct" in content


def test_format_download_error_mentions_cookie_hint():
    message = audio._format_download_error("ERROR: No video formats found!", has_cookies=False)

    assert "No video formats found" in message
    assert "配置 BILI_SESSDATA" in message


def test_progress_payload_calculates_percent_from_estimated_total():
    payload = audio._progress_payload(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes_estimate": 200,
            "speed": 10,
            "eta": 15,
        }
    )

    assert payload == {
        "status": "downloading",
        "downloaded_bytes": 50,
        "total_bytes": 200,
        "percent": 25.0,
        "speed": 10,
        "eta": 15,
    }


async def test_prepare_cookie_values_merges_warmed_bilibili_jar(monkeypatch):
    async def fake_prime():
        return None

    jar = SimpleNamespace(
        jar=[
            SimpleNamespace(domain=".bilibili.com", name="buvid4", value="warm-buvid4"),
            SimpleNamespace(domain="example.com", name="ignored", value="ignored"),
        ]
    )
    monkeypatch.setattr(audio.settings, "bili_sessdata", "sess")
    monkeypatch.setattr(audio.settings, "bili_buvid3", "configured-buvid3")
    monkeypatch.setattr(audio.settings, "bili_bili_jct", "jct")
    monkeypatch.setattr(audio._guard, "prime_cookies", fake_prime)
    monkeypatch.setattr(audio, "bili_client", lambda: SimpleNamespace(cookies=jar))

    values = await audio._prepare_cookie_values()

    assert values == {
        "SESSDATA": "sess",
        "buvid3": "configured-buvid3",
        "bili_jct": "jct",
        "buvid4": "warm-buvid4",
    }


async def test_download_uses_canonical_url_for_untrusted_meta_url(monkeypatch, tmp_path):
    downloaded_urls = []
    captured_options = []

    async def fake_prepare_cookie_values(*, refresh_buvid=False):
        assert refresh_buvid is False
        return {}

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            captured_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            downloaded_urls.extend(urls)
            tmp_path.joinpath("audio.wav").touch()

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(audio, "_prepare_cookie_values", fake_prepare_cookie_values)
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(name, "socks5://127.0.0.1:7897")
    meta = VideoMeta(
        url="http://127.0.0.1:8000/video/BV1xx?p=2",
        bvid="BV1xx",
        cid=None,
        title="title",
        author="author",
        duration=0,
    )

    await audio.download(meta, tmp_path / "audio.wav")

    assert downloaded_urls == ["https://www.bilibili.com/video/BV1xx?p=2"]
    assert captured_options[0]["proxy"] == ""
    assert captured_options[0]["sleep_interval_requests"] == 0.75
    assert "http_headers" not in captured_options[0]


async def test_download_retries_412_once_with_refreshed_cookie(monkeypatch, tmp_path):
    attempts = []
    refreshes = []
    sleeps = []
    cookie_paths = []

    class FakeHttpError(RuntimeError):
        status = 412

    async def fake_prepare_cookie_values(*, refresh_buvid=False):
        refreshes.append(refresh_buvid)
        return {"buvid3": f"attempt-{len(refreshes)}"}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            attempts.append(urls)
            cookie_paths.append(self.options["cookiefile"])
            assert Path(self.options["cookiefile"]).is_file()
            if len(attempts) == 1:
                raise FakeHttpError("blocked")
            tmp_path.joinpath("audio.wav").touch()

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(audio, "_prepare_cookie_values", fake_prepare_cookie_values)
    monkeypatch.setattr(audio.asyncio, "sleep", fake_sleep)

    result = await audio.download(_video_meta(), tmp_path / "audio.wav")

    assert result == tmp_path / "audio.wav"
    assert len(attempts) == 2
    assert refreshes == [False, True]
    assert sleeps == [audio._RATE_LIMIT_RETRY_DELAY_SECONDS]
    assert all(not Path(path).exists() for path in cookie_paths)


async def test_download_stops_after_second_412(monkeypatch, tmp_path):
    attempts = []

    class FakeHttpError(RuntimeError):
        status = 412

    async def fake_prepare_cookie_values(*, refresh_buvid=False):
        return {}

    async def fake_sleep(_seconds):
        return None

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            attempts.append(urls)
            raise FakeHttpError("blocked")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(audio, "_prepare_cookie_values", fake_prepare_cookie_values)
    monkeypatch.setattr(audio.asyncio, "sleep", fake_sleep)

    with pytest.raises(audio.BiliRateLimitedError) as error:
        await audio.download(_video_meta(), tmp_path / "audio.wav")

    assert error.value.error_code == "BILI_RATE_LIMITED"
    assert "10–30 分钟" in str(error.value)
    assert len(attempts) == 2


async def test_download_does_not_retry_permanent_http_error(monkeypatch, tmp_path):
    attempts = []
    refreshes = []

    class FakeHttpError(RuntimeError):
        status = 403

    async def fake_prepare_cookie_values(*, refresh_buvid=False):
        refreshes.append(refresh_buvid)
        return {}

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            attempts.append(urls)
            raise FakeHttpError("forbidden")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(audio, "_prepare_cookie_values", fake_prepare_cookie_values)

    with pytest.raises(RuntimeError, match="forbidden"):
        await audio.download(_video_meta(), tmp_path / "audio.wav")

    assert len(attempts) == 1
    assert refreshes == [False]
