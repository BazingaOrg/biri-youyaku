from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import urlparse

import httpx

from biri_youyaku.modules.llm.usage import key_fingerprint, record_balance_snapshot


@dataclass(frozen=True)
class Balance:
    provider: str
    balance: float
    currency: str
    # key_limit is a key-level spending limit, not an account balance.
    scope: str = "account_balance"


@dataclass
class _CacheEntry:
    value: Balance | None
    expires_at: float


_TTL_SECONDS = 300
_CACHE: dict[tuple[str, str], _CacheEntry] = {}


def _host_of(base_url: str) -> str:
    return (urlparse(base_url).hostname or "").lower()


def _provider_for_host(host: str) -> str | None:
    if host == "api.deepseek.com" or host.endswith(".api.deepseek.com"):
        return "DeepSeek"
    if host == "api.moonshot.cn" or host.endswith(".api.moonshot.cn"):
        return "Moonshot"
    if host == "api.siliconflow.cn" or host.endswith(".api.siliconflow.cn"):
        return "SiliconFlow"
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        return "OpenRouter"
    return None


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_amount(data: dict, *keys: str) -> float | None:
    # 取第一个「存在且可解析」的字段——不能用 `a or b`，否则真实余额 0 会被当 falsy 跳过
    # （余额恰好为 0 正是用户最该看到的状态）。
    for key in keys:
        if key in data:
            amount = _safe_float(data[key])
            if amount is not None:
                return amount
    return None


def _deepseek_balance(payload: dict) -> Balance | None:
    infos = payload.get("balance_infos")
    if not isinstance(infos, list):
        return None
    # A scalar balance cannot safely add CNY and USD. Select the first valid
    # currency and sum only entries in that same currency.
    selected_currency: str | None = None
    total = 0.0
    for item in infos:
        if not isinstance(item, dict):
            continue
        currency = str(item.get("currency") or "CNY").upper()
        amount = _safe_float(item.get("total_balance"))
        if amount is None:
            continue
        if selected_currency is None:
            selected_currency = currency
        if currency == selected_currency:
            total += amount
    return Balance(provider="DeepSeek", balance=total, currency=selected_currency) if selected_currency else None


def _moonshot_balance(payload: dict) -> Balance | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    amount = _first_amount(data, "available_balance", "balance")
    return (
        Balance(provider="Moonshot", balance=amount, currency="CNY") if amount is not None else None
    )


def _siliconflow_balance(payload: dict) -> Balance | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    amount = _first_amount(data, "balance", "totalBalance", "chargeBalance")
    return (
        Balance(provider="SiliconFlow", balance=amount, currency="CNY")
        if amount is not None
        else None
    )


def _openrouter_credits(payload: dict) -> Balance | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    total = _safe_float(data.get("total_credits"))
    usage = _safe_float(data.get("total_usage")) or 0.0
    if total is None:
        return None
    return Balance(provider="OpenRouter", balance=max(total - usage, 0.0), currency="USD", scope="account_credits")


def _openrouter_key_limit(payload: dict) -> Balance | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    remaining = _safe_float(data.get("limit_remaining"))
    return Balance(provider="OpenRouter", balance=remaining, currency="USD", scope="key_limit") if remaining is not None else None


async def fetch_balance(
    *, base_url: str, api_key: str, force_refresh: bool = False, openrouter_management_api_key: str = ""
) -> Balance | None:
    if not api_key:
        return None
    host = _host_of(base_url)
    provider = _provider_for_host(host)
    if provider is None:
        return None

    # A management key intentionally switches the OpenRouter endpoint and cache
    # identity: it represents account credits, whereas a normal key exposes only
    # its own remaining limit.
    lookup_key = openrouter_management_api_key if provider == "OpenRouter" and openrouter_management_api_key else api_key
    cache_key = (provider, key_fingerprint(lookup_key))
    now = time.monotonic()
    if not force_refresh:
        entry = _CACHE.get(cache_key)
        if entry is not None and entry.expires_at > now:
            return entry.value

    if provider == "DeepSeek":
        url = "https://api.deepseek.com/user/balance"
        parser = _deepseek_balance
    elif provider == "Moonshot":
        url = "https://api.moonshot.cn/v1/users/me/balance"
        parser = _moonshot_balance
    elif provider == "SiliconFlow":
        url = "https://api.siliconflow.cn/v1/user/info"
        parser = _siliconflow_balance
    else:
        if openrouter_management_api_key:
            url = "https://openrouter.ai/api/v1/credits"
            parser = _openrouter_credits
        else:
            url = "https://openrouter.ai/api/v1/key"
            parser = _openrouter_key_limit

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {lookup_key}"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        value = None
    else:
        value = parser(payload) if isinstance(payload, dict) else None

    # 只缓存成功结果：临时失败（网络抖动 / 401）不写缓存，否则会把余额卡隐藏整整 5 分钟，
    # 下次进统计页也不会重试。失败就让下次打开重新探测。
    if value is not None:
        _CACHE[cache_key] = _CacheEntry(value=value, expires_at=now + _TTL_SECONDS)
        record_balance_snapshot(
            provider=value.provider, api_key=lookup_key, balance=value.balance, currency=value.currency, scope=value.scope
        )
    return value


def _reset_for_tests() -> None:
    _CACHE.clear()
