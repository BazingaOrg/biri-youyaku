from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DistillRunStatus(StrEnum):
    PENDING = "PENDING"
    FETCHING_DYNAMICS = "FETCHING_DYNAMICS"
    PREPARING_TRANSCRIPTS = "PREPARING_TRANSCRIPTS"
    EXTRACTING = "EXTRACTING"
    ASSEMBLING = "ASSEMBLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_DISTILL_RUN_STATUSES = frozenset(
    {
        DistillRunStatus.COMPLETED,
        DistillRunStatus.FAILED,
        DistillRunStatus.CANCELLED,
    }
)
TERMINAL_DISTILL_RUN_STATUS_VALUES = frozenset(
    status.value for status in TERMINAL_DISTILL_RUN_STATUSES
)


def default_counters() -> dict[str, Any]:
    return {
        "videos_total": 0,
        "videos_transcribed": 0,
        "videos_extracted": 0,
        "videos_failed": 0,
        "dynamics_count": 0,
        # 失败视频的 bvid 列表；没有单独的 DB 列（spec 只列了 counters 一个 JSON
        # 字段涵盖计数），塞在这个 dict 里一起持久化最省事，assembler.py 组装
        # manifest 时直接读这个 key 填 failed 列表。
        "failed_bvids": [],
    }


@dataclass(frozen=True)
class DistillRun:
    id: str
    mid: int
    status: DistillRunStatus
    video_limit: int
    dir_path: str
    created_at: int
    updated_at: int
    up_name: str | None = None
    dynamics_status: str | None = None
    counters: dict[str, Any] = field(default_factory=default_counters)
    error: str | None = None
