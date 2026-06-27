import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobStatus, RETENTION_DELETE_JOB_STATUSES

logger = logging.getLogger(__name__)


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


# --- 主循环：每轮做哪些事 -------------------------------------------------------


async def cleanup_once() -> dict[str, int]:
    """每小时跑一次的「文件级 + 任务级」常规清理。"""
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

    expired_jobs = repo.list_jobs_by_status_before(RETENTION_DELETE_JOB_STATUSES, job_cutoff)
    for job in expired_jobs:
        delete_job_files(job)
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
        repo.set_error(
            job.id,
            stage=job.status.value,
            message=f"任务在 {hours}h 内无心跳，已自动置 FAILED",
            code="STAGE_STUCK",
        )
        repo.update_status(job.id, JobStatus.FAILED)
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


async def scan_orphans_once() -> dict[str, int]:
    """文件 → DB 反向校验：DB 不引用的文件清掉。"""
    retention = max(0, settings.orphan_file_retention_days)
    audio_dir = Path(settings.audio_storage_dir)
    summary_dir = Path(settings.summary_storage_dir)
    audio_known = repo.all_audio_paths()
    summary_known = repo.all_summary_paths()
    audio_orphans = _scan_orphan_files(audio_dir, audio_known, retention)
    summary_orphans = _scan_orphan_files(summary_dir, summary_known, retention)
    if audio_orphans or summary_orphans:
        logger.info("Removed orphans: audio=%d summary=%d", audio_orphans, summary_orphans)
    return {"audio_orphans": audio_orphans, "summary_orphans": summary_orphans}


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


async def checkpoint_wal() -> None:
    """`PRAGMA wal_checkpoint(TRUNCATE)`：把 WAL 文件截断回 0 字节，避免长跑膨胀。"""
    try:
        with connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        logger.exception("wal_checkpoint failed")


async def vacuum_db() -> None:
    """`VACUUM`：回收已删除行的页。比较重，跑得稀疏些。"""
    try:
        with connect() as connection:
            connection.execute("VACUUM")
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
        except Exception:
            logger.exception("Cleanup loop tick failed")
        now = time.monotonic()
        if now - last_wal >= wal_every:
            await checkpoint_wal()
            last_wal = time.monotonic()
        if now - last_vacuum >= vacuum_every:
            await vacuum_db()
            last_vacuum = time.monotonic()
