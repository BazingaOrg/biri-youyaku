import logging

from biri_youyaku.modules import _http


def test_bili_client_ignores_proxy_environment_without_socksio(monkeypatch):
    """B 站 client 不应因宿主 SOCKS 代理环境而无法初始化。"""
    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("all_proxy", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "socks5://127.0.0.1:1080")

    captured_kwargs = {}
    fake_client = type("FakeAsyncClient", (), {"is_closed": False})()

    def create_client(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_client

    monkeypatch.setattr(_http.httpx, "AsyncClient", create_client)
    _http._reset_for_tests()
    try:
        client = _http.bili_client()

        assert client is fake_client
        assert captured_kwargs["trust_env"] is False
    finally:
        _http._reset_for_tests()


async def test_aclose_all_logs_openai_close_failure_without_api_key(caplog):
    secret = "super-secret-api-key"

    class FailingClient:
        async def close(self):
            raise RuntimeError("close failed")

    _http._reset_for_tests()
    _http._openai_clients[(secret, "https://api.example/v1", 12.5, 3)] = FailingClient()
    with caplog.at_level(logging.ERROR, logger=_http.__name__):
        await _http.aclose_all()

    assert secret not in caplog.text
    assert "provider=openai" in caplog.text
    assert "base_url=https://api.example/v1" in caplog.text
    assert "timeout=12.5" in caplog.text
