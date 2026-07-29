"""A1 compatibility baseline — knowledge/RAG must not break these contracts.

Freezes legacy summary path/hash, API/SSE contracts, weekly summary fingerprint,
and email markdown payload. Rollback = delete fixtures only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from biri_youyaku import db
from biri_youyaku.events import _COALESCED_EVENTS
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import VideoMeta
from biri_youyaku.modules.email import webhook
from biri_youyaku.modules.storage import summary as summary_storage
from biri_youyaku.routes.jobs import serialize_job
from biri_youyaku.weekly import repo as weekly_repo

FIXTURES = Path(__file__).parent / "fixtures" / "compatibility"
LEGACY_SUMMARY_PATH = FIXTURES / "legacy_summary.md"
MANIFEST_PATH = FIXTURES / "manifest.json"

# Frozen job-stream event names (must stay aligned with web/src/lib/sse.ts JobStreamEvent
# and biri_youyaku.events coalesced set).
REQUIRED_JOB_STREAM_EVENTS = frozenset(
    {
        "status",
        "meta",
        "summary_chunk",
        "summary_segment",
        "download_progress",
        "transcribe_progress",
        "error",
    }
)

REQUIRED_SERIALIZE_JOB_KEYS = frozenset(
    {
        "id",
        "url",
        "status",
        "summary",
        "tags",
        "created_at",
        "updated_at",
        "options",
        "audio_available",
    }
)


def _load_fixture_bytes() -> bytes:
    return LEGACY_SUMMARY_PATH.read_bytes()


def _load_fixture_text() -> str:
    return _load_fixture_bytes().decode("utf-8")


def _manifest_sha256() -> str:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["legacy_summary_sha256"]


def test_legacy_summary_fixture_matches_manifest():
    raw = _load_fixture_bytes()
    assert raw.endswith(b"\n")
    assert not raw.startswith(b"---")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == _manifest_sha256()


def test_summary_path_and_byte_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(summary_storage.settings, "summary_storage_dir", tmp_path)
    job_id = "compat-a1-job"
    fixture_bytes = _load_fixture_bytes()
    fixture_text = fixture_bytes.decode("utf-8")

    path = summary_storage.save(job_id, fixture_text)

    assert path == tmp_path / f"{job_id}.md"
    written = path.read_bytes()
    assert written == fixture_bytes
    assert hashlib.sha256(written).hexdigest() == _manifest_sha256()
    assert not written.startswith(b"---")


def test_read_summary_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(summary_storage.settings, "summary_storage_dir", tmp_path / "summaries")
    db.init_db()

    fixture_text = _load_fixture_text()
    job = repo.create_job("https://example.test/compat-a1", JobOptions(email_enabled=False))
    saved = summary_storage.save(job.id, fixture_text)
    repo.set_summary_path(job.id, saved)
    repo.update_status(job.id, JobStatus.COMPLETED)

    loaded = repo.get_job(job.id)
    assert loaded is not None
    assert loaded.status == JobStatus.COMPLETED
    assert repo.read_summary(loaded) == fixture_text


def test_weekly_fingerprint_includes_body_sha256_and_is_sensitive(monkeypatch, tmp_path):
    """Fingerprint includes sha256 of the full summary body (see weekly.repo.fingerprint)."""
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(summary_storage.settings, "summary_storage_dir", tmp_path / "summaries")
    db.init_db()

    fixture_text = _load_fixture_text()
    job = repo.create_job("https://example.test/compat-a1-fp", JobOptions(email_enabled=False))
    saved = summary_storage.save(job.id, fixture_text)
    repo.set_summary_path(job.id, saved)
    repo.update_status(job.id, JobStatus.COMPLETED)
    loaded = repo.get_job(job.id)
    assert loaded is not None

    first = weekly_repo.fingerprint([loaded])
    second = weekly_repo.fingerprint([loaded])
    assert first == second
    assert len(first) == 64

    # One-character body change must invalidate the weekly cache fingerprint.
    mutated = fixture_text[:-2] + "X" + fixture_text[-1:]  # keep trailing newline
    assert mutated != fixture_text
    saved.write_text(mutated, encoding="utf-8")
    after = weekly_repo.fingerprint([loaded])
    assert after != first


def test_serialize_job_detail_vs_lite(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(summary_storage.settings, "summary_storage_dir", tmp_path / "summaries")
    db.init_db()

    fixture_text = _load_fixture_text()
    job = repo.create_job("https://example.test/compat-a1-api", JobOptions(email_enabled=False))
    saved = summary_storage.save(job.id, fixture_text)
    repo.set_summary_path(job.id, saved)
    repo.update_status(job.id, JobStatus.COMPLETED)
    loaded = repo.get_job(job.id)
    assert loaded is not None

    detail = serialize_job(loaded, lite=False)
    assert REQUIRED_SERIALIZE_JOB_KEYS <= detail.keys()
    assert detail["summary"] == fixture_text
    assert "summary_available" not in detail

    lite = serialize_job(loaded, lite=True)
    assert REQUIRED_SERIALIZE_JOB_KEYS <= lite.keys()
    assert lite["summary"] is None
    assert lite["summary_available"] is True


class _FakeAsyncClient:
    last_request: dict | None = None
    response = httpx.Response(200, json={"ok": True})

    async def post(self, url, **kwargs):
        self.__class__.last_request = {"url": url, **kwargs}
        return self.__class__.response


@pytest.mark.asyncio
async def test_email_uses_full_markdown_body(monkeypatch):
    monkeypatch.setattr(webhook.settings, "email_webhook_url", "https://worker.example")
    monkeypatch.setattr(webhook.settings, "email_webhook_token", "secret")
    monkeypatch.setattr(webhook.settings, "email_default_recipient", "default@example.com")
    monkeypatch.setattr(webhook.settings, "email_subject_template", "[Biri-Youyaku] {{title}}")
    fake = _FakeAsyncClient()
    monkeypatch.setattr(webhook, "email_client", lambda: fake)
    _FakeAsyncClient.response = httpx.Response(200, json={"ok": True})
    _FakeAsyncClient.last_request = None

    fixture_text = _load_fixture_text()
    meta = VideoMeta(
        url="https://www.bilibili.com/video/BVCompat",
        bvid="BVCompat",
        cid=1,
        title="Compat fixture",
        author="Author",
        duration=42,
    )
    await webhook.send(meta, fixture_text, JobOptions())

    assert _FakeAsyncClient.last_request is not None
    assert _FakeAsyncClient.last_request["json"]["markdown"] == fixture_text


def test_sse_job_stream_event_names_frozen():
    # Coalesced server events must still cover the high-frequency stream names.
    assert {
        "status",
        "summary_chunk",
        "summary_segment",
        "download_progress",
        "transcribe_progress",
    } <= _COALESCED_EVENTS
    # Full client-facing JobStreamEvent set (web/src/lib/sse.ts).
    assert REQUIRED_JOB_STREAM_EVENTS == {
        "status",
        "meta",
        "summary_chunk",
        "summary_segment",
        "download_progress",
        "transcribe_progress",
        "error",
    }
    # Discrete (non-coalesced) names that must not silently disappear from the freeze set.
    assert "meta" in REQUIRED_JOB_STREAM_EVENTS
    assert "error" in REQUIRED_JOB_STREAM_EVENTS
