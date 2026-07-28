"""Persist provider-reported LLM usage without estimating money from tokens."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from biri_youyaku.config import settings
from biri_youyaku.db import connect

_MICROS = Decimal("1000000")


@dataclass(frozen=True)
class UsageContext:
    job_id: str | None
    operation: str
    provider: str
    key_fingerprint: str
    requested_model: str


def now_ms() -> int:
    return int(time.time() * 1000)


def key_fingerprint(api_key: str) -> str:
    """Stable, non-reversible per-deployment API key identifier.

    `USAGE_FINGERPRINT_SECRET` is preferred.  The fallback is derived from
    deployment secrets, so raw keys are never stored or exposed, but changing
    those settings changes future fingerprints; set the explicit secret before
    moving an existing installation between environments.
    """
    secret = settings.usage_fingerprint_secret
    if not secret:
        secret = hashlib.sha256(
            f"biri-youyaku usage fingerprint\0{settings.api_token}\0{settings.llm_api_key}".encode(
                "utf-8"
            )
        ).hexdigest()
    return hmac.new(secret.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def provider_for_base_url(base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        return "OpenRouter"
    if host == "api.deepseek.com" or host.endswith(".api.deepseek.com"):
        return "DeepSeek"
    if host == "api.moonshot.cn" or host.endswith(".api.moonshot.cn"):
        return "Moonshot"
    if host == "api.siliconflow.cn" or host.endswith(".api.siliconflow.cn"):
        return "SiliconFlow"
    return host or "Unknown"


def make_context(
    *, job_id: str | None, operation: str, base_url: str, api_key: str, model: str
) -> UsageContext:
    return UsageContext(
        job_id=job_id,
        operation=operation,
        provider=provider_for_base_url(base_url),
        key_fingerprint=key_fingerprint(api_key),
        requested_model=model,
    )


def _micros(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int((Decimal(str(value)) * _MICROS).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _value(usage: object, name: str) -> object:
    if isinstance(usage, dict):
        return usage.get(name)
    return getattr(usage, name, None)


def record_usage(
    context: UsageContext,
    usage: object,
    *,
    response_id: str | None = None,
    settled_model: str | None = None,
    request_id: str | None = None,
) -> None:
    """Record one successful request. Repeated provider event IDs are idempotent."""
    input_tokens = int(_value(usage, "input_tokens") or _value(usage, "prompt_tokens") or 0)
    output_tokens = int(_value(usage, "output_tokens") or _value(usage, "completion_tokens") or 0)
    total_tokens = int(_value(usage, "total_tokens") or input_tokens + output_tokens)
    details = _value(usage, "prompt_tokens_details")
    cached_tokens = int(_value(details, "cached_tokens") or _value(usage, "cached_tokens") or 0)
    cost = _value(usage, "cost")
    cost_micros = _micros(cost) if context.provider == "OpenRouter" else None
    status = (
        "confirmed"
        if cost_micros is not None
        else ("pending" if context.provider == "OpenRouter" else "not_supported")
    )
    currency = "USD" if cost_micros is not None else None
    # Provider IDs identify one billable event and can be reconciled later.
    # Without one, each successful request needs its own local id: NULL provider
    # IDs intentionally remain independent instead of collapsing unrelated calls.
    local_request_id = request_id or (
        f"provider:{context.provider}:{context.key_fingerprint}:{response_id}"
        if response_id
        else f"local:{uuid.uuid4()}"
    )
    values = (
        now_ms(),
        context.job_id,
        context.operation,
        context.provider,
        context.key_fingerprint,
        context.requested_model,
        settled_model,
        input_tokens,
        output_tokens,
        total_tokens,
        cached_tokens,
        local_request_id,
        response_id,
        cost_micros,
        currency,
        status,
    )
    with connect() as connection:
        if response_id is None:
            connection.execute(
                """
                INSERT INTO llm_usage_events (
              occurred_at, job_id, operation, provider, key_fingerprint, requested_model,
              settled_model, input_tokens, output_tokens, total_tokens, cached_tokens,
              request_id, provider_event_id, actual_cost_micros, currency, cost_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                  occurred_at=excluded.occurred_at, job_id=excluded.job_id, operation=excluded.operation,
                  requested_model=excluded.requested_model, settled_model=excluded.settled_model,
                  input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                  total_tokens=excluded.total_tokens, cached_tokens=excluded.cached_tokens,
                  actual_cost_micros=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN llm_usage_events.actual_cost_micros ELSE excluded.actual_cost_micros END,
                  currency=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN llm_usage_events.currency ELSE excluded.currency END,
                  cost_status=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN 'confirmed' ELSE excluded.cost_status END
                """,
                values,
            )
        else:
            connection.execute(
                """
                INSERT INTO llm_usage_events (
                  occurred_at, job_id, operation, provider, key_fingerprint, requested_model,
                  settled_model, input_tokens, output_tokens, total_tokens, cached_tokens,
                  request_id, provider_event_id, actual_cost_micros, currency, cost_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, key_fingerprint, provider_event_id) DO UPDATE SET
                  occurred_at=excluded.occurred_at, job_id=excluded.job_id, operation=excluded.operation,
                  requested_model=excluded.requested_model, settled_model=excluded.settled_model,
                  input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                  total_tokens=excluded.total_tokens, cached_tokens=excluded.cached_tokens,
                  request_id=excluded.request_id,
                  actual_cost_micros=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN llm_usage_events.actual_cost_micros ELSE excluded.actual_cost_micros END,
                  currency=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN llm_usage_events.currency ELSE excluded.currency END,
                  cost_status=CASE WHEN llm_usage_events.cost_status = 'confirmed'
                    THEN 'confirmed' ELSE excluded.cost_status END
                """,
                values,
            )


def record_balance_snapshot(
    *, provider: str, api_key: str, balance: object, currency: str, scope: str = "account_balance"
) -> None:
    amount = _micros(balance)
    if amount is None:
        return
    try:
        with connect() as connection:
            connection.execute(
                """INSERT INTO provider_balance_snapshots
                (observed_at, provider, key_fingerprint, balance_micros, currency, scope) VALUES (?, ?, ?, ?, ?, ?)""",
                (now_ms(), provider, key_fingerprint(api_key), amount, currency.upper(), scope),
            )
    except sqlite3.OperationalError:
        # 兼容应用启动前被单独调用的余额探测；正常 lifespan 会先 init_db。
        return


def _weekly_zone() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "weekly_summary_timezone", "Asia/Shanghai"))


def week_start_for_timestamp(timestamp_ms: int, *, zone: ZoneInfo | None = None) -> str:
    """Return the Monday date used by weekly summaries for one event timestamp."""
    local_date = datetime.fromtimestamp(timestamp_ms / 1000, tz=zone or _weekly_zone()).date()
    return (local_date - timedelta(days=local_date.weekday())).isoformat()


def cost_summary(*, now: datetime | None = None) -> dict:
    """Return exact historical costs and token counts for the costs screen."""
    zone = _weekly_zone()
    local_now = now.astimezone(zone) if now is not None else datetime.now(zone)
    current_week_start = (local_now.date() - timedelta(days=local_now.weekday())).isoformat()
    first_week_start = local_now.date() - timedelta(days=local_now.weekday(), weeks=11)
    first_week_ms = int(
        datetime.combine(first_week_start, datetime.min.time(), tzinfo=zone).timestamp() * 1000
    )
    with connect() as connection:
        started = connection.execute(
            "SELECT MIN(occurred_at) AS value FROM llm_usage_events"
        ).fetchone()["value"]
        event_totals = connection.execute(
            """SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens,
                      COALESCE(SUM(output_tokens), 0) AS output_tokens,
                      COALESCE(SUM(total_tokens), 0) AS total_tokens,
                      COALESCE(SUM(cost_status = 'confirmed'), 0) AS confirmed_requests,
                      COALESCE(SUM(cost_status = 'pending'), 0) AS pending_requests,
                      COALESCE(SUM(cost_status = 'not_supported'), 0) AS unsupported_requests
               FROM llm_usage_events"""
        ).fetchone()
        legacy_totals = connection.execute(
            """SELECT
                  COALESCE(SUM(CAST(json_extract(token_usage_json, '$.input_tokens') AS INTEGER)), 0) AS input_tokens,
                  COALESCE(SUM(CAST(json_extract(token_usage_json, '$.output_tokens') AS INTEGER)), 0) AS output_tokens,
                  COALESCE(SUM(CAST(json_extract(token_usage_json, '$.total_tokens') AS INTEGER)), 0) AS total_tokens
               FROM jobs
               WHERE token_usage_json IS NOT NULL AND json_valid(token_usage_json)
                 -- token_usage_json is the old summary-chain aggregate. Only a
                 -- summary event replaces it; a later tags event must add on.
                 AND NOT EXISTS (
                   SELECT 1 FROM llm_usage_events e
                   WHERE e.job_id = jobs.id AND e.operation = 'summary'
                 )"""
        ).fetchone()
        cost_rows = connection.execute(
            """SELECT currency, COALESCE(SUM(actual_cost_micros), 0) AS micros
               FROM llm_usage_events WHERE cost_status = 'confirmed' GROUP BY currency"""
        ).fetchall()
        by_operation = connection.execute(
            """SELECT operation, currency, COALESCE(SUM(actual_cost_micros), 0) AS micros,
                      COUNT(*) AS requests
               FROM llm_usage_events WHERE cost_status = 'confirmed'
               GROUP BY operation, currency ORDER BY micros DESC"""
        ).fetchall()
        latest_balances = connection.execute(
            """SELECT b.provider, b.balance_micros, b.currency, b.scope, b.observed_at
               FROM provider_balance_snapshots b
               JOIN (SELECT provider, key_fingerprint, scope, MAX(observed_at) AS observed_at
                     FROM provider_balance_snapshots GROUP BY provider, key_fingerprint, scope) latest
                 ON latest.provider = b.provider AND latest.key_fingerprint = b.key_fingerprint
                AND latest.scope = b.scope AND latest.observed_at = b.observed_at
               ORDER BY b.observed_at DESC"""
        ).fetchall()
        weekly_events = connection.execute(
            """SELECT occurred_at, currency, actual_cost_micros
               FROM llm_usage_events
               WHERE cost_status = 'confirmed' AND occurred_at >= ?
               ORDER BY occurred_at""",
            (first_week_ms,),
        ).fetchall()
    weekly_costs: dict[tuple[str, str], int] = {}
    for event in weekly_events:
        key = (week_start_for_timestamp(event["occurred_at"], zone=zone), event["currency"])
        weekly_costs[key] = weekly_costs.get(key, 0) + event["actual_cost_micros"]
    return {
        "tracking_started_at": started,
        "event_tracking_started_at": started,
        "timezone": str(zone),
        "current_week_start": current_week_start,
        "tokens": {
            **dict(event_totals),
            "legacy_input_tokens": legacy_totals["input_tokens"],
            "legacy_output_tokens": legacy_totals["output_tokens"],
            "legacy_total_tokens": legacy_totals["total_tokens"],
            "all_recorded_input_tokens": event_totals["input_tokens"]
            + legacy_totals["input_tokens"],
            "all_recorded_output_tokens": event_totals["output_tokens"]
            + legacy_totals["output_tokens"],
            "all_recorded_total_tokens": event_totals["total_tokens"]
            + legacy_totals["total_tokens"],
        },
        "confirmed_costs": [
            {"currency": row["currency"], "micros": row["micros"]} for row in cost_rows
        ],
        "by_operation": [dict(row) for row in by_operation],
        "balances": [dict(row) for row in latest_balances],
        "weekly": [
            {"week_start": week_start, "currency": currency, "micros": micros}
            for (week_start, currency), micros in sorted(weekly_costs.items())
        ],
    }
