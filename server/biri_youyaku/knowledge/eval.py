"""Phase F: synthetic / fixture knowledge retrieval evaluation.

Seeds real jobs through try_register_job so FTS matches production paths.
Does not enable chat or dense retrieval.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from biri_youyaku import db
from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge import try_register_job
from biri_youyaku.knowledge.model import RECONCILE_REGISTERED
from biri_youyaku.knowledge.retrieve import retrieve
from biri_youyaku.knowledge.search import search_summaries
from biri_youyaku.modules.transcript import TranscriptItem

logger = logging.getLogger("biri_youyaku.knowledge.eval")

_GATE_METRIC_KEYS = (
    "summary_recall_at_5",
    "summary_mrr_at_10",
    "no_answer_empty_rate",
    "transcript_doc_recall_at_5",
)


def default_fixtures_dir() -> Path:
    """``server/tests/fixtures/knowledge_eval`` relative to the package tree."""
    # biri_youyaku/knowledge/eval.py → server/
    server_root = Path(__file__).resolve().parents[2]
    return server_root / "tests" / "fixtures" / "knowledge_eval"


def load_corpus(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        p = p / "corpus" / "docs.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"corpus must be a JSON list: {p}")
    return data


def load_queries(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        p = p / "queries.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        queries = data.get("queries", [])
    else:
        queries = data
    if not isinstance(queries, list):
        raise ValueError(f"queries must be a list: {p}")
    return queries


def load_manifest(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        p = p / "manifest.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a JSON object: {p}")
    return data


def doc_key_to_bvid(docs: Iterable[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for doc in docs:
        key = str(doc.get("doc_key") or "").strip()
        bvid = str(doc.get("bvid") or "").strip()
        if key and bvid:
            mapping[key] = bvid
    return mapping


def bvid_to_doc_key(docs: Iterable[dict[str, Any]]) -> dict[str, str]:
    return {bvid: key for key, bvid in doc_key_to_bvid(docs).items()}


def seed_eval_corpus(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Create completed jobs + register/index each synthetic doc.

    Caller must point settings (db_path, knowledge_storage_dir, summary_storage_dir)
    at an isolated tree and call ``db.init_db()`` first.
    """
    registered: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for doc in docs:
        doc_key = str(doc.get("doc_key") or "")
        bvid = str(doc.get("bvid") or "")
        cid = int(doc.get("cid") or 0)
        title = str(doc.get("title") or doc_key or bvid)
        author = str(doc.get("author") or "eval")
        summary_md = str(doc.get("summary_md") or "")
        subtitle_source = str(doc.get("subtitle_source") or "platform")
        raw_transcript = doc.get("transcript") or []
        if not bvid or not cid:
            failures.append({"doc_key": doc_key, "reason": "missing_bvid_or_cid"})
            continue

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
        items = [
            TranscriptItem(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=str(seg.get("text") or ""),
            )
            for seg in raw_transcript
            if isinstance(seg, dict)
        ]
        if not items:
            items = [TranscriptItem(start=0.0, end=1.0, text=title)]
        jobs_repo.set_transcript(job.id, items)
        jobs_repo.set_subtitle_source(job.id, subtitle_source)

        summary_dir = Path(settings.summary_storage_dir)
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_path = summary_dir / f"{job.id}.md"
        summary_path.write_bytes(summary_md.encode("utf-8"))
        jobs_repo.set_summary_path(job.id, summary_path)
        jobs_repo.update_status(job.id, JobStatus.COMPLETED)
        with db.connect() as connection:
            connection.execute(
                "UPDATE jobs SET completed_at = ? WHERE id = ?",
                (now_ms(), job.id),
            )

        status = try_register_job(job.id)
        if status != RECONCILE_REGISTERED:
            failures.append(
                {"doc_key": doc_key, "job_id": job.id, "reason": status or "register_failed"}
            )
            continue
        registered.append(
            {
                "doc_key": doc_key,
                "bvid": bvid,
                "job_id": job.id,
            }
        )
    return {
        "registered_count": len(registered),
        "failure_count": len(failures),
        "registered": registered,
        "failures": failures,
    }


