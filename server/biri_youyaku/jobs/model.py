from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from biri_youyaku.config import Settings
from biri_youyaku.modules.bilibili.meta import VideoMeta


class JobStatus(StrEnum):
    PENDING = "PENDING"
    FETCHING_META = "FETCHING_META"
    DOWNLOADING_AUDIO = "DOWNLOADING_AUDIO"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIPT_READY = "TRANSCRIPT_READY"
    SUMMARIZING = "SUMMARIZING"
    EMAILING = "EMAILING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
)
TERMINAL_JOB_STATUS_VALUES = frozenset(status.value for status in TERMINAL_JOB_STATUSES)

# TRANSCRIPT_READY is persisted as a boundary state: it is handled by a dedicated
# resume path on startup, but it is not a final user-visible outcome.
PAUSED_OR_TERMINAL_JOB_STATUSES = TERMINAL_JOB_STATUSES | frozenset({JobStatus.TRANSCRIPT_READY})

# Manual single-delete eligibility (routes/jobs.py) and auto audio-sweep candidates.
# Includes COMPLETED / TRANSCRIPT_READY so users can still delete finished work.
# Auto job-row purge does NOT use this set — see AUTO_JOB_DELETE_STATUSES.
RETENTION_DELETE_JOB_STATUSES = PAUSED_OR_TERMINAL_JOB_STATUSES

# A0 auto job-row purge: only terminal failures/cancels without durable content.
# COMPLETED and TRANSCRIPT_READY are never auto-deleted; jobs with summary_path
# are also kept (defensive check in cleanup.is_auto_job_purge_eligible).
AUTO_JOB_DELETE_STATUSES = frozenset({JobStatus.FAILED, JobStatus.CANCELED})

# 用户从历史页发起的批量删除只覆盖已经结束的主任务。它刻意不复用
# RETENTION_DELETE_JOB_STATUSES：TRANSCRIPT_READY 仍可继续总结，不应被当作历史清理掉。
BULK_DELETE_JOB_STATUSES = TERMINAL_JOB_STATUSES


@dataclass(frozen=True)
class JobOptions:
    task_type: str = "summary"
    language: str = "auto"
    force_asr: bool = False
    summary_language: str = "中文简体"
    email_enabled: bool = True
    email_subject_template: str = "[Biri-Youyaku] {{title}}"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"
    prompt_template: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobOptions":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})

    @classmethod
    def from_settings(cls, settings: Settings) -> "JobOptions":
        return cls(
            task_type="summary",
            language=settings.asr_language_default,
            force_asr=False,
            summary_language=settings.summary_language,
            email_enabled=settings.email_enabled,
            email_subject_template=settings.email_subject_template,
            llm_base_url=settings.llm_base_url,
            llm_model=settings.llm_model,
            prompt_template=None,
        )

    @classmethod
    def from_overrides(cls, data: dict[str, Any], settings: Settings) -> "JobOptions":
        defaults = cls.from_settings(settings).as_dict()
        allowed = cls.__dataclass_fields__.keys()
        overrides = {
            key: value for key, value in data.items() if key in allowed and value is not None
        }
        return cls.from_dict({**defaults, **overrides})

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "task_type": self.task_type,
            "force_asr": self.force_asr,
            "summary_language": self.summary_language,
            "email_enabled": self.email_enabled,
            "email_subject_template": self.email_subject_template,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "prompt_template": self.prompt_template,
        }


@dataclass(frozen=True)
class Job:
    id: str
    url: str
    status: JobStatus
    options: JobOptions
    created_at: int
    updated_at: int
    option_overrides: dict[str, Any] | None = None
    bvid: str | None = None
    cid: int | None = None
    mid: int | None = None
    title: str | None = None
    author: str | None = None
    duration: float | None = None
    error_stage: str | None = None
    error_message: str | None = None
    error_code: str | None = None
    audio_path: str | None = None
    subtitle_source: str | None = None
    chapters: list[dict[str, Any]] | None = None
    transcript: list[dict[str, Any]] | None = None
    summary_path: str | None = None
    completed_at: int | None = None
    stream_finished_at: int | None = None
    token_usage: dict[str, Any] | None = None
    stage_timings: list[dict[str, Any]] | None = None
    email_error: str | None = None
    tags: list[str] | None = None


def video_meta_from_job(job: "Job") -> VideoMeta:
    return VideoMeta(
        url=job.url,
        bvid=job.bvid or "",
        cid=job.cid,
        title=job.title or job.bvid or job.id,
        author=job.author or "",
        duration=job.duration or 0,
    )
