"""Register completed Bili summary jobs into the knowledge registry.

Failures are recorded in knowledge_reconcile and never raised to job callers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs.model import Job, JobStatus
from biri_youyaku.knowledge import artifacts as art
from biri_youyaku.knowledge import repo as knowledge_repo
from biri_youyaku.knowledge.model import (
    ARTIFACT_KIND_SUMMARY,
    ARTIFACT_KIND_TRANSCRIPT_RAW,
    MAX_RECONCILE_ATTEMPTS,
    PERMANENT_SKIP_REASONS,
    PROVIDER_BILIBILI,
    RECONCILE_FAILED,
    RECONCILE_REGISTERED,
    RECONCILE_SKIPPED,
    SKIP_TASK_TYPES,
)

logger = logging.getLogger("biri_youyaku.knowledge.register")


def try_register_job(job_id: str) -> str:
    """Best-effort register; returns final reconcile status string. Never raises."""
    if not settings.knowledge_register_enabled:
        return RECONCILE_SKIPPED
    try:
        return _register_from_job_id(job_id)
    except Exception as exc:
        logger.exception("knowledge register failed for job %s", job_id)
        try:
            knowledge_repo.set_reconcile(
                job_id,
                status=RECONCILE_FAILED,
                reason="exception",
                last_error=str(exc)[:1000],
                increment_attempts=True,
            )
        except Exception:
            logger.exception("could not persist reconcile failure for job %s", job_id)
        return RECONCILE_FAILED


def register_from_job(job: Job) -> str:
    """Register a loaded Job. Prefer try_register_job for call sites."""
    if not settings.knowledge_register_enabled:
        return RECONCILE_SKIPPED
    try:
        return _register_job(job)
    except Exception as exc:
        logger.exception("knowledge register failed for job %s", job.id)
        try:
            knowledge_repo.set_reconcile(
                job.id,
                status=RECONCILE_FAILED,
                reason="exception",
                last_error=str(exc)[:1000],
                increment_attempts=True,
            )
        except Exception:
            logger.exception("could not persist reconcile failure for job %s", job.id)
        return RECONCILE_FAILED


def _register_from_job_id(job_id: str) -> str:
    job = jobs_repo.get_job(job_id)
    if job is None:
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_FAILED,
            reason="job_not_found",
            last_error="job not found",
            increment_attempts=True,
        )
        return RECONCILE_FAILED
    return _register_job(job)


def _register_job(job: Job) -> str:
    job_id = job.id

    # Idempotent success path.
    existing = knowledge_repo.get_reconcile(job_id)
    link = knowledge_repo.get_job_link(job_id)
    if (
        existing is not None
        and existing.status == RECONCILE_REGISTERED
        and link is not None
        and link.unlinked_at is None
    ):
        return RECONCILE_REGISTERED

    if existing is not None and existing.status == RECONCILE_SKIPPED:
        if existing.reason in PERMANENT_SKIP_REASONS or (
            existing.reason and existing.reason.startswith("task_type_")
        ):
            return RECONCILE_SKIPPED

    if existing is not None and existing.status == RECONCILE_FAILED:
        if existing.attempts >= MAX_RECONCILE_ATTEMPTS:
            return RECONCILE_FAILED

    # Eligibility.
    if job.status != JobStatus.COMPLETED:
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_SKIPPED,
            reason="not_completed",
            last_error=None,
        )
        return RECONCILE_SKIPPED

    task_type = (job.options.task_type or "summary").strip()
    if task_type in SKIP_TASK_TYPES:
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_SKIPPED,
            reason=f"task_type_{task_type}",
            last_error=None,
        )
        return RECONCILE_SKIPPED

    if not job.summary_path:
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_SKIPPED,
            reason="missing_summary_path",
            last_error=None,
        )
        return RECONCILE_SKIPPED

    summary_path = Path(job.summary_path)
    if not summary_path.is_file():
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_FAILED,
            reason="summary_file_missing",
            last_error=f"summary file not found: {job.summary_path}",
            increment_attempts=True,
        )
        return RECONCILE_FAILED

    bvid = (job.bvid or "").strip()
    if not bvid or job.cid is None:
        knowledge_repo.set_reconcile(
            job_id,
            status=RECONCILE_FAILED,
            reason="missing_bvid_or_cid",
            last_error="bvid or cid missing",
            increment_attempts=True,
        )
        return RECONCILE_FAILED

    # Read legacy summary bytes (byte-identical copy into knowledge store).
    summary_bytes = summary_path.read_bytes()
    summary_hash = art.sha256_bytes(summary_bytes)

    transcript_payload = art.build_transcript_payload(
        job.transcript, subtitle_source=job.subtitle_source
    )
    transcript_bytes = art.encode_transcript_bytes(transcript_payload)
    transcript_hash = art.sha256_bytes(transcript_bytes)

    document_id = knowledge_repo.upsert_document(
        provider=PROVIDER_BILIBILI,
        external_bvid=bvid,
        external_cid=int(job.cid),
        title=job.title,
        author=job.author,
        mid=job.mid,
        source_url=job.url,
    )

    # Transcript artifact + content revision (reuse by hash).
    transcript_path = art.transcript_artifact_path(document_id, transcript_hash)
    art.ensure_bytes_on_disk(transcript_path, transcript_bytes)
    transcript_artifact_id = knowledge_repo.insert_artifact(
        document_id=document_id,
        kind=ARTIFACT_KIND_TRANSCRIPT_RAW,
        content_hash=transcript_hash,
        storage_path=str(transcript_path),
        byte_size=len(transcript_bytes),
    )
    content_revision_id = knowledge_repo.upsert_content_revision(
        document_id=document_id,
        artifact_id=transcript_artifact_id,
        content_hash=transcript_hash,
        subtitle_source=job.subtitle_source,
    )

    # Summary artifact + summary revision.
    summary_art_path = art.summary_artifact_path(document_id, summary_hash)
    art.ensure_bytes_on_disk(summary_art_path, summary_bytes)
    summary_artifact_id = knowledge_repo.insert_artifact(
        document_id=document_id,
        kind=ARTIFACT_KIND_SUMMARY,
        content_hash=summary_hash,
        storage_path=str(summary_art_path),
        byte_size=len(summary_bytes),
    )
    summary_revision_id = knowledge_repo.upsert_summary_revision(
        document_id=document_id,
        artifact_id=summary_artifact_id,
        content_hash=summary_hash,
        source_job_id=job_id,
    )

    # If link was unlinked, do not re-link (delete already happened semantics).
    # For normal first register, insert the link.
    knowledge_repo.upsert_job_link(
        job_id=job_id,
        document_id=document_id,
        summary_revision_id=summary_revision_id,
        content_revision_id=content_revision_id,
    )

    knowledge_repo.set_reconcile(
        job_id,
        status=RECONCILE_REGISTERED,
        reason=None,
        last_error=None,
    )
    logger.info(
        "knowledge registered job=%s document=%s summary=%s transcript=%s",
        job_id,
        document_id,
        summary_hash[:12],
        transcript_hash[:12],
    )
    return RECONCILE_REGISTERED
