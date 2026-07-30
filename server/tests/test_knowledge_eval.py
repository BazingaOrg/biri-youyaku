"""Phase F: knowledge eval fixtures + gates (synthetic only)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.knowledge.eval import (
    default_fixtures_dir,
    evaluate_gates,
    load_corpus,
    load_manifest,
    load_queries,
    run_eval,
    run_synthetic_eval,
    seed_eval_corpus,
)


def _setup(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "db_path", tmp_path / "jobs.db")
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(settings, "knowledge_storage_dir", knowledge_dir)
    monkeypatch.setattr(settings, "summary_storage_dir", tmp_path / "summaries")
    monkeypatch.setattr(settings, "knowledge_register_enabled", True)
    monkeypatch.setattr(settings, "knowledge_search_enabled", True)
    monkeypatch.setattr(settings, "knowledge_transcript_index_enabled", True)
    monkeypatch.setattr(settings, "knowledge_chat_enabled", False)
    monkeypatch.setattr(settings, "api_token", "")
    db.init_db()
    return knowledge_dir


def test_fixtures_shape():
    fixtures = default_fixtures_dir()
    docs = load_corpus(fixtures)
    queries = load_queries(fixtures)
    manifest = load_manifest(fixtures)

    assert len(docs) >= 6
    keys = {d["doc_key"] for d in docs}
    assert "doc_ffmpeg" in keys

    answerable = [q for q in queries if q.get("kind") == "answerable"]
    no_answer = [q for q in queries if q.get("kind") == "no_answer"]
    assert len(answerable) >= 15
    assert len(no_answer) >= 5

    categories = {q.get("category") for q in queries}
    for needed in ("entity", "topic", "commands", "no_answer"):
        assert needed in categories

    layers = {q.get("layer") for q in answerable}
    assert "summary" in layers
    assert "transcript" in layers

    thr = manifest.get("ci_thresholds") or {}
    for key in (
        "summary_recall_at_5",
        "summary_mrr_at_10",
        "no_answer_empty_rate",
        "transcript_doc_recall_at_5",
    ):
        assert key in thr


def test_synthetic_eval_meets_ci_gates(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    result = run_synthetic_eval(
        fixtures_dir=default_fixtures_dir(),
        root=tmp_path,
        init_db=False,
        configure_settings=False,
    )
    assert result["seed"]["registered_count"] >= 6
    assert result["seed"]["failure_count"] == 0
    assert result["gates_met"] is True, result.get("gates")
    metrics = result["metrics"]
    assert metrics["summary_recall_at_5"] is not None
    assert metrics["summary_recall_at_5"] >= 0.85
    assert metrics["no_answer_empty_rate"] is not None
    assert metrics["no_answer_empty_rate"] >= 0.80


def test_holdout_split_gates(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    result = run_synthetic_eval(
        fixtures_dir=default_fixtures_dir(),
        root=tmp_path,
        splits=["holdout"],
        init_db=False,
        configure_settings=False,
    )
    assert result["metrics"]["n_queries"] > 0
    assert result["seed"]["failure_count"] == 0
    assert result["gates_met"] is True, result.get("gates")


def test_empty_queries_do_not_claim_ready():
    report = run_eval(queries=[], docs=[])
    gates = evaluate_gates(
        report,
        {
            "summary_recall_at_5": 0.85,
            "summary_mrr_at_10": 0.70,
            "no_answer_empty_rate": 0.80,
            "transcript_doc_recall_at_5": 0.75,
        },
    )
    assert gates["gates_met"] is False
    reasons = {f["reason"] for f in gates["failures"]}
    assert "empty_eval" in reasons or "missing_metric" in reasons


def test_no_answer_uses_layered_retrieval(monkeypatch):
    transcript_hit = SimpleNamespace(bvid="BVtranscript", source_level="transcript")
    monkeypatch.setattr(
        "biri_youyaku.knowledge.eval.retrieve", lambda *args, **kwargs: [transcript_hit]
    )
    report = run_eval(
        queries=[{"id": "no-answer", "query": "npm install", "kind": "no_answer"}],
        bvid_map={"BVtranscript": "doc_cli"},
    )
    assert report["metrics"]["no_answer_empty_rate"] == 0.0
    assert report["per_query"][0]["empty"] is False


def test_transcript_recall_ignores_summary_evidence(monkeypatch):
    summary_hit = SimpleNamespace(bvid="BVsummary", source_level="summary")
    monkeypatch.setattr(
        "biri_youyaku.knowledge.eval.retrieve", lambda *args, **kwargs: [summary_hit]
    )
    report = run_eval(
        queries=[
            {
                "id": "transcript",
                "query": "npm install",
                "kind": "answerable",
                "layer": "transcript",
                "gold_doc_keys": ["doc_cli"],
            }
        ],
        bvid_map={"BVsummary": "doc_cli"},
    )
    assert report["metrics"]["transcript_doc_recall_at_5"] == 0.0


def test_invalid_thresholds_fail_closed():
    report = {
        "metrics": {
            "n_queries": 1,
            "summary_recall_at_5": 1.0,
            "summary_mrr_at_10": 1.0,
            "no_answer_empty_rate": 1.0,
            "transcript_doc_recall_at_5": 1.0,
        }
    }
    cases = (
        {},
        {"summary_recall_at_5": 1.0},
        {"typo": 1.0},
        {
            "summary_recall_at_5": True,
            "summary_mrr_at_10": 1.0,
            "no_answer_empty_rate": 1.0,
            "transcript_doc_recall_at_5": 1.0,
        },
        {
            "summary_recall_at_5": 1.1,
            "summary_mrr_at_10": 1.0,
            "no_answer_empty_rate": 1.0,
            "transcript_doc_recall_at_5": 1.0,
        },
    )
    for thresholds in cases:
        gates = evaluate_gates(report, thresholds)
        assert gates["gates_met"] is False
        assert gates["failures"]


def test_partial_seed_failure_fails_synthetic_runner(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "biri_youyaku.knowledge.eval.seed_eval_corpus",
        lambda docs: {
            "registered_count": len(docs) - 1,
            "failure_count": 1,
            "registered": [],
            "failures": [{"doc_key": "doc_cli", "reason": "register_failed"}],
        },
    )
    result = run_synthetic_eval(
        fixtures_dir=default_fixtures_dir(),
        root=tmp_path,
        init_db=False,
        configure_settings=False,
    )
    assert result["gates_met"] is False
    assert any(
        failure["reason"] == "seed_registration_incomplete"
        for failure in result["gates"]["failures"]
    )


def test_empty_corpus_seed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    seed = seed_eval_corpus([])
    assert seed["registered_count"] == 0
    report = run_eval(queries=[], docs=[])
    gates = evaluate_gates(
        report,
        {
            "summary_recall_at_5": 0.85,
            "summary_mrr_at_10": 0.70,
            "no_answer_empty_rate": 0.80,
            "transcript_doc_recall_at_5": 0.75,
        },
    )
    assert gates["gates_met"] is False


def test_chat_remains_default_off_in_eval_path(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    assert settings.knowledge_chat_enabled is False
    run_synthetic_eval(
        fixtures_dir=default_fixtures_dir(),
        root=tmp_path,
        init_db=False,
        configure_settings=False,
    )
    assert settings.knowledge_chat_enabled is False
