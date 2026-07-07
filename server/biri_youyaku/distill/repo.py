import json
import uuid
from typing import Any

from biri_youyaku.db import connect
from biri_youyaku.distill.model import (
    DistillRun,
    DistillRunStatus,
    TERMINAL_DISTILL_RUN_STATUSES,
    default_counters,
)
from biri_youyaku.jobs.repo import now_ms


def _row_to_run(row) -> DistillRun:
    counters_raw = row["counters_json"]
    counters = json.loads(counters_raw) if counters_raw else default_counters()
    return DistillRun(
        id=row["id"],
        mid=row["mid"],
        up_name=row["up_name"],
        status=DistillRunStatus(row["status"]),
        video_limit=row["video_limit"],
        dynamics_status=row["dynamics_status"],
        counters=counters,
        error=row["error"],
        dir_path=row["dir_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_run(mid: int, *, video_limit: int, dir_path: str) -> DistillRun:
    timestamp = now_ms()
    run = DistillRun(
        id=str(uuid.uuid4()),
        mid=mid,
        status=DistillRunStatus.PENDING,
        video_limit=video_limit,
        dir_path=dir_path,
        created_at=timestamp,
        updated_at=timestamp,
    )
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO distill_runs (
              id, mid, up_name, status, video_limit, dynamics_status,
              counters_json, error, dir_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.mid,
                run.up_name,
                run.status.value,
                run.video_limit,
                run.dynamics_status,
                json.dumps(run.counters, ensure_ascii=False),
                run.error,
                run.dir_path,
                timestamp,
                timestamp,
            ),
        )
    return run


def get_run(run_id: str) -> DistillRun | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM distill_runs WHERE id = ?", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def find_active_by_mid(mid: int) -> DistillRun | None:
    """同一 mid 是否已有非终态 run（用于 start_run 时拒绝重复启动）。"""
    placeholders = ",".join("?" for _ in TERMINAL_DISTILL_RUN_STATUSES)
    values = [status.value for status in TERMINAL_DISTILL_RUN_STATUSES]
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT * FROM distill_runs
            WHERE mid = ? AND status NOT IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (mid, *values),
        ).fetchone()
    return _row_to_run(row) if row else None


def latest_by_mid(mid: int) -> DistillRun | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM distill_runs WHERE mid = ? ORDER BY created_at DESC LIMIT 1",
            (mid,),
        ).fetchone()
    return _row_to_run(row) if row else None


def list_unfinished_runs() -> list[DistillRun]:
    """启动恢复用：所有非终态 run。"""
    placeholders = ",".join("?" for _ in TERMINAL_DISTILL_RUN_STATUSES)
    values = [status.value for status in TERMINAL_DISTILL_RUN_STATUSES]
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM distill_runs
            WHERE status NOT IN ({placeholders})
            ORDER BY created_at ASC
            """,
            values,
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def update_status(run_id: str, status: DistillRunStatus, *, error: str | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE distill_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status.value, error, now_ms(), run_id),
        )


def set_up_name(run_id: str, up_name: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE distill_runs SET up_name = ?, updated_at = ? WHERE id = ?",
            (up_name, now_ms(), run_id),
        )


def set_dynamics_status(run_id: str, dynamics_status: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE distill_runs SET dynamics_status = ?, updated_at = ? WHERE id = ?",
            (dynamics_status, now_ms(), run_id),
        )


def update_counters(run_id: str, **updates: Any) -> dict[str, Any]:
    """局部更新 counters JSON 里的几个 key，返回更新后的完整 counters。"""
    run = get_run(run_id)
    if run is None:
        raise RuntimeError(f"Distill run {run_id} not found")
    counters = {**run.counters, **updates}
    with connect() as connection:
        connection.execute(
            "UPDATE distill_runs SET counters_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(counters, ensure_ascii=False), now_ms(), run_id),
        )
    return counters


def add_failed_bvid(run_id: str, bvid: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise RuntimeError(f"Distill run {run_id} not found")
    failed = list(run.counters.get("failed_bvids") or [])
    if bvid not in failed:
        failed.append(bvid)
    return update_counters(
        run_id,
        failed_bvids=failed,
        videos_failed=len(failed),
    )


def delete_run(run_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM distill_runs WHERE id = ?", (run_id,))
