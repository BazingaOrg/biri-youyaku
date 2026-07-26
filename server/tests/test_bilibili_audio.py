import sys
from types import SimpleNamespace

from biri_youyaku.modules.bilibili import audio
from biri_youyaku.modules.bilibili.meta import VideoMeta


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


async def test_download_uses_canonical_url_for_untrusted_meta_url(monkeypatch, tmp_path):
    downloaded_urls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, urls):
            downloaded_urls.extend(urls)
            tmp_path.joinpath("audio.wav").touch()

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
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
