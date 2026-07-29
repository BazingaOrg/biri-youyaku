"""Knowledge registry constants and small shared types."""

from __future__ import annotations

from dataclasses import dataclass

PROVIDER_BILIBILI = "bilibili"

ARTIFACT_KIND_SUMMARY = "summary"
ARTIFACT_KIND_TRANSCRIPT_RAW = "transcript_raw"

RECONCILE_PENDING = "pending"
RECONCILE_REGISTERED = "registered"
RECONCILE_FAILED = "failed"
RECONCILE_SKIPPED = "skipped"

# task_type values that must never enter the knowledge registry.
SKIP_TASK_TYPES = frozenset({"distill", "audio"})

# Permanent skip reasons — reconcile will not re-attempt these jobs.
PERMANENT_SKIP_REASONS = frozenset(
    {
        "task_type_distill",
        "task_type_audio",
        "knowledge_register_disabled",
        "not_completed",
        "missing_summary_path",
    }
)

MAX_RECONCILE_ATTEMPTS = 5


@dataclass(frozen=True)
class JobLink:
    job_id: str
    document_id: str
    summary_revision_id: str | None
    content_revision_id: str | None
    linked_at: int
    unlinked_at: int | None


@dataclass(frozen=True)
class ReconcileRow:
    job_id: str
    status: str
    reason: str | None
    attempts: int
    last_error: str | None
    created_at: int
    updated_at: int
