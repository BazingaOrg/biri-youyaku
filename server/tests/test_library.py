"""Library list/search/content/trash + related v2 backend behaviour."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from fastapi.testclient import TestClient

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import reconcile_once, try_register_job
from biri_youyaku.knowledge.chunker import chunk_summary_markdown
from biri_youyaku.knowledge.lifecycle import purge_permanent
from biri_youyaku.knowledge.model import RECONCILE_FAILED, RECONCILE_PURGED, RECONCILE_REGISTERED
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.modules.asr.formatter import transcript_to_text
from biri_youyaku.modules.transcript import TranscriptItem


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "knowledge_search_enabled", True)
    monkeypatch.setattr(settings, "knowledge_transcript_index_enabled", True)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    monkeypatch.setattr(settings, "api_token", "")
    db.init_db()
    return knowledge_dir


def _make_completed_job(
    *,
    bvid: str,
    cid: int | None,
    title: str,
    summary_body: str,
    author: str = "Author",
    mid: int | None = 1,
    duration: float = 12.0,
    transcript: list[dict] | None = None,
    tags: list[str] | None = None,
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
        duration=duration,
        mid=mid,
    )
    items = transcript or [{"start": 0.0, "end": 1.0, "text": "hello"}]
    jobs_repo.set_transcript(
        job.id,
        [
            TranscriptItem(start=float(i["start"]), end=float(i["end"]), text=str(i["text"]))
            for i in items
        ],
    )
    jobs_repo.set_subtitle_source(job.id, "platform")
    if tags is not None:
        jobs_repo.set_tags(job.id, tags)
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


def _client():
    from biri_youyaku.app import create_app

    return TestClient(create_app())


def test_transcript_to_text_inserts_timestamp_every_30s():
    items = [
        TranscriptItem(start=0, end=1, text="a"),
        TranscriptItem(start=10, end=11, text="b"),
        TranscriptItem(start=30, end=31, text="c"),
        TranscriptItem(start=40, end=41, text="d"),
    ]
    text = transcript_to_text(items)
    assert text.split("\n") == ["[00:00]", "a", "b", "[00:30]", "c", "d"]


def test_chunker_legacy_format_unchanged():
    md = """## TL;DR
一句话概要。

## 笔记
### 背景
背景段落。

### 方法
方法段落。

## 收束
收束内容。
"""
    chunks = chunk_summary_markdown(md)
    paths = [c.heading_path for c in chunks]
    assert "AI 总结：TL;DR" in paths
    assert "AI 总结：笔记 / 背景" in paths
    assert "AI 总结：笔记 / 方法" in paths
    assert "AI 总结：收束" in paths
    assert all(c.start_sec is None for c in chunks)


def test_chunker_new_format_parses_start_sec():
    md = """> 一句话定位

## 00:00 问题背景
背景内容。

## 02:15 方案尝试
方案内容。

