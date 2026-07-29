import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.db import connect, maintenance_connection
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import (
    AUTO_JOB_DELETE_STATUSES,
    Job,
    JobStatus,
    RETENTION_DELETE_JOB_STATUSES,
)
from biri_youyaku.jobs.runner import has_active_task
from biri_youyaku.weekly import repo as weekly_summary_repo

logger = logging.getLogger(__name__)


def is_auto_job_purge_eligible(job: Job) -> bool:
    """A0: auto-delete job rows only for FAILED/CANCELED with no durable summary.

    COMPLETED and any job with summary_path are retained indefinitely until
    explicit user delete. TRANSCRIPT_READY is never auto-purged.
    """
    if job.status == JobStatus.COMPLETED:
        return False
    if job.summary_path is not None:
        return False
    return job.status in AUTO_JOB_DELETE_STATUSES


# --- 单 job 文件级清理 ---------------------------------------------------------


def delete_job_files(job: Job, *, audio_only: bool = False) -> None:
    if job.audio_path:
        audio_path = Path(job.audio_path)
        try:
            if audio_path.is_file():
                audio_path.unlink()
            for sibling in audio_path.parent.glob(f"{job.id}*"):
                if sibling.is_file():
                    sibling.unlink()
        except OSError:
            logger.warning("Failed to remove audio files for job %s", job.id, exc_info=True)
    if not audio_only and job.summary_path:
        summary_path = Path(job.summary_path)
        try:
            if summary_path.is_file():
                summary_path.unlink()
        except OSError:
            logger.warning("Failed to remove summary file for job %s", job.id, exc_info=True)


def collect_job_file_cleanup_targets(job: Job) -> list[dict[str, str]]:
    """Snapshot every known file before a bulk-delete transaction commits."""
    targets: list[dict[str, str]] = []
    if job.audio_path:
        audio_path = Path(job.audio_path)
        targets.append({"job_id": job.id, "file_type": "audio", "path": str(audio_path)})
        try:
            siblings = list(audio_path.parent.glob(f"{job.id}*"))
        except OSError:
            logger.warning("Failed to list audio files for job %s", job.id, exc_info=True)
            targets.append(
                {
                    "job_id": job.id,
                    "file_type": "audio_siblings",
                    "path": str(audio_path.parent),
                }
            )
        else:
            targets.extend(
                {"job_id": job.id, "file_type": "audio", "path": str(sibling)}
                for sibling in siblings
                if sibling.is_file()
            )
    if job.summary_path:
        targets.append({"job_id": job.id, "file_type": "summary", "path": job.summary_path})
    return targets