def _unique_doc_keys_from_hits(
    hits: list[Any],
    *,
    bvid_map: dict[str, str],
) -> list[str]:
    """Map hit bvids → doc_keys in rank order (first occurrence wins)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        bvid = getattr(hit, "bvid", None) or (hit.get("bvid") if isinstance(hit, dict) else None)
        if not bvid:
            continue
        key = bvid_map.get(str(bvid))
        if key is None:
            # Fall back to bvid itself so unmatched gold still fails cleanly.
            key = str(bvid)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _first_gold_rank(ranked_keys: list[str], gold: set[str], *, k: int) -> int | None:
    for i, key in enumerate(ranked_keys[:k]):
        if key in gold:
            return i + 1
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def run_eval(
    *,
    queries: list[dict[str, Any]],
    docs: list[dict[str, Any]] | None = None,
    bvid_map: dict[str, str] | None = None,
    splits: list[str] | None = None,
    k_recall: int = 5,
    k_mrr: int = 10,
) -> dict[str, Any]:
    """Run retrieval metrics over labeled queries against the live FTS indexes."""
    if bvid_map is None:
        if docs is None:
            bvid_map = {}
        else:
            bvid_map = bvid_to_doc_key(docs)

    split_filter: set[str] | None = None
    if splits:
        split_filter = {s.strip() for s in splits if s and str(s).strip()}

    selected = []
    for q in queries:
        if split_filter is not None and str(q.get("split") or "") not in split_filter:
            continue
        selected.append(q)

    per_query: list[dict[str, Any]] = []
    summary_hits_flags: list[float] = []
    summary_rr: list[float] = []
    no_answer_empty: list[float] = []
    transcript_hits_flags: list[float] = []

    by_split: dict[str, dict[str, list[float]]] = {}

    def _bucket(split: str) -> dict[str, list[float]]:
        if split not in by_split:
            by_split[split] = {
                "summary_recall": [],
                "summary_mrr": [],
                "no_answer_empty": [],
                "transcript_recall": [],
            }
        return by_split[split]

    for q in selected:
        qid = str(q.get("id") or "")
        text = str(q.get("query") or "").strip()
        kind = str(q.get("kind") or "answerable")
        layer = str(q.get("layer") or "summary")
        split = str(q.get("split") or "train")
        gold_keys = {str(k) for k in (q.get("gold_doc_keys") or []) if k}
        bucket = _bucket(split)

        row: dict[str, Any] = {
            "id": qid,
            "query": text,
            "kind": kind,
            "layer": layer,
            "split": split,
            "gold_doc_keys": sorted(gold_keys),
        }

        if kind == "no_answer":
            hits = search_summaries(text, limit=max(k_recall, k_mrr))
            empty = len(hits) == 0
            no_answer_empty.append(1.0 if empty else 0.0)
            bucket["no_answer_empty"].append(1.0 if empty else 0.0)
            row["empty"] = empty
            row["top_doc_keys"] = _unique_doc_keys_from_hits(hits, bvid_map=bvid_map)
            per_query.append(row)
            continue

        if layer == "transcript":
            evidence = retrieve(text, mode="search", limit=max(k_recall, 12))
            ranked = _unique_doc_keys_from_hits(evidence, bvid_map=bvid_map)
            rank = _first_gold_rank(ranked, gold_keys, k=k_recall)
            hit = rank is not None
            transcript_hits_flags.append(1.0 if hit else 0.0)
            bucket["transcript_recall"].append(1.0 if hit else 0.0)
            row["hit"] = hit
            row["rank"] = rank
            row["top_doc_keys"] = ranked[:k_recall]
            per_query.append(row)
            continue

        # summary layer (default) — also used when layer is "both"
        hits = search_summaries(text, limit=max(k_mrr, k_recall))
        ranked = _unique_doc_keys_from_hits(hits, bvid_map=bvid_map)
        rank_recall = _first_gold_rank(ranked, gold_keys, k=k_recall)
        rank_mrr = _first_gold_rank(ranked, gold_keys, k=k_mrr)
        hit = rank_recall is not None
        rr = (1.0 / rank_mrr) if rank_mrr is not None else 0.0
        summary_hits_flags.append(1.0 if hit else 0.0)
        summary_rr.append(rr)
        bucket["summary_recall"].append(1.0 if hit else 0.0)
        bucket["summary_mrr"].append(rr)
        row["hit"] = hit
        row["rank"] = rank_mrr
        row["top_doc_keys"] = ranked[:k_mrr]
        per_query.append(row)

    metrics = {
        "summary_recall_at_5": _mean(summary_hits_flags),
        "summary_mrr_at_10": _mean(summary_rr),
        "no_answer_empty_rate": _mean(no_answer_empty),
        "transcript_doc_recall_at_5": _mean(transcript_hits_flags),
        "n_queries": len(selected),
        "n_summary_answerable": len(summary_hits_flags),
        "n_transcript_answerable": len(transcript_hits_flags),
        "n_no_answer": len(no_answer_empty),
    }

    split_metrics: dict[str, dict[str, Any]] = {}
    for split_name, lists in by_split.items():
        split_metrics[split_name] = {
            "summary_recall_at_5": _mean(lists["summary_recall"]),
            "summary_mrr_at_10": _mean(lists["summary_mrr"]),
            "no_answer_empty_rate": _mean(lists["no_answer_empty"]),
            "transcript_doc_recall_at_5": _mean(lists["transcript_recall"]),
            "n_summary_answerable": len(lists["summary_recall"]),
            "n_transcript_answerable": len(lists["transcript_recall"]),
            "n_no_answer": len(lists["no_answer_empty"]),
        }

    return {
        "metrics": metrics,
        "split_metrics": split_metrics,
        "per_query": per_query,
        "k_recall": k_recall,
        "k_mrr": k_mrr,
        "splits": sorted(split_filter) if split_filter else None,
    }


def evaluate_gates(
    report: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Compare metrics to thresholds. Missing metrics or empty eval → not met."""
    metrics = report.get("metrics") or {}
    n_queries = int(metrics.get("n_queries") or 0)
    failures: list[dict[str, Any]] = []

    if n_queries <= 0:
        failures.append(
            {
                "metric": "n_queries",
                "actual": n_queries,
                "threshold": 1,
                "reason": "empty_eval",
            }
        )

    for key in _GATE_METRIC_KEYS:
        if key not in thresholds:
            continue
        thr = float(thresholds[key])
        actual = metrics.get(key)
        if actual is None:
            failures.append(
                {
                    "metric": key,
                    "actual": None,
                    "threshold": thr,
                    "reason": "missing_metric",
                }
            )
            continue
        if float(actual) < thr:
            failures.append(
                {
                    "metric": key,
                    "actual": float(actual),
                    "threshold": thr,
                    "reason": "below_threshold",
                }
            )

    return {
        "gates_met": len(failures) == 0,
        "failures": failures,
        "thresholds": {k: float(thresholds[k]) for k in thresholds if k in _GATE_METRIC_KEYS or k in thresholds},
    }


