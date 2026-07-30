"""Scan completed jobs and best-effort register into knowledge registry."""

from __future__ import annotations

import logging

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.model import (
    MAX_RECONCILE_ATTEMPTS,
    PERMANENT_SKIP_REASONS,
    RECONCILE_FAILED,
    RECONCILE_REGISTERED,
    RECONCILE_SKIPPED,
)
from biri_youyaku.knowledge.register import try_register_job

logger = logging.getLogger("biri_youyaku.knowledge.reconcile")


def _should_attempt(job_id: str) -> bool:
    row = knowledge_repo.get_reconcile(job_id)
    if row is None:
        return True
    if row.status == RECONCILE_REGISTERED:
        # Still try if job_link missing (partial failure recovery).
        link = knowledge_repo.get_job_link(job_id)
        return link is None
    if row.status == RECONCILE_SKIPPED:
        if row.reason in PERMANENT_SKIP_REASONS:
            return False
        if row.reason and row.reason.startswith("task_type_"):
            return False
        return True
    if row.status == RECONCILE_FAILED:
        if row.attempts < MAX_RECONCILE_ATTEMPTS:
            return True
        if row.reason != "missing_bvid_or_cid":
            return False
        job = jobs_repo.get_job(job_id)
        return job is not None and bool((job.bvid or "").strip()) and job.cid is not None
    # pending or unknown
    return True


def reconcile_once(limit: int = 50) -> dict[str, int]:
    """Register pending completed summary jobs. Best-effort; never raises."""
    counts = {
        "scanned": 0,
        "attempted": 0,
        "registered": 0,
        "failed": 0,
        "skipped": 0,
    }
    if not settings.knowledge_register_enabled:
        return counts
    try:
        job_ids = knowledge_repo.list_reconcilable_completed_jobs(limit=limit)
        for job_id in job_ids:
            if counts["attempted"] >= limit:
                break
            counts["scanned"] += 1
            if not _should_attempt(job_id):
                continue
            counts["attempted"] += 1
            status = try_register_job(job_id)
            if status == RECONCILE_REGISTERED:
                counts["registered"] += 1
            elif status == RECONCILE_FAILED:
                counts["failed"] += 1
            else:
                counts["skipped"] += 1
    except Exception:
        logger.exception("knowledge reconcile_once failed")
    if counts["attempted"]:
        logger.info("knowledge reconcile: %s", counts)
    return counts