def delete_job_file_targets_with_result(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """Delete a pre-commit file snapshot and return any post-commit failures."""
    failures: list[dict[str, str]] = []
    for target in targets:
        path = Path(target["path"])
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            logger.warning(
                "Failed to remove %s file for job %s", target["file_type"], target["job_id"], exc_info=True
            )
            failures.append(target)
    return failures


def delete_job_files_with_result(job: Job) -> list[dict[str, str]]:
    """Compatibility wrapper for callers that do not need transaction snapshots."""
    return delete_job_file_targets_with_result(collect_job_file_cleanup_targets(job))


def enqueue_pending_file_cleanup(failures: list[dict[str, str]]) -> None:
    """Persist post-commit failures so maintenance can retry them immediately.

    The caller has already committed job deletion.  Paths stay internal and are
    never sent to the browser, while the returned API response reports a count
    and file type for observability.
    """
    now = repo.now_ms()
    rows = [
        (failure["path"], failure["job_id"], failure["file_type"], now, now)
        for failure in failures
        if failure.get("path")
    ]
    if not rows:
        return
    with connect() as connection:
        connection.executemany(
            """INSERT INTO pending_file_cleanup (path, job_id, file_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET job_id=excluded.job_id, file_type=excluded.file_type,
                 updated_at=excluded.updated_at""",
            rows,
        )


def retry_pending_file_cleanup_once() -> int:
    """Retry every explicitly recorded post-commit cleanup failure once."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT path, job_id, file_type FROM pending_file_cleanup ORDER BY updated_at, path"
        ).fetchall()
    removed = 0
    for row in rows:
        path = Path(row["path"])
        try:
            if row["file_type"] == "audio_siblings":
                for sibling in path.glob(f"{row['job_id']}*"):
                    if sibling.is_file():
                        sibling.unlink()
            elif path.is_file():
                path.unlink()
        except OSError as exc:
            with connect() as connection:
                connection.execute(
                    "UPDATE pending_file_cleanup SET attempts=attempts+1, updated_at=?, last_error=? WHERE path=?",
                    (repo.now_ms(), str(exc)[:1000], str(path)),
                )
            logger.warning("Failed to retry pending file cleanup for %s", path, exc_info=True)
        else:
            with connect() as connection:
                connection.execute("DELETE FROM pending_file_cleanup WHERE path=?", (str(path),))
            removed += 1
    return removed


# --- 主循环：每轮做哪些事 -------------------------------------------------------


async def cleanup_once() -> dict[str, int]:
    """每小时跑一次的「文件级 + 任务级」常规清理。

    A0 retention matrix (automatic only; manual delete unchanged):
    - audio_path: after audio_retention_days, delete file(s) and clear path; job stays
    - COMPLETED or summary_path set: never auto-delete job/summary/transcript
    - TRANSCRIPT_READY: never auto-delete
    - FAILED/CANCELED with no summary: after job_retention_days, delete files + row
    """
    now = repo.now_ms()
    audio_cutoff = now - settings.audio_retention_days * 24 * 60 * 60 * 1000
    job_cutoff = now - settings.job_retention_days * 24 * 60 * 60 * 1000
    audio_removed = 0
    jobs_removed = 0

    for job in repo.list_jobs_by_status(RETENTION_DELETE_JOB_STATUSES):
        if job.audio_path and job.updated_at < audio_cutoff:
            delete_job_files(job, audio_only=True)
            repo.clear_audio_path(job.id)
            audio_removed += 1

    expired_jobs = repo.list_jobs_by_status_before(AUTO_JOB_DELETE_STATUSES, job_cutoff)
    for job in expired_jobs:
        if not is_auto_job_purge_eligible(job):
            continue
        delete_job_files(job)
        weekly_summary_repo.mark_stale_for_job_ids([job.id])
        jobs_removed += repo.delete_job(job.id)

    return {"audio_removed": audio_removed, "jobs_removed": jobs_removed}


# --- P3 新增：僵尸任务、孤儿文件、DB 维护 -----------------------------------


async def fail_stale_running_once() -> int:
    """非终态任务长时间 `updated_at` 不动 → 视为僵尸，置 FAILED。

    避免 SenseVoice 死锁、yt-dlp hang 这类不抛异常的卡死把 job 永远留在中间态。
    """
    hours = max(1, settings.stale_running_fail_hours)
    cutoff = repo.now_ms() - hours * 60 * 60 * 1000
    count = 0
    for job in repo.list_running_jobs_stale_before(cutoff):
        if has_active_task(job.id):
            continue
        if repo.fail_stale_running_job(
            job.id,
            expected_status=job.status,
            cutoff_ms=cutoff,
            message=f"任务在 {hours}h 内无心跳，已自动置 FAILED",
        ):
            count += 1
    if count:
        logger.info("Marked %d stale running jobs as FAILED", count)
    return count


def _scan_orphan_files(directory: Path, known_paths: set[str], retention_days: int) -> int:
    """删除 directory 下「DB 不再引用且 mtime 比 retention_days 早」的文件。

    既清掉手动 DELETE / 异常退出留下的死文件，也不会误伤刚写入但还没回 DB 的文件。
    """
    if not directory.exists():
        return 0
    cutoff_seconds = retention_days * 24 * 60 * 60
    removed = 0
    # 文件 mtime 是真实时间，必须用 time.time() 比对（不是 loop time）
    now_seconds = time.time()
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        path_str = str(entry)
        if path_str in known_paths:
            continue
        try:
            if now_seconds - entry.stat().st_mtime < cutoff_seconds:
                continue
            entry.unlink()
            removed += 1
        except OSError:
            logger.warning("Failed to remove orphan file %s", entry, exc_info=True)
    return removed


def _scan_orphan_distill_dirs(directory: Path, retention_days: int) -> int:
    """删除 directory 下「distill_runs 表无 mid 记录且 mtime 比 retention_days 早」的子目录。

    与 `_scan_orphan_files` 同一套「DB 不引用 + 过了保留期才删」的规则，只是这里
    校验对象是 `<mid>` 子目录而非单个文件。
    """
    if not directory.exists():
        return 0
    cutoff_seconds = retention_days * 24 * 60 * 60
    removed = 0
    now_seconds = time.time()
    for entry in directory.iterdir():
        if not entry.is_dir():
            continue
        try:
            mid = int(entry.name)
        except ValueError:
            continue
        if distill_repo.mid_has_run(mid):
            continue
        try:
            if now_seconds - entry.stat().st_mtime < cutoff_seconds:
                continue
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            logger.warning("Failed to remove orphan distill dir %s", entry, exc_info=True)
    return removed


async def scan_orphans_once() -> dict[str, int]:
    """文件 → DB 反向校验：DB 不引用的文件清掉。"""
    retry_pending_file_cleanup_once()
    retention = max(0, settings.orphan_file_retention_days)
    audio_dir = Path(settings.audio_storage_dir)
    summary_dir = Path(settings.summary_storage_dir)
    distill_dir = Path(settings.distill_storage_dir)
    audio_known = repo.all_audio_paths()
    summary_known = repo.all_summary_paths()
    audio_orphans = _scan_orphan_files(audio_dir, audio_known, retention)
    summary_orphans = _scan_orphan_files(summary_dir, summary_known, retention)
    distill_orphans = _scan_orphan_distill_dirs(distill_dir, retention)
    if audio_orphans or summary_orphans or distill_orphans:
        logger.info(
            "Removed orphans: audio=%d summary=%d distill=%d",
            audio_orphans,
            summary_orphans,
            distill_orphans,
        )
    return {
        "audio_orphans": audio_orphans,
        "summary_orphans": summary_orphans,
        "distill_orphans": distill_orphans,
    }


def clean_tempfile_residues() -> int:
    """lifespan 启动期一次性清掉上次进程异常退出留下的 tempfile 残留。"""
    tmp = Path(tempfile.gettempdir())
    removed = 0
    for pattern in ("biri-youyaku-bili-*.cookies.txt", "biri_asr_*"):
        for entry in tmp.glob(pattern):
            try:
                if entry.is_file():
                    entry.unlink()
                    removed += 1
                elif entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                logger.warning("Failed to remove tempfile residue %s", entry, exc_info=True)
    if removed:
        logger.info("Cleared %d tempfile residue entries", removed)
    return removed


def _checkpoint_wal_sync() -> None:
    with maintenance_connection() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


async def checkpoint_wal() -> None:
    """`PRAGMA wal_checkpoint(TRUNCATE)`：把 WAL 文件截断回 0 字节，避免长跑膨胀。"""
    try:
        await asyncio.to_thread(_checkpoint_wal_sync)
    except Exception:
        logger.exception("wal_checkpoint failed")


def _vacuum_db_sync() -> None:
    with maintenance_connection() as connection:
        connection.execute("VACUUM")


async def vacuum_db() -> None:
    """`VACUUM`：回收已删除行的页。比较重，跑得稀疏些。"""
    try:
        await asyncio.to_thread(_vacuum_db_sync)
    except Exception:
        logger.exception("VACUUM failed")


# --- 调度循环 -------------------------------------------------------------------

async def cleanup_loop() -> None:
    """`lifespan` 启动后台跑的清理循环。

    单循环内时序：
        每 N 秒：cleanup_once + fail_stale_running + scan_orphans
        每 wal_checkpoint_interval_hours：checkpoint_wal
        每 db_vacuum_interval_days：vacuum_db

    WAL/VACUUM 用 monotonic wall-clock 跟踪，避免「上一轮 cleanup 跑了几分钟」把
    维护时点逻辑性地推迟掉。
    """
    interval = max(60, settings.cleanup_interval_seconds)
    wal_every = max(1, settings.wal_checkpoint_interval_hours) * 3600
    vacuum_every = max(1, settings.db_vacuum_interval_days) * 24 * 3600
    last_wal = time.monotonic()
    last_vacuum = time.monotonic()
    # lifespan 启动期已经手动跑过一遍常规清理，循环先 sleep 再做活，避免双跑
    while True:
        await asyncio.sleep(interval)
        try:
            await cleanup_once()
            await fail_stale_running_once()
            await scan_orphans_once()
            # A3 knowledge reconcile: best-effort register pending completed jobs.
            try:
                from biri_youyaku.knowledge import reconcile_once

                reconcile_once(limit=50)
            except Exception:
                logger.exception("knowledge reconcile in cleanup_loop failed")
        except Exception:
            logger.exception("Cleanup loop tick failed")
        now = time.monotonic()
        if now - last_wal >= wal_every:
            await checkpoint_wal()
            last_wal = time.monotonic()
        if now - last_vacuum >= vacuum_every:
            await vacuum_db()
            last_vacuum = time.monotonic()