def configure_eval_settings(root: Path) -> None:
    """Point settings at an isolated root (db + knowledge + summaries)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    settings.db_path = root / "jobs.db"
    settings.knowledge_storage_dir = root / "knowledge"
    settings.summary_storage_dir = root / "summaries"
    settings.knowledge_register_enabled = True
    settings.knowledge_search_enabled = True
    settings.knowledge_transcript_index_enabled = True
    # Chat remains off for eval harness.
    settings.knowledge_chat_enabled = False


def run_synthetic_eval(
    *,
    fixtures_dir: Path | str | None = None,
    root: Path | str | None = None,
    splits: list[str] | None = None,
    k_recall: int = 5,
    k_mrr: int = 10,
    init_db: bool = True,
    configure_settings: bool = True,
) -> dict[str, Any]:
    """Load fixtures, optionally configure tmp root, seed, evaluate, gate-check.

    If ``configure_settings`` is False, caller already monkeypatched settings and
    initialized the DB (pytest path).
    """
    fixtures = Path(fixtures_dir) if fixtures_dir else default_fixtures_dir()
    docs = load_corpus(fixtures)
    queries = load_queries(fixtures)
    manifest = load_manifest(fixtures)
    thresholds = dict(manifest.get("ci_thresholds") or {})

    if configure_settings:
        if root is None:
            raise ValueError("root is required when configure_settings=True")
        configure_eval_settings(Path(root))
    if init_db:
        db.init_db()

    seed = seed_eval_corpus(docs)
    report = run_eval(
        queries=queries,
        docs=docs,
        splits=splits,
        k_recall=k_recall,
        k_mrr=k_mrr,
    )
    gates = evaluate_gates(report, thresholds)
    return {
        "corpus": manifest.get("corpus", "unknown"),
        "fixtures_dir": str(fixtures),
        "seed": seed,
        "metrics": report["metrics"],
        "split_metrics": report["split_metrics"],
        "per_query": report["per_query"],
        "gates": gates,
        "gates_met": gates["gates_met"],
        "thresholds": thresholds,
        "k_recall": k_recall,
        "k_mrr": k_mrr,
        "splits": report.get("splits"),
        "note": (
            "Synthetic CI thresholds only; production holdout gates not claimed. "
            "See production_gates_ref in manifest."
        ),
        "production_gates_ref": manifest.get("production_gates_ref"),
    }
