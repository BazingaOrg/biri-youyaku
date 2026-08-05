"""Phase C: raw transcript FTS index + layered retrieval + chat citations."""

from __future__ import annotations

from pathlib import Path


from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import try_register_job
from biri_youyaku.knowledge.chunker import window_transcript_segments
from biri_youyaku.knowledge import index as knowledge_index
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.model import RECONCILE_REGISTERED
from biri_youyaku.knowledge.retrieve import (
    EvidenceHit,
    format_mmss,
    query_needs_transcript_evidence,
    retrieve,
    transcript_locator,
)
from biri_youyaku.knowledge.search import Hit, search_summaries
import biri_youyaku.knowledge.retrieve as retrieve_module
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
    cid: int,
    title: str,
    summary_body: str,
    transcript: list[dict] | None = None,
    author: str = "Author",
    subtitle_source: str = "platform",
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
        duration=120.0,
        mid=1,
    )
    items = transcript or [
        {"start": 0.0, "end": 1.0, "text": "hello"},
    ]
    jobs_repo.set_transcript(
        job.id,
        [
            TranscriptItem(start=float(i["start"]), end=float(i["end"]), text=str(i["text"]))
            for i in items
        ],
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
    return jobs_repo.get_job(job.id)


# --- windowing ---


def test_window_covers_segment_bounds():
    segs = [
        {"start": 0.0, "end": 2.0, "raw_text": "alpha", "source": "platform"},
        {"start": 2.0, "end": 4.5, "raw_text": "beta", "source": "platform"},
        {"start": 4.5, "end": 7.0, "raw_text": "gamma", "source": "platform"},
    ]
    windows = window_transcript_segments(segs, max_chars=50, max_span_sec=90, max_segments=8)
    assert windows
    assert windows[0].start_sec == 0.0
    assert windows[0].end_sec == 7.0
    assert "alpha" in windows[0].chunk_text
    assert "gamma" in windows[0].chunk_text
    assert windows[0].subtitle_source == "platform"


def test_window_splits_on_max_segments():
    segs = [
        {"start": float(i), "end": float(i + 1), "raw_text": f"seg{i}", "source": "asr"}
        for i in range(20)
    ]
    windows = window_transcript_segments(
        segs, max_chars=100_000, max_span_sec=10_000, max_segments=8
    )
    assert len(windows) >= 3
    assert windows[0].start_sec == 0.0
    assert windows[0].end_sec == 8.0  # segs 0..7 → end of seg 7 is 8.0
    for w in windows:
        assert w.subtitle_source == "asr"


def test_format_mmss_and_locator():
    assert format_mmss(0) == "00:00"
    assert format_mmss(65.9) == "01:05"
    assert transcript_locator(65.0, 90.0) == "转写：01:05–01:30"


def test_query_needs_transcript_evidence_heuristics():
    assert query_needs_transcript_evidence("深度学习", summary_hit_count=5) is False
    assert query_needs_transcript_evidence("端口 8080", summary_hit_count=5) is True
    assert query_needs_transcript_evidence("几点开始", summary_hit_count=5) is True
    assert query_needs_transcript_evidence("他说「完成」", summary_hit_count=5) is True
    assert query_needs_transcript_evidence("npm install", summary_hit_count=5) is True
    assert query_needs_transcript_evidence("唯一词", summary_hit_count=0) is True


# --- index on register ---


def test_register_indexes_transcript_chunks(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1tx01",
        cid=1,
        title="Tx video",
        summary_body="## TL;DR\n概要内容。\n",
        transcript=[
            {"start": 0.0, "end": 3.0, "text": "第一句转写"},
            {"start": 3.0, "end": 6.0, "text": "第二句包含UniqueTxToken"},
            {"start": 6.0, "end": 9.0, "text": "第三句收尾"},
        ],
        subtitle_source="platform",
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    assert knowledge_index.count_transcript_chunks() >= 1
    assert knowledge_index.count_summary_chunks() >= 1

    with db.connect() as connection:
        row = connection.execute(
            """
            SELECT start_sec, end_sec, chunk_text, subtitle_source
            FROM knowledge_transcript_chunks
            ORDER BY chunk_ord
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    assert float(row["start_sec"]) == 0.0
    assert float(row["end_sec"]) >= 6.0
    assert "UniqueTxToken" in row["chunk_text"] or "第一句" in row["chunk_text"]
    assert row["subtitle_source"] == "platform"


def test_startup_index_reaches_old_missing_summary_and_transcript(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    old = _make_completed_job(
        bvid="BV1oldindex",
        cid=1,
        title="Old missing",
        summary_body="## TL;DR\nOldSummaryNeedle\n",
        transcript=[{"start": 0, "end": 1, "text": "OldTranscriptNeedle"}],
    )
    assert try_register_job(old.id) == RECONCILE_REGISTERED
    old_link = knowledge_repo.get_job_link(old.id)
    assert old_link is not None
    with db.connect() as connection:
        connection.execute(
            "UPDATE knowledge_summary_revisions SET created_at = 1 WHERE id = ?",
            (old_link.summary_revision_id,),
        )
        connection.execute(
            "UPDATE knowledge_content_revisions SET created_at = 1 WHERE id = ?",
            (old_link.content_revision_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_rag_chunks_fts WHERE summary_revision_id = ?",
            (old_link.summary_revision_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_rag_chunks WHERE summary_revision_id = ?",
            (old_link.summary_revision_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_transcript_chunks_fts WHERE content_revision_id = ?",
            (old_link.content_revision_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_transcript_chunks WHERE content_revision_id = ?",
            (old_link.content_revision_id,),
        )

    for index in range(100):
        job = _make_completed_job(
            bvid=f"BV1newindex{index:03d}",
            cid=index + 2,
            title=f"New {index}",
            summary_body=f"## TL;DR\nNewSummary{index}\n",
            transcript=[{"start": 0, "end": 1, "text": f"NewTranscript{index}"}],
        )
        assert try_register_job(job.id) == RECONCILE_REGISTERED
        link = knowledge_repo.get_job_link(job.id)
        assert link is not None
        with db.connect() as connection:
            connection.execute(
                "UPDATE knowledge_summary_revisions SET created_at = ? WHERE id = ?",
                (index + 2, link.summary_revision_id),
            )
            connection.execute(
                "UPDATE knowledge_content_revisions SET created_at = ? WHERE id = ?",
                (index + 2, link.content_revision_id),
            )

    assert knowledge_index.index_active_summaries(limit=100, only_missing=True) == 1
    assert knowledge_index.index_active_transcripts(limit=100, only_missing=True) == 1
    assert knowledge_index.count_summary_chunks() >= 101
    assert knowledge_index.count_transcript_chunks() >= 101


# --- layered retrieval ---


def _summary_hit(index: int) -> Hit:
    return Hit(
        chunk_id=f"summary-{index}",
        document_id=f"doc-{index}",
        summary_revision_id="summary-revision",
        title="Summary",
        author=None,
        bvid=None,
        source_url=None,
        heading_path="TL;DR",
        chunk_text=f"summary {index}",
        snippet=f"summary {index}",
        score=float(index),
    )


def _transcript_hit() -> EvidenceHit:
    return EvidenceHit(
        chunk_id="transcript-1",
        document_id="transcript-doc",
        source_level="transcript",
        title="Transcript",
        author=None,
        bvid=None,
        source_url=None,
        heading_path=None,
        start_sec=10.0,
        end_sec=20.0,
        subtitle_source="platform",
        chunk_text="transcript evidence",
        snippet="transcript evidence",
        score=0.0,
        locator="转写：00:10–00:20",
        content_revision_id="content-revision",
        chunk_ord=0,
    )


def test_retrieve_reserves_slot_for_transcript_evidence(monkeypatch):
    transcript = _transcript_hit()
    monkeypatch.setattr(retrieve_module, "search_summaries", lambda *_args, **_kwargs: [_summary_hit(i) for i in range(6)])
    monkeypatch.setattr(retrieve_module, "_search_transcripts", lambda *_args, **_kwargs: [transcript])
    monkeypatch.setattr(retrieve_module, "_load_adjacent_transcript_chunks", lambda *_args, **_kwargs: [transcript])

    hits = retrieve("quota", limit=6)

    assert len(hits) <= 6
    assert any(hit.source_level == "transcript" for hit in hits)


def test_retrieve_allows_summaries_to_fill_limit_without_transcript(monkeypatch):
    monkeypatch.setattr(retrieve_module, "search_summaries", lambda *_args, **_kwargs: [_summary_hit(i) for i in range(6)])
    monkeypatch.setattr(retrieve_module, "_search_transcripts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(retrieve_module, "_load_adjacent_transcript_chunks", lambda *_args, **_kwargs: [])

    hits = retrieve("quota", limit=6)

    assert len(hits) == 6
    assert all(hit.source_level == "summary" for hit in hits)


def test_retrieve_limit_one_prefers_available_transcript_evidence(monkeypatch):
    transcript = _transcript_hit()
    monkeypatch.setattr(retrieve_module, "search_summaries", lambda *_args, **_kwargs: [_summary_hit(1)])
    monkeypatch.setattr(retrieve_module, "_search_transcripts", lambda *_args, **_kwargs: [transcript])
    monkeypatch.setattr(retrieve_module, "_load_adjacent_transcript_chunks", lambda *_args, **_kwargs: [transcript])

    hits = retrieve("quota", limit=1)

    assert hits == [transcript]


def test_layered_summary_discovery_and_global_transcript_fallback(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    # Doc A: summary has UniqueSumAlpha; transcript has ordinary words only.
    job_a = _make_completed_job(
        bvid="BV1layerA",
        cid=10,
        title="Alpha sum",
        summary_body="## TL;DR\nUniqueSumAlpha 只在总结里。\n",
        transcript=[
            {"start": 0.0, "end": 2.0, "text": "闲聊天气很好"},
        ],
    )
    # Doc B: summary is unrelated; transcript holds rare number token.
    job_b = _make_completed_job(
        bvid="BV1layerB",
        cid=11,
        title="Beta tx",
        summary_body="## TL;DR\n完全无关的总结内容。\n",
        transcript=[
            {"start": 10.0, "end": 15.0, "text": "配置端口为 3847291 后重启服务"},
            {"start": 15.0, "end": 20.0, "text": "然后检查健康检查接口"},
        ],
    )
    assert try_register_job(job_a.id) == RECONCILE_REGISTERED
    assert try_register_job(job_b.id) == RECONCILE_REGISTERED

    sum_hits = search_summaries("UniqueSumAlpha", limit=5)
    assert sum_hits
    assert any("UniqueSumAlpha" in h.chunk_text for h in sum_hits)

    # Number only in transcript → global fallback.
    hits = retrieve("3847291", mode="search", limit=10)
    assert hits
    tx = [h for h in hits if h.source_level == "transcript"]
    assert tx
    assert any("3847291" in h.chunk_text for h in tx)
    assert any(h.locator.startswith("转写：") for h in tx)
    assert any(h.start_sec is not None and h.end_sec is not None for h in tx)


def test_phrase_search_on_transcript_fts(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1phrase",
        cid=20,
        title="Phrase video",
        summary_body="## TL;DR\n无数字无命令。\n",
        transcript=[
            {"start": 0.0, "end": 5.0, "text": "今天讨论量子纠缠现象"},
            {"start": 5.0, "end": 10.0, "text": "以及观测问题"},
        ],
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    hits = retrieve("量子纠缠", mode="search", limit=10)
    assert hits
    assert any(
        h.source_level == "transcript" and "量子" in h.chunk_text for h in hits
    ) or any("量子" in h.chunk_text for h in hits)


def test_search_route_returns_transcript_fields(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1routeTx",
        cid=40,
        title="Route tx",
        summary_body="## TL;DR\nRouteSumOnly。\n",
        transcript=[
            {"start": 5.0, "end": 12.0, "text": "RouteTxUniqueWord 出现在转写"},
        ],
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED

    from biri_youyaku.app import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    search = client.get("/v1/knowledge/search", params={"q": "RouteTxUniqueWord"})
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits
    tx = [h for h in hits if h.get("source_level") == "transcript"]
    assert tx
    assert tx[0]["locator"].startswith("转写：")
    assert "start_sec" in tx[0]
    assert "end_sec" in tx[0]

    status = client.get("/v1/knowledge/status")
    body = status.json()
    assert body["transcript_chunks"] >= 1
    assert body["transcript_index_enabled"] is True


def test_rebuild_all_includes_transcripts(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_completed_job(
        bvid="BV1rebuild",
        cid=50,
        title="Rebuild",
        summary_body="## TL;DR\nok\n",
        transcript=[{"start": 0.0, "end": 1.0, "text": "rebuild token xyz"}],
    )
    assert try_register_job(job.id) == RECONCILE_REGISTERED
    n_before = knowledge_index.count_transcript_chunks()
    assert n_before >= 1
    knowledge_index.rebuild_all()
    assert knowledge_index.count_transcript_chunks() >= 1
    assert knowledge_index.count_summary_chunks() >= 1
