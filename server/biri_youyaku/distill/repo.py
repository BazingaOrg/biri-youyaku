import json
import uuid
from collections.abc import Collection
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


def update_status(
    run_id: str,
    status: DistillRunStatus,
    *,
    error: str | None = None,
    expected_status: DistillRunStatus | Collection[DistillRunStatus] | None = None,
) -> bool:
    """原子更新状态，且绝不把终态改回非终态。

    ``expected_status`` 用于调用者做 compare-and-swap，返回值表示本次是否实际写入。
    """
    terminal_values = [item.value for item in TERMINAL_DISTILL_RUN_STATUSES]
    clauses = ["id = ?", f"status NOT IN ({','.join('?' for _ in terminal_values)})"]
    values: list[Any] = [status.value, error, now_ms(), run_id, *terminal_values]
    if expected_status is not None:
        expected = (
            [expected_status]
            if isinstance(expected_status, DistillRunStatus)
            else list(expected_status)
        )
        if not expected:
            return False
        clauses.append(f"status IN ({','.join('?' for _ in expected)})")
        values.extend(item.value for item in expected)
    with connect() as connection:
        result = connection.execute(
            f"UPDATE distill_runs SET status = ?, error = ?, updated_at = ? WHERE {' AND '.join(clauses)}",
            values,
        )
    return result.rowcount == 1


def set_up_name(run_id: str, up_name: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE distill_runs SET up_name = ?, updated_at = ? WHERE id = ?",
            (up_name, now_ms(), run_id),
        )


def update_counters(run_id: str, **updates: Any) -> dict[str, Any]:
    """Atomically merge *updates* into the counters JSON column.

    Wraps the read-modify-write in a transaction so concurrent phase tasks
    (``_obtain_one`` / ``_extract_one``) cannot lose counter increments or
    overwrite each other's ``failed_bvids``.
    """
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT counters_json FROM distill_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Distill run {run_id} not found")
        counters = {**json.loads(row["counters_json"] or "{}"), **updates}
        connection.execute(
            "UPDATE distill_runs SET counters_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(counters, ensure_ascii=False), now_ms(), run_id),
        )
    return counters


def add_failed_bvid(run_id: str, bvid: str) -> dict[str, Any]:
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT counters_json FROM distill_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Distill run {run_id} not found")
        counters = json.loads(row["counters_json"] or "{}")
        failed = list(counters.get("failed_bvids") or [])
        if bvid not in failed:
            failed.append(bvid)
        counters = {**counters, "failed_bvids": failed, "videos_failed": len(failed)}
        connection.execute(
            "UPDATE distill_runs SET counters_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(counters, ensure_ascii=False), now_ms(), run_id),
        )
    return counters


def list_runs_by_mid(mid: int) -> list[DistillRun]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM distill_runs WHERE mid = ? ORDER BY created_at ASC", (mid,)
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def mid_has_run(mid: int) -> bool:
    with connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM distill_runs WHERE mid = ? LIMIT 1", (mid,)
        ).fetchone()
    return row is not None


def delete_run(run_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM distill_runs WHERE id = ?", (run_id,))
