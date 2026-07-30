"""S1 cloud-prep: relative storage paths, rewrite, backup restore."""

from __future__ import annotations

from pathlib import Path

import pytest

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import try_register_job
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.knowledge import index as knowledge_index
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.backup import create_backup, restore_backup, verify_backup
from biri_youyaku.knowledge.model import RECONCILE_REGISTERED
from biri_youyaku.knowledge.search import search_summaries
from biri_youyaku.modules.storage import summary as summary_storage
from biri_youyaku.modules.transcript import TranscriptItem


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "knowledge_search_enabled", True)
    monkeypatch.setattr(settings, "knowledge_chat_enabled", False)
    monkeypatch.setattr(settings, "knowledge_transcript_index_enabled", True)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    monkeypatch.setattr(settings, "knowledge_backup_dir", tmp_path / "backups")
    db.init_db()
    return knowledge_dir


def _make_completed_job(
    *,
    bvid: str = "BV1pathTest001",
    cid: int = 99001,
    title: str = "Path Relative Test",
    summary_body: str = "## 概述\n相对路径登记测试关键字 pathrel\n",
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
        author="Author",
        duration=12.0,
        mid=1,
    )
    jobs_repo.set_transcript(
        job.id,
        [TranscriptItem(start=0.0, end=1.0, text="hello paths")],
    )
    jobs_repo.set_subtitle_source(job.id, "platform")
    summary_dir = Path(settings.summary_storage_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{job.id}.md"
    summary_path.write_bytes(summary_body.encode("utf-8"))
    jobs_repo.set_summary_path(job.id, summary_path)
    jobs_repo.update_status(job.id, JobStatus.COMPLETED)
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET completed_at = ? WHERE id = ?",
            (now_ms(), job.id),
        )
    return jobs_repo.get_job(job.id)


def test_register_stores_relative_storage_path(monkeypatch, tmp_path):
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job = _make_completed_job()
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None
    paths = knowledge_repo.list_artifact_paths(doc_id)
    assert paths
    abs_prefix = str(knowledge_dir.resolve())
    for stored in paths:
        assert not Path(stored).is_absolute(), stored
        assert stored.startswith("artifacts/"), stored
        assert "\\" not in stored
        assert not stored.startswith(abs_prefix)
        resolved = art.resolve_stored_path(stored)
        assert resolved.is_file()
        assert resolved.is_relative_to(knowledge_dir.resolve())


