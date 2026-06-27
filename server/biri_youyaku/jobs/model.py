from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from biri_youyaku.config import Settings


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


@dataclass(frozen=True)
class JobOptions:
    task_type: str = "summary"
    language: str = "auto"
    force_asr: bool = False
    summary_language: str = "中文简体"
    email_enabled: bool = True
    email_recipient: str | None = None
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
            email_recipient=settings.email_default_recipient,
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
            key: value
            for key, value in data.items()
            if key in allowed and value is not None
        }
        return cls.from_dict({**defaults, **overrides})

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "task_type": self.task_type,
            "force_asr": self.force_asr,
            "summary_language": self.summary_language,
            "email_enabled": self.email_enabled,
            "email_recipient": self.email_recipient,
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
    content_hash: str | None = None
    stage_timings: list[dict[str, Any]] | None = None
    email_error: str | None = None
    tags: list[str] | None = None
