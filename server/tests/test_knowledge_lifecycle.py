"""Phase D: document soft-delete / restore / purge / audit / backup."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import cleanup
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.knowledge import try_register_job
from biri_youyaku.knowledge.backup import create_backup
from biri_youyaku.knowledge.lifecycle import (
    list_audit_events,
    purge_permanent,
    restore,
    soft_delete,
)
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.model import RECONCILE_REGISTERED
from biri_youyaku.knowledge.search import search_summaries
from biri_youyaku.modules.transcript import TranscriptItem


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "knowledge_search_enabled", True)
    monkeypatch.setattr(settings, "knowledge_transcript_index_enabled", True)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    monkeypatch.setattr(settings, "knowledge_backup_dir", tmp_path / "backups")
    monkeypatch.setattr(cleanup, "KNOWLEDGE_SOFT_DELETE_DAYS", 30)
    monkeypatch.setattr(settings, "api_token", "")
    db.init_db()
    return knowledge_dir


def _make_completed_job(
    *,
    bvid: str = "BV1xx411c7mD",
    cid: int = 12345,
    title: str = "Lifecycle Test Video",
    author: str = "Author",
    summary_body: str = "## 概述\n这是生命周期测试内容关键字\n",
) -> object:
    job = jobs_repo.create_job(
        f"https://www.bilibili.com/video/{bvid}",
        JobOptions(task_type="summary", email_enabled=False),
    )
    jobs_repo.update_meta(
        job.id,
        bvid=bvid,
        cid=cid,
        title=title,
        author=author,
        duration=12.0,
        mid=1,
    )
    jobs_repo.set_transcript(
        job.id,
        [TranscriptItem(start=0.0, end=1.0, text="hello lifecycle")],
    )
    jobs_repo.set_subtitle_source(job.id, "platform")
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
    return jobs_repo.get_job(job.id)


def _register_doc(monkeypatch, tmp_path: Path) -> tuple[str, object, Path]:
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job = _make_completed_job()
    status = try_register_job(job.id)
    assert status == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None
    return doc_id, job, knowledge_dir


def test_soft_delete_hides_from_search(monkeypatch, tmp_path):
    doc_id, _job, _kdir = _register_doc(monkeypatch, tmp_path)
    hits = search_summaries("生命周期测试", limit=10)
    assert any(h.document_id == doc_id for h in hits)

    soft_delete(doc_id, actor="api")
    hits_after = search_summaries("生命周期测试", limit=10)
    assert all(h.document_id != doc_id for h in hits_after)
    assert knowledge_repo.count_documents() == 0
    assert knowledge_repo.count_documents(include_deleted=True) == 1
    assert knowledge_repo.count_deleted_documents() == 1


def test_restore_returns_to_search(monkeypatch, tmp_path):
    doc_id, _job, _kdir = _register_doc(monkeypatch, tmp_path)
    soft_delete(doc_id)
    assert search_summaries("生命周期测试", limit=10) == []

    restore(doc_id)
    hits = search_summaries("生命周期测试", limit=10)
    assert any(h.document_id == doc_id for h in hits)
    assert knowledge_repo.count_documents() == 1
    assert knowledge_repo.count_deleted_documents() == 0


def test_purge_requires_confirm_and_removes_artifacts(monkeypatch, tmp_path):
    doc_id, job, knowledge_dir = _register_doc(monkeypatch, tmp_path)
    doc_dir = art.document_dir(doc_id)
    assert doc_dir.is_dir()
    paths_before = knowledge_repo.list_artifact_paths(doc_id)
    assert paths_before
    for path in paths_before:
        assert art.resolve_stored_path(path).is_file()

    from biri_youyaku.knowledge.lifecycle import LifecycleError

    with pytest.raises(LifecycleError) as exc_info:
        purge_permanent(doc_id, confirm_title="wrong-title", actor="api")
    assert exc_info.value.status_code == 400
    assert art.document_dir(doc_id).is_dir()

    result = purge_permanent(doc_id, confirm_title=job.title, actor="api")
    assert result["purged"] is True
    assert knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    ) is None
    assert knowledge_repo.count_documents(include_deleted=True) == 0
    assert not art.document_dir(doc_id).exists()
    for path in paths_before:
        assert not art.resolve_stored_path(path).exists()


def test_purge_api_confirm_mismatch_400(monkeypatch, tmp_path):
    doc_id, job, _kdir = _register_doc(monkeypatch, tmp_path)
    from biri_youyaku.app import app

    client = TestClient(app)
    bad = client.post(
        f"/v1/knowledge/documents/{doc_id}/purge",
        json={"confirm": True, "confirm_title": "not-the-title"},
    )
    assert bad.status_code == 400

    ok = client.post(
        f"/v1/knowledge/documents/{doc_id}/purge",
        json={"confirm": True, "confirm_title": job.bvid},
    )
    assert ok.status_code == 200
    assert ok.json()["purged"] is True


def test_audit_events_recorded(monkeypatch, tmp_path):
    doc_id, job, _kdir = _register_doc(monkeypatch, tmp_path)
    soft_delete(doc_id, reason="test")
    restore(doc_id)
    soft_delete(doc_id)
    purge_permanent(doc_id, confirm_title=job.title)

    events = list_audit_events(limit=20)
    actions = [e["action"] for e in events]
    assert "soft_delete" in actions
    assert "restore" in actions
    assert "purge" in actions
    assert any(e["document_id"] == doc_id for e in events if e["action"] == "purge")


def test_backup_dry_run_manifest(monkeypatch, tmp_path):
    _register_doc(monkeypatch, tmp_path)
    result = create_backup(dry_run=True, actor="api")
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert "manifest" in result
    assert result["file_count"] >= 1
    # dry-run must not create backup tree
    assert not (Path(settings.knowledge_backup_dir) / result["timestamp"]).exists()

    events = list_audit_events(limit=5)
    assert any(e["action"] == "backup" for e in events)


def test_register_after_soft_delete_reactivates(monkeypatch, tmp_path):
    doc_id, job, _kdir = _register_doc(monkeypatch, tmp_path)
    soft_delete(doc_id)
    assert knowledge_repo.count_documents() == 0

    # New completed job same bvid/cid → register clears deleted_at
    job2 = _make_completed_job(
        bvid=job.bvid,
        cid=job.cid,
        title="Lifecycle Test Video Updated",
        summary_body="## 概述\n再次登记后应可检索 生命周期测试\n",
    )
    status = try_register_job(job2.id)
    assert status == RECONCILE_REGISTERED

    same_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert same_id == doc_id
    assert knowledge_repo.count_documents() == 1
    assert knowledge_repo.count_deleted_documents() == 0
    hits = search_summaries("生命周期测试", limit=10)
    assert any(h.document_id == doc_id for h in hits)


def test_list_documents_api_filters_deleted(monkeypatch, tmp_path):
    doc_id, _job, _kdir = _register_doc(monkeypatch, tmp_path)
    soft_delete(doc_id)
    from biri_youyaku.app import app

    client = TestClient(app)
    active = client.get("/v1/knowledge/documents")
    assert active.status_code == 200
    assert active.json()["documents"] == []

    all_docs = client.get("/v1/knowledge/documents?include_deleted=true")
    assert all_docs.status_code == 200
    ids = [d["id"] for d in all_docs.json()["documents"]]
    assert doc_id in ids

    status = client.get("/v1/knowledge/status")
    assert status.status_code == 200
    body = status.json()
    assert body["documents"] == 0
    assert body["documents_deleted"] == 1