def test_register_stores_relative_summary_path(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job()
    loaded = jobs_repo.get_job(job.id)
    assert loaded is not None
    assert loaded.summary_path is not None
    assert not Path(loaded.summary_path).is_absolute()
    assert loaded.summary_path.endswith(".md")
    assert "\\" not in loaded.summary_path
    body = jobs_repo.read_summary(loaded)
    assert body is not None
    assert "pathrel" in body


def test_index_works_after_register_relative(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job()
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None
    n = knowledge_index.index_document_active_summary(doc_id)
    assert n >= 1
    hits = search_summaries("pathrel", limit=10)
    assert any(h.document_id == doc_id for h in hits)


def test_legacy_absolute_artifact_path_resolves(monkeypatch, tmp_path):
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job = _make_completed_job(bvid="BV1legacyAbs01", cid=99002)
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None

    # Force absolute paths in DB (legacy shape).
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, storage_path FROM knowledge_artifacts WHERE document_id = ?",
            (doc_id,),
        ).fetchall()
        for row in rows:
            abs_path = art.resolve_stored_path(row["storage_path"])
            assert abs_path.is_file()
            connection.execute(
                "UPDATE knowledge_artifacts SET storage_path = ? WHERE id = ?",
                (str(abs_path), row["id"]),
            )

    for stored in knowledge_repo.list_artifact_paths(doc_id):
        assert Path(stored).is_absolute()
        assert art.resolve_stored_path(stored).is_file()

    n = knowledge_index.index_document_active_summary(doc_id)
    assert n >= 1
    hits = search_summaries("pathrel", limit=10)
    assert any(h.document_id == doc_id for h in hits)
    # knowledge_dir still holds files at absolute locations.
    assert knowledge_dir.exists()


def test_legacy_absolute_summary_path_read(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(bvid="BV1legacySum01", cid=99003)
    abs_summary = Path(settings.summary_storage_dir) / f"{job.id}.md"
    assert abs_summary.is_file()
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET summary_path = ? WHERE id = ?",
            (str(abs_summary), job.id),
        )
    loaded = jobs_repo.get_job(job.id)
    assert loaded is not None
    assert Path(loaded.summary_path).is_absolute()
    assert jobs_repo.read_summary(loaded) is not None


def test_rewrite_artifact_paths_absolute_to_relative(monkeypatch, tmp_path):
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job = _make_completed_job(bvid="BV1rewrite001", cid=99004)
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    # Force absolute then rewrite.
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, storage_path FROM knowledge_artifacts WHERE document_id = ?",
            (doc_id,),
        ).fetchall()
        for row in rows:
            abs_path = art.resolve_stored_path(row["storage_path"])
            connection.execute(
                "UPDATE knowledge_artifacts SET storage_path = ? WHERE id = ?",
                (str(abs_path), row["id"]),
            )

    counts = art.rewrite_artifact_paths_in_db()
    assert counts["rewritten"] >= 2
    for stored in knowledge_repo.list_artifact_paths(doc_id):
        assert not Path(stored).is_absolute()
        assert stored.startswith("artifacts/")
        assert art.resolve_stored_path(stored).is_file()
    assert knowledge_dir.exists()


def test_rewrite_summary_paths_absolute_to_relative(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(bvid="BV1rewriteSum", cid=99005)
    abs_summary = Path(settings.summary_storage_dir) / f"{job.id}.md"
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET summary_path = ? WHERE id = ?",
            (str(abs_summary), job.id),
        )
    counts = summary_storage.rewrite_summary_paths_in_db()
    assert counts["rewritten"] >= 1
    loaded = jobs_repo.get_job(job.id)
    assert loaded is not None
    assert not Path(loaded.summary_path).is_absolute()
    assert jobs_repo.read_summary(loaded) is not None


def test_backup_verify_and_restore(monkeypatch, tmp_path):
    knowledge_dir = _setup(monkeypatch, tmp_path)
    job = _make_completed_job(bvid="BV1backup001", cid=99006)
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    backup_root = tmp_path / "backups"
    result = create_backup(dry_run=False, backup_dir=backup_root, actor="test")
    assert result["ok"] is True
    backup_dir = Path(result["backup_dir"])
    assert (backup_dir / "manifest.json").is_file()
    assert (backup_dir / "biri_youyaku.db").is_file()

    verification = verify_backup(backup_dir)
    assert verification["ok"] is True
    assert verification["checked"] >= 1
    assert verification["mismatches"] == []
    assert verification["missing"] == []

    # dry-run restore
    dest = tmp_path / "restore_target"
    dry = restore_backup(
        backup_dir,
        dest_db=dest / "biri_youyaku.db",
        dest_knowledge=dest / "knowledge",
        dest_summaries=dest / "summaries",
        dry_run=True,
    )
    assert dry["ok"] is True
    assert dry["dry_run"] is True
    assert dry["restored"] is False
    assert not (dest / "biri_youyaku.db").exists()

    live = restore_backup(
        backup_dir,
        dest_db=dest / "biri_youyaku.db",
        dest_knowledge=dest / "knowledge",
        dest_summaries=dest / "summaries",
        dry_run=False,
    )
    assert live["ok"] is True
    assert live["restored"] is True
    assert (dest / "biri_youyaku.db").is_file()
    assert (dest / "knowledge").is_dir()
    assert (dest / "summaries").is_dir()
    # At least one artifact file copied
    art_files = list((dest / "knowledge").rglob("*"))
    assert any(p.is_file() for p in art_files)
    assert knowledge_dir.exists()
