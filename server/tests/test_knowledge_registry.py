"""A3 knowledge registry: register, reconcile, unlink on history delete."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import (
    reconcile_once,
    try_register_job,
    unlink_job,
)
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.model import (
    ARTIFACT_KIND_SUMMARY,
    ARTIFACT_KIND_TRANSCRIPT_RAW,
    RECONCILE_FAILED,
    RECONCILE_REGISTERED,
    RECONCILE_SKIPPED,
)
from biri_youyaku.modules.transcript import TranscriptItem
from biri_youyaku.routes import jobs as jobs_route


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    db.init_db()
    return knowledge_dir


def _make_completed_job(
    *,
    bvid: str = "BV1xx411c7mD",
    cid: int | None = 12345,
    title: str = "Test video",
    author: str = "Author",
    mid: int | None = 42,
    task_type: str = "summary",
    summary_body: str = "# summary\nhello\n",
    transcript: list[dict] | None = None,
    subtitle_source: str = "platform",
    url: str | None = None,
) -> tuple[object, Path]:
    job = jobs_repo.create_job(
        url or f"https://www.bilibili.com/video/{bvid}",
        JobOptions(task_type=task_type, email_enabled=False),
    )
    jobs_repo.update_meta(
        job.id,
        bvid=bvid,
        cid=cid,
        title=title,
        author=author,
        duration=12.0,
        mid=mid,
    )
    items = transcript or [
        {"start": 0.0, "end": 1.2, "text": "hello"},
        {"start": 1.2, "end": 2.5, "text": "world"},
    ]
    jobs_repo.set_transcript(
        job.id,
        [TranscriptItem(start=i["start"], end=i["end"], text=i["text"]) for i in items],
    )
    jobs_repo.set_subtitle_source(job.id, subtitle_source)
    summary_dir = Path(settings.summary_storage_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{job.id}.md"
    summary_path.write_bytes(summary_body.encode("utf-8"))
    jobs_repo.set_summary_path(job.id, summary_path)
    jobs_repo.update_status(job.id, JobStatus.COMPLETED)
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET completed_at = ? WHERE id = ?",
            (now_ms(), job.id),
        )
    return jobs_repo.get_job(job.id), summary_path


def test_register_happy_path(monkeypatch, tmp_path):
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job, summary_path = _make_completed_job()
    legacy_bytes = summary_path.read_bytes()

    status = try_register_job(job.id)
    assert status == RECONCILE_REGISTERED

    assert knowledge_repo.count_documents() == 1
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None
    assert knowledge_repo.count_artifacts(document_id=doc_id) == 2
    assert knowledge_repo.count_content_revisions(doc_id) == 1
    assert knowledge_repo.count_summary_revisions(doc_id) == 1
    assert knowledge_repo.count_summary_revisions(doc_id, active_only=True) == 1

    link = knowledge_repo.get_job_link(job.id)
    assert link is not None
    assert link.unlinked_at is None
    assert link.document_id == doc_id

    rec = knowledge_repo.get_reconcile(job.id)
    assert rec is not None
    assert rec.status == RECONCILE_REGISTERED

    # Legacy summary still present and byte-identical.
    assert summary_path.is_file()
    assert summary_path.read_bytes() == legacy_bytes

    # Knowledge summary artifact matches legacy bytes + hash.
    summary_hash = hashlib.sha256(legacy_bytes).hexdigest()
    art_path = art.summary_artifact_path(doc_id, summary_hash)
    assert art_path.is_file()
    assert art_path.read_bytes() == legacy_bytes
    assert art_path.is_relative_to(knowledge_dir) or str(art_path).startswith(str(knowledge_dir))


def test_register_idempotent(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job, _ = _make_completed_job()
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    assert knowledge_repo.count_documents() == 1
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert knowledge_repo.count_artifacts(document_id=doc_id) == 2
    assert knowledge_repo.count_summary_revisions(doc_id) == 1
    assert knowledge_repo.count_content_revisions(doc_id) == 1


def test_missing_cid_fails_no_document(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job, _ = _make_completed_job(cid=None)
    status = try_register_job(job.id)
    assert status == RECONCILE_FAILED
    rec = knowledge_repo.get_reconcile(job.id)
    assert rec is not None
    assert rec.reason == "missing_bvid_or_cid"
    assert knowledge_repo.count_documents() == 0


def test_skip_distill_and_audio(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    distill_job, _ = _make_completed_job(task_type="distill", bvid="BV1distill001")
    audio_job, _ = _make_completed_job(task_type="audio", bvid="BV1audio00001", cid=99)
    assert try_register_job(distill_job.id) == RECONCILE_SKIPPED
    assert try_register_job(audio_job.id) == RECONCILE_SKIPPED
    assert knowledge_repo.get_reconcile(distill_job.id).reason == "task_type_distill"
    assert knowledge_repo.get_reconcile(audio_job.id).reason == "task_type_audio"
    assert knowledge_repo.count_documents() == 0


def test_resummary_same_transcript_two_summary_revisions(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    shared_transcript = [
        {"start": 0.0, "end": 1.0, "text": "same"},
        {"start": 1.0, "end": 2.0, "text": "lines"},
    ]
    job1, _ = _make_completed_job(
        bvid="BV1same000001",
        cid=7,
        summary_body="# v1\nfirst\n",
        transcript=shared_transcript,
    )
    job2, _ = _make_completed_job(
        bvid="BV1same000001",
        cid=7,
        summary_body="# v2\nsecond body longer\n",
        transcript=shared_transcript,
    )
    assert try_register_job(job1.id) == RECONCILE_REGISTERED
    assert try_register_job(job2.id) == RECONCILE_REGISTERED

    assert knowledge_repo.count_documents() == 1
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid="BV1same000001", external_cid=7
    )
    assert knowledge_repo.count_content_revisions(doc_id) == 1
    assert knowledge_repo.count_summary_revisions(doc_id) == 2
    assert knowledge_repo.count_summary_revisions(doc_id, active_only=True) == 1
    # Two summary artifacts (different hashes), one transcript artifact.
    assert (
        knowledge_repo.count_artifacts(document_id=doc_id, kind=ARTIFACT_KIND_SUMMARY) == 2
    )
    assert (
        knowledge_repo.count_artifacts(
            document_id=doc_id, kind=ARTIFACT_KIND_TRANSCRIPT_RAW
        )
        == 1
    )


@pytest.mark.asyncio
async def test_unlink_on_single_delete(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job, summary_path = _make_completed_job()
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    artifact_paths = [
        art.resolve_stored_path(p) for p in knowledge_repo.list_artifact_paths(doc_id)
    ]
    assert artifact_paths
    assert all(p.is_file() for p in artifact_paths)

    result = await jobs_route.delete(job.id)
    assert result["ok"] is True
    assert jobs_repo.get_job(job.id) is None
    assert not summary_path.exists()

    link = knowledge_repo.get_job_link(job.id)
    assert link is not None
    assert link.unlinked_at is not None
    assert knowledge_repo.count_documents() == 1
    assert all(p.is_file() for p in artifact_paths)


@pytest.mark.asyncio
async def test_unlink_on_bulk_delete(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job, summary_path = _make_completed_job(
        bvid="BV1bulk000001", cid=88, author="BulkAuthor", title="Bulk one"
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid="BV1bulk000001", external_cid=88
    )
    artifact_paths = [
        art.resolve_stored_path(p) for p in knowledge_repo.list_artifact_paths(doc_id)
    ]

    preview = await jobs_route.preview_bulk_delete(
        jobs_route.BulkDeleteFilterPayload(author="BulkAuthor")
    )
    result = await jobs_route.execute_bulk_delete(
        jobs_route.BulkDeleteExecutePayload(preview_token=preview["preview_token"])
    )
    assert result["deleted_count"] == 1
    assert jobs_repo.get_job(job.id) is None
    assert not summary_path.exists()

    link = knowledge_repo.get_job_link(job.id)
    assert link is not None
    assert link.unlinked_at is not None
    assert all(p.is_file() for p in artifact_paths)
    assert knowledge_repo.count_documents() == 1


def test_register_disabled(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "knowledge_register_enabled", False)
    job, _ = _make_completed_job(bvid="BV1disabled01")
    assert try_register_job(job.id) == RECONCILE_SKIPPED
    assert knowledge_repo.count_documents() == 0
    assert knowledge_repo.get_reconcile(job.id) is None
    assert knowledge_repo.get_job_link(job.id) is None
    counts = reconcile_once(limit=10)
    assert counts["attempted"] == 0
    assert knowledge_repo.count_documents() == 0


def test_reconcile_once_registers_historical(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job, _ = _make_completed_job(bvid="BV1hist000001", cid=3)
    counts = reconcile_once(limit=50)
    assert counts["registered"] >= 1
    assert knowledge_repo.get_reconcile(job.id).status == RECONCILE_REGISTERED


def test_unlink_noop_without_link(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    # Should not raise when no knowledge row exists.
    unlink_job("nonexistent-job-id")
