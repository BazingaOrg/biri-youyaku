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
async def test_zero_balance_is_reported_not_dropped(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"available_balance": 0}})

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs)
    )

    result = await balance.fetch_balance(
        base_url="https://api.moonshot.cn/v1", api_key="secret-key"
    )

    assert result == balance.Balance(provider="Moonshot", balance=0.0, currency="CNY")


@pytest.mark.asyncio
async def test_deepseek_usd_balance_keeps_its_currency(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balance_infos": [{"currency": "USD", "total_balance": "4.50"}]})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs))
    result = await balance.fetch_balance(base_url="https://api.deepseek.com/v1", api_key="secret-key")

    assert result == balance.Balance(provider="DeepSeek", balance=4.5, currency="USD")


@pytest.mark.asyncio
async def test_transient_failure_is_not_cached(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"balance_infos": [{"currency": "CNY", "total_balance": "5"}]})

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs)
    )

    first = await balance.fetch_balance(base_url="https://api.deepseek.com/v1", api_key="secret-key")
    second = await balance.fetch_balance(base_url="https://api.deepseek.com/v1", api_key="secret-key")

    assert first is None
    assert second == balance.Balance(provider="DeepSeek", balance=5.0, currency="CNY")
    assert calls == 2


@pytest.mark.asyncio
async def test_unsupported_provider_returns_none():
    result = await balance.fetch_balance(base_url="https://api.openai.com/v1", api_key="secret-key")

    assert result is None


@pytest.mark.asyncio
async def test_openrouter_regular_key_reads_key_limit(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openrouter.ai/api/v1/key"
        assert request.headers["authorization"] == "Bearer inference-key"
        return httpx.Response(200, json={"data": {"limit_remaining": "3.25"}})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs))
    result = await balance.fetch_balance(base_url="https://openrouter.ai/api/v1", api_key="inference-key")

    assert result == balance.Balance(provider="OpenRouter", balance=3.25, currency="USD", scope="key_limit")


@pytest.mark.asyncio
async def test_openrouter_management_key_reads_account_credits(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openrouter.ai/api/v1/credits"
        assert request.headers["authorization"] == "Bearer management-key"
        return httpx.Response(200, json={"data": {"total_credits": 10, "total_usage": 1.5}})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(balance.httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs))
    result = await balance.fetch_balance(base_url="https://openrouter.ai/api/v1", api_key="inference-key", openrouter_management_api_key="management-key")

    assert result == balance.Balance(provider="OpenRouter", balance=8.5, currency="USD", scope="account_credits")


@pytest.mark.asyncio
async def test_balance_route_hides_unsupported(monkeypatch):
    monkeypatch.setattr(config_route.settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(config_route.settings, "llm_api_key", "secret-key")

    response = await config_route.get_llm_balance()

    assert response == {"ok": True, "supported": False}