## 收束
带走的话。
"""
    chunks = chunk_summary_markdown(md)
    by_path = {c.heading_path: c for c in chunks}
    assert "问题背景" in by_path
    assert "方案尝试" in by_path
    assert "笔记" not in by_path["问题背景"].heading_path
    assert by_path["问题背景"].start_sec == 0.0
    assert by_path["方案尝试"].start_sec == 135.0
    assert by_path["收束"].start_sec is None
    assert any(c.heading_path == "TL;DR" for c in chunks)


def test_library_search_orders_all_match_types_by_generation_time(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    term = "RankNeedle"
    job_bvid = _make_completed_job(
        bvid=f"BV{term}",
        cid=1,
        title="unrelated bvid document",
        summary_body="## 笔记\n没有任何这个关键词。\n",
    )
    job_title = _make_completed_job(
        bvid="BV1titlezz",
        cid=2,
        title=f"{term} appears in title",
        summary_body="## 笔记\n标题文档正文不含检索词。\n",
    )
    job_notes = _make_completed_job(
        bvid="BV1noteszz",
        cid=3,
        title="notes only video",
        summary_body=(f"## 笔记\n### A\n{term} one\n\n### B\n{term} two\n\n### C\n{term} three\n"),
    )
    job_subs = _make_completed_job(
        bvid="BV1subszz",
        cid=4,
        title="subs only video",
        summary_body="## 笔记\n字幕文档正文不含检索词。\n",
        transcript=[
            {"start": 0.0, "end": 2.0, "text": f"{term} alpha"},
            {"start": 200.0, "end": 202.0, "text": f"{term} beta"},
            {"start": 400.0, "end": 402.0, "text": f"{term} gamma"},
        ],
    )
    for job in (job_bvid, job_title, job_notes, job_subs):
        assert try_register_job(job.id) == RECONCILE_REGISTERED

    with db.connect() as connection:
        for timestamp, job in enumerate((job_bvid, job_title, job_notes, job_subs), start=1):
            connection.execute("UPDATE jobs SET completed_at = ? WHERE id = ?", (timestamp, job.id))
        connection.execute("UPDATE knowledge_documents SET updated_at = 100 WHERE external_bvid = ?", (f"BV{term}",))

    client = _client()
    params = {"q": term, "scope": "all", "limit": 2}
    first = client.get("/v1/library/search", params=params)
    assert first.status_code == 200
    page = first.json()
    assert page["partial"] == []
    subs, notes = page["groups"]
    assert [subs["bvid"], notes["bvid"]] == ["BV1subszz", "BV1noteszz"]
    assert subs["hit_counts"]["subs"] >= 2
    assert notes["hit_counts"]["notes"] >= 2

    # A removed result at the page boundary must not skip the remaining notes.
    with db.connect() as connection:
        connection.execute("UPDATE knowledge_documents SET deleted_at = 100 WHERE id = ?", (notes["document_id"],))
    second = client.get("/v1/library/search", params={**params, "cursor": page["next_cursor"]})
    assert second.status_code == 200
    title, bvid = second.json()["groups"]
    assert [title["bvid"], bvid["bvid"]] == ["BV1titlezz", f"BV{term}"]
    assert title["match"]["title"] is True
    assert bvid["match"]["bvid"] is True
    assert second.json()["next_cursor"] is None


def test_library_search_partial_subs_keeps_notes(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1partial",
        cid=8,
        title="Partial notes video",
        summary_body="## 笔记\nPartialUniqueNotes 出现在笔记里。\n",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    def boom(*_a, **_k):
        raise RuntimeError("subs fts down")

    monkeypatch.setattr("biri_youyaku.library.search.query_subs_fts", boom)
    client = _client()
    response = client.get("/v1/library/search", params={"q": "PartialUniqueNotes", "scope": "all"})
    assert response.status_code == 200
    body = response.json()
    assert "subs" in body["partial"]
    assert body["groups"]
    assert any(
        "PartialUniqueNotes" in (g["title"] or "") or g["hit_counts"]["notes"]
        for g in body["groups"]
    )


def test_unregistered_job_in_list_and_metadata_search(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1legacyz",
        cid=None,
        title="LegacyOnlyTitleXYZ",
        summary_body="## 笔记\n旧任务。\n",
    )
    assert try_register_job(job.id) == RECONCILE_FAILED

    client = _client()
    listed = client.get("/v1/library")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(
        item["kind"] == "legacy_job"
        and item["legacy"] is True
        and item["title"] == "LegacyOnlyTitleXYZ"
        and item["legacy_reason"] == "missing_bvid_or_cid"
        for item in items
    )

    searched = client.get("/v1/library/search", params={"q": "LegacyOnlyTitleXYZ"})
    assert searched.status_code == 200
    groups = searched.json()["groups"]
    assert groups
    assert groups[0]["legacy"] is True
    assert groups[0]["legacy_reason"] == "missing_bvid_or_cid"
    assert groups[0]["match"]["title"] is True


def test_purge_then_reconcile_does_not_resurrect(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1purgezz",
        cid=9,
        title="Purge Resurrect Video",
        summary_body="## 笔记\npurge body\n",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    assert doc_id is not None
    summary_path = Path(settings.summary_storage_dir) / f"{job.id}.md"
    assert summary_path.is_file()

    result = purge_permanent(doc_id, confirm_title=job.title, actor="api")
    assert result["purged"] is True
    rec = knowledge_repo.get_reconcile(job.id)
    assert rec is not None
    assert rec.status == RECONCILE_PURGED
    assert not summary_path.exists()
    stored = jobs_repo.get_job(job.id)
    assert stored is not None
    assert stored.summary_path is None

    assert try_register_job(job.id) == "purged"
    reconcile_once(limit=50)
    assert (
        knowledge_repo.find_document_id(
            provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
        )
        is None
    )
    assert knowledge_repo.count_documents(include_deleted=True) == 0


def test_library_content_304(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1etagzz",
        cid=10,
        title="ETag video",
        summary_body="## 笔记\ncontent hash body\n",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    doc_id = knowledge_repo.find_document_id(
        provider="bilibili", external_bvid=job.bvid, external_cid=job.cid
    )
    client = _client()
    first = client.get(f"/v1/library/documents/{doc_id}/content")
    assert first.status_code == 200
    body = first.json()
    assert "markdown" in body
    assert "cues" in body
    assert "note_chunks" in body
    assert "path" not in body
    assert "storage_path" not in str(body)
    etag = first.headers.get("etag")
    assert etag
    second = client.get(
        f"/v1/library/documents/{doc_id}/content",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.content == b""


def test_library_tag_and_up_are_not_keyword_concat(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job_a = _make_completed_job(
        bvid="BV1tagaaa",
        cid=11,
        title="Tagged rust video",
        author="Alice",
        mid=111,
        tags=["rust"],
        summary_body="## 笔记\ntag a\n",
    )
    job_b = _make_completed_job(
        bvid="BV1tagbbb",
        cid=12,
        title="Author named rust",
        author="rust",
        mid=222,
        tags=["python"],
        summary_body="## 笔记\ntag b\n",
    )
    assert try_register_job(job_a.id) == RECONCILE_REGISTERED
    assert try_register_job(job_b.id) == RECONCILE_REGISTERED

    client = _client()
    by_tag = client.get("/v1/library", params={"tag": "rust"})
    assert by_tag.status_code == 200
    tag_bvids = [item["bvid"] for item in by_tag.json()["items"]]
    assert "BV1tagaaa" in tag_bvids
    assert "BV1tagbbb" not in tag_bvids

    by_up = client.get("/v1/library", params={"up": "111"})
    assert by_up.status_code == 200
    up_bvids = [item["bvid"] for item in by_up.json()["items"]]
    assert "BV1tagaaa" in up_bvids
    assert "BV1tagbbb" not in up_bvids
    assert by_tag.json()["total"] == 1
    assert by_up.json()["total"] == 1

    paged = client.get("/v1/library", params={"limit": 1})
    assert paged.status_code == 200
    page = paged.json()
    assert len(page["items"]) == 1
    assert page["next_cursor"]
    assert page["total"] == 2
    rest = client.get("/v1/library", params={"limit": 1, "cursor": page["next_cursor"]})
    assert rest.json()["total"] == 2


def test_library_search_empty_q_400(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    client = _client()
    response = client.get("/v1/library/search", params={"q": "  "})
    assert response.status_code == 400


def test_library_exposes_and_searches_generic_source_identity(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="placeholder",
        cid=None,
        title="Imported lesson",
        summary_body="## 笔记\nlocal media\n",
    )
    jobs_repo.set_source(job.id, "upload", "sha256abc", "")
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET bvid = NULL, cid = NULL WHERE id = ?", (job.id,))
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    client = _client()
    listed = client.get("/v1/library")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["provider"] == "upload"
    assert item["source_id"] == "sha256abc"
    assert item["source_part"] == ""
    assert item["bvid"] is None

    searched = client.get("/v1/library/search", params={"q": "sha256abc"})
    assert searched.status_code == 200
    group = searched.json()["groups"][0]
    assert group["provider"] == "upload"
    assert group["source_id"] == "sha256abc"
    assert group["match"]["source_id"] is True


@pytest.mark.parametrize("register", [True, False])
def test_library_cursor_keeps_visibility_and_filters(monkeypatch, tmp_path, register):
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "knowledge_register_enabled", register)
    with db.connect() as connection:
        connection.executemany(
            """INSERT INTO knowledge_documents
               (id, provider, source_id, mid, tags_json, created_at, updated_at, deleted_at)
               VALUES (?, 'upload', ?, ?, '["topic"]', 100, 100, ?)""",
            [("z", "z", 1, None), ("y", "y", 1, 101), ("x", "x", 2, None)],
        )
        connection.executemany(
            """INSERT INTO jobs (id, url, status, mid, tags_json, options_json, summary_path, created_at, updated_at)
               VALUES (?, 'upload://file', ?, 1, ?, '{}', 'saved.md', 100, 100)""",
            [("jz", "COMPLETED", '["topic"]'), ("jy", "FAILED", '["topic"]'),
             ("jx", "COMPLETED", '["other"]'), ("ja", "COMPLETED", '["topic"]')],
        )
    params = {"limit": 1, "up": 1, "tag": "topic"}
    expected = ["z", "jz", "ja"] if register else ["jz", "ja"]
    client = _client()
    for expected_id in expected:
        response = client.get("/v1/library", params=params)
        assert response.status_code == 200
        page = response.json()
        assert [item["id"] for item in page["items"]] == [expected_id]
        assert page["total"] == len(expected)
        params["cursor"] = page["next_cursor"]
    assert params["cursor"] is None


def test_subtitle_search_work_and_metadata_fallback(monkeypatch, tmp_path):
    from biri_youyaku.library import search

    _setup(monkeypatch, tmp_path)
    for i in range(4):
        job = _make_completed_job(
            bvid=f"BV1scope{i}", cid=i + 1, title="SharedTerm in title",
            summary_body="## 笔记\n内容", transcript=[
                {"start": 0, "end": 1, "text": "SharedTerm" if i < 3 else "unrelated"}
            ],
        )
        assert try_register_job(job.id) == RECONCILE_REGISTERED
    metadata = Mock(wraps=search._query_document_metadata)
    snippet = Mock(wraps=search.make_snippet)
    monkeypatch.setattr(search, "_query_document_metadata", metadata)
    monkeypatch.setattr(search, "make_snippet", snippet)
    client = _client()
    params = {"q": "SharedTerm", "scope": "subs", "limit": 1}
    seen = set()
    for _ in range(3):
        page = client.get("/v1/library/search", params=params).json()
        (group,) = page["groups"]
        seen.add(group["document_id"])
        assert group["hit_counts"] == {"notes": 0, "subs": 1}
        assert "SharedTerm" in group["hits"][0]["snippet"]
        params["cursor"] = page["next_cursor"]
    assert len(seen) == 3
    assert params["cursor"] is None
    assert snippet.call_count == 3
    metadata.assert_not_called()

    monkeypatch.setattr(search, "query_subs_fts", Mock(side_effect=RuntimeError("index unavailable")))
    for register in (True, False):
        monkeypatch.setattr(settings, "knowledge_register_enabled", register)
        fallback = client.get("/v1/library/search", params={"q": "SharedTerm", "scope": "subs"}).json()
        assert fallback["partial"] == ["subs"]
        assert len(fallback["groups"]) == 4
        assert all(group["hits"] == [] for group in fallback["groups"])
        metadata.assert_called_once()
        metadata.reset_mock()
