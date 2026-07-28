from datetime import datetime, timezone

from biri_youyaku import db
from biri_youyaku.modules.llm import usage


def _init_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "usage.db")
    db.init_db()


def test_openrouter_cost_is_exact_and_idempotent(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    context = usage.make_context(
        job_id="job-1",
        operation="summary",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
        model="openai/gpt-4o-mini",
    )
    response_usage = {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
        "cost": "0.0001234",
    }
    usage.record_usage(
        context, response_usage, response_id="request-1", settled_model="provider/model"
    )
    usage.record_usage(
        context, response_usage, response_id="request-1", settled_model="provider/model"
    )

    result = usage.cost_summary()

    assert result["tokens"]["total_tokens"] == 15
    assert result["tokens"]["confirmed_requests"] == 1
    assert result["confirmed_costs"] == [{"currency": "USD", "micros": 123}]
    assert result["by_operation"][0]["operation"] == "summary"


def test_provider_event_can_upgrade_pending_to_confirmed(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    context = usage.make_context(
        job_id="job-1",
        operation="summary",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
        model="model",
    )
    usage.record_usage(
        context, {"prompt_tokens": 3, "completion_tokens": 1}, response_id="request-1"
    )
    usage.record_usage(
        context,
        {"prompt_tokens": 3, "completion_tokens": 1, "cost": "0.000010"},
        response_id="request-1",
    )

    result = usage.cost_summary()

    assert result["tokens"]["total_tokens"] == 4
    assert result["tokens"]["pending_requests"] == 0
    assert result["tokens"]["confirmed_requests"] == 1
    assert result["confirmed_costs"] == [{"currency": "USD", "micros": 10}]


def test_confirmed_provider_event_never_downgrades_to_pending(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    context = usage.make_context(
        job_id="job-1",
        operation="summary",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
        model="model",
    )
    usage.record_usage(
        context,
        {"prompt_tokens": 3, "completion_tokens": 1, "cost": "0.000010"},
        response_id="request-1",
    )
    usage.record_usage(
        context, {"prompt_tokens": 3, "completion_tokens": 1}, response_id="request-1"
    )

    result = usage.cost_summary()

    assert result["tokens"]["confirmed_requests"] == 1
    assert result["tokens"]["pending_requests"] == 0
    assert result["confirmed_costs"] == [{"currency": "USD", "micros": 10}]


def test_all_recorded_tokens_include_only_legacy_jobs_without_events(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    with db.connect() as connection:
        connection.executemany(
            """INSERT INTO jobs (id, url, status, options_json, created_at, updated_at, token_usage_json)
               VALUES (?, 'https://example.test', 'COMPLETED', '{}', 1, 1, ?)""",
            [
                ("legacy", '{"input_tokens": 9, "output_tokens": 2, "total_tokens": 11}'),
                ("new", '{"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}'),
            ],
        )
    context = usage.make_context(
        job_id="new",
        operation="summary",
        base_url="https://api.deepseek.com/v1",
        api_key="secret-key",
        model="model",
    )
    usage.record_usage(context, {"prompt_tokens": 7, "completion_tokens": 3}, request_id="one-call")

    tokens = usage.cost_summary()["tokens"]

    assert tokens["legacy_total_tokens"] == 11
    assert tokens["total_tokens"] == 10
    assert tokens["all_recorded_total_tokens"] == 21
    assert tokens["all_recorded_input_tokens"] == 16
    assert tokens["all_recorded_output_tokens"] == 5


def test_legacy_summary_tokens_survive_later_tag_event(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO jobs (id, url, status, options_json, created_at, updated_at, token_usage_json)
               VALUES ('legacy', 'https://example.test', 'COMPLETED', '{}', 1, 1,
                       '{"input_tokens": 9, "output_tokens": 2, "total_tokens": 11}')"""
        )
    context = usage.make_context(
        job_id="legacy",
        operation="tags",
        base_url="https://api.deepseek.com/v1",
        api_key="secret-key",
        model="model",
    )
    usage.record_usage(
        context, {"prompt_tokens": 2, "completion_tokens": 1}, request_id="tags-call"
    )

    tokens = usage.cost_summary()["tokens"]

    assert tokens["legacy_total_tokens"] == 11
    assert tokens["total_tokens"] == 3
    assert tokens["all_recorded_total_tokens"] == 14


def test_fingerprint_is_hmac_stable_and_never_raw_key(monkeypatch):
    monkeypatch.setattr(usage.settings, "usage_fingerprint_secret", "test-secret")
    first = usage.key_fingerprint("secret-key")
    assert first == usage.key_fingerprint("secret-key")
    assert first != "secret-key"
    assert len(first) == 64


def test_other_provider_never_estimates_cost(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    context = usage.make_context(
        job_id=None,
        operation="tags",
        base_url="https://api.deepseek.com/v1",
        api_key="secret-key",
        model="deepseek-v4-flash",
    )
    usage.record_usage(context, {"prompt_tokens": 2, "completion_tokens": 1, "cost": "99"})

    result = usage.cost_summary()

    assert result["tokens"]["total_tokens"] == 3
    assert result["tokens"]["unsupported_requests"] == 1
    assert result["confirmed_costs"] == []


def test_balance_snapshot_is_stored_as_micros(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    usage.record_balance_snapshot(
        provider="DeepSeek", api_key="secret-key", balance="12.30", currency="CNY"
    )

    assert usage.cost_summary()["balances"][0]["balance_micros"] == 12_300_000


def test_weekly_costs_use_shanghai_monday_boundary(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    monkeypatch.setattr(usage.settings, "weekly_summary_timezone", "Asia/Shanghai")
    # 2026-07-26 15:59 UTC is Sunday 23:59 in Shanghai; one minute later is Monday.
    before_boundary = int(datetime(2026, 7, 26, 15, 59, tzinfo=timezone.utc).timestamp() * 1000)
    after_boundary = int(datetime(2026, 7, 26, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)
    with db.connect() as connection:
        connection.executemany(
            """INSERT INTO llm_usage_events (
                occurred_at, operation, provider, key_fingerprint, input_tokens, output_tokens,
                total_tokens, cached_tokens, request_id, actual_cost_micros, currency, cost_status
            ) VALUES (?, 'summary', 'OpenRouter', 'fingerprint', 1, 1, 2, 0, ?, 10, 'USD', 'confirmed')""",
            [(before_boundary, "before"), (after_boundary, "after")],
        )

    result = usage.cost_summary(now=datetime(2026, 7, 28, tzinfo=timezone.utc))

    assert result["timezone"] == "Asia/Shanghai"
    assert result["current_week_start"] == "2026-07-27"
    assert result["weekly"] == [
        {"week_start": "2026-07-20", "currency": "USD", "micros": 10},
        {"week_start": "2026-07-27", "currency": "USD", "micros": 10},
    ]
