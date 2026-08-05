"""Phase B: FTS summary search + opt-in knowledge chat."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import try_register_job
from biri_youyaku.knowledge.chunker import chunk_summary_markdown, fts_prepare_text
from biri_youyaku.knowledge import index as knowledge_index
from biri_youyaku.knowledge.model import RECONCILE_REGISTERED
from biri_youyaku.knowledge.search import search_summaries
from biri_youyaku.modules.transcript import TranscriptItem


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "knowledge_search_enabled", True)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    monkeypatch.setattr(settings, "api_token", "")
    db.init_db()
    return knowledge_dir


def _make_completed_job(
    *,
    bvid: str,
    cid: int,
    title: str,
    summary_body: str,
    author: str = "Author",
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
        [TranscriptItem(start=0.0, end=1.0, text="hello")],
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


# --- chunker ---


def test_chunker_tldr_and_nested_headings():
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
    assert all(not p.startswith("AI 总结：##") for p in paths)


def test_chunker_no_heading_is_full_doc():
    md = "没有二级标题的纯文本总结。\n第二段。"
    chunks = chunk_summary_markdown(md)
    assert len(chunks) == 1
    assert chunks[0].heading_path == "AI 总结：全文"
    assert "纯文本总结" in chunks[0].chunk_text


def test_fts_prepare_splits_cjk():
    prepared = fts_prepare_text("深度学习")
    assert "深" in prepared and "学" in prepared
    assert " " in prepared
    tokens = prepared.split()
    assert tokens == ["深", "度", "学", "习"]


# --- index + search ---


def test_index_and_search_finds_distinct_docs(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job_a = _make_completed_job(
        bvid="BV1aaa",
        cid=1,
        title="Alpha video",
        summary_body="## TL;DR\nUniqueTermAlpha 出现在这里。\n",
    )
    job_b = _make_completed_job(
        bvid="BV1bbb",
        cid=2,
        title="Beta video",
        summary_body="## TL;DR\nUniqueTermBeta 完全不同。\n",
    )
    assert try_register_job(job_a.id) == RECONCILE_REGISTERED
    assert try_register_job(job_b.id) == RECONCILE_REGISTERED
    assert knowledge_index.count_chunks() >= 2

    hits_a = search_summaries("UniqueTermAlpha", limit=5)
    assert hits_a
    assert all("Alpha" in (h.title or "") or "UniqueTermAlpha" in h.chunk_text for h in hits_a)
    assert not any("UniqueTermBeta" in h.chunk_text for h in hits_a)

    hits_b = search_summaries("UniqueTermBeta", limit=5)
    assert hits_b
    assert all("Beta" in (h.title or "") or "UniqueTermBeta" in h.chunk_text for h in hits_b)


def test_chinese_term_match_via_fts_prepare(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1zhcn",
        cid=9,
        title="中文视频",
        summary_body="## 笔记\n本节讨论量子纠缠与观测问题。\n",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    hits = search_summaries("量子纠缠", limit=5)
    assert hits
    assert any("量子" in h.chunk_text for h in hits)


def test_cjk_phrase_avoids_reversed_character_false_positive(monkeypatch, tmp_path):
    """「张三」must not match a chunk that only has 「三张…」(order reversed)."""
    _setup(monkeypatch, tmp_path)
    noise = _make_completed_job(
        bvid="BV1noise",
        cid=1,
        title="扑克教学",
        summary_body="## 笔记\n先发三张牌再看公共牌。\n",
    )
    target = _make_completed_job(
        bvid="BV1name",
        cid=2,
        title="人物访谈",
        summary_body="## 笔记\n嘉宾张三谈到创业经历。\n",
    )
    assert try_register_job(noise.id) == RECONCILE_REGISTERED
    assert try_register_job(target.id) == RECONCILE_REGISTERED

    hits = search_summaries("张三", limit=10)
    assert hits
    assert all("三张" not in h.chunk_text for h in hits)
    assert any("张三" in h.chunk_text for h in hits)


def test_empty_query_returns_empty(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    assert search_summaries("") == []
    assert search_summaries("   ") == []


def test_search_route_and_status(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1route",
        cid=4,
        title="Route video",
        summary_body="## TL;DR\nRouteUniqueWord 检索接口。\n",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    from biri_youyaku.app import create_app

    client = TestClient(create_app())
    status = client.get("/v1/knowledge/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ok"] is True
    assert body["documents"] >= 1
    assert body["chunks"] >= 1
    assert body["search_enabled"] is True

    search = client.get("/v1/knowledge/search", params={"q": "RouteUniqueWord"})
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits
    assert hits[0]["heading_path"].startswith("AI 总结：")


def test_register_still_succeeds_if_index_fails(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1idxfail",
        cid=5,
        title="Index fail",
        summary_body="## TL;DR\nok\n",
    )

    def boom(*_a, **_k):
        raise RuntimeError("index boom")

    monkeypatch.setattr(
        "biri_youyaku.knowledge.index.index_document_active_summary",
        boom,
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
