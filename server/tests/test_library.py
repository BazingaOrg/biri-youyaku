"""Library list/search/content/trash + related v2 backend behaviour."""

from __future__ import annotations

from pathlib import Path

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


def test_library_rank_bvid_title_notes_subs(monkeypatch, tmp_path):
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

    client = _client()
    response = client.get("/v1/library/search", params={"q": term, "scope": "all"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["partial"] == []
    bvids = [g["bvid"] for g in body["groups"]]
    assert bvids[:4] == [f"BV{term}", "BV1titlezz", "BV1noteszz", "BV1subszz"]
    assert body["groups"][0]["match"]["bvid"] is True
    assert body["groups"][1]["match"]["title"] is True
    assert body["groups"][2]["hit_counts"]["notes"] >= 2
    assert body["groups"][3]["hit_counts"]["subs"] >= 2


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


def test_library_search_empty_q_400(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    client = _client()
    response = client.get("/v1/library/search", params={"q": "  "})
    assert response.status_code == 400
