from biri_youyaku.modules.bilibili import audio


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
