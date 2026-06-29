import httpx
import pytest

from biri_youyaku.modules.llm import balance
from biri_youyaku.routes import config as config_route


@pytest.fixture(autouse=True)
def reset_balance_cache():
    balance._reset_for_tests()
    yield
    balance._reset_for_tests()


@pytest.mark.asyncio
async def test_deepseek_balance_is_normalized_and_cached(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url == "https://api.deepseek.com/user/balance"
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(
            200,
            json={
                "balance_infos": [
                    {"currency": "CNY", "total_balance": "12.30"},
                    {"currency": "CNY", "total_balance": "0.70"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs)
    )

    first = await balance.fetch_balance(
        base_url="https://api.deepseek.com/v1", api_key="secret-key"
    )
    second = await balance.fetch_balance(
        base_url="https://api.deepseek.com/v1", api_key="secret-key"
    )

    assert first == balance.Balance(provider="DeepSeek", balance=13.0, currency="CNY")
    assert second == first
    assert calls == 1


@pytest.mark.asyncio
async def test_unsupported_provider_returns_none():
    result = await balance.fetch_balance(base_url="https://api.openai.com/v1", api_key="secret-key")

    assert result is None


@pytest.mark.asyncio
async def test_balance_route_hides_unsupported(monkeypatch):
    monkeypatch.setattr(config_route.settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(config_route.settings, "llm_api_key", "secret-key")

    response = await config_route.get_llm_balance()

    assert response == {"ok": True, "supported": False}
