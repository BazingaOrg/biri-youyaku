import asyncio
import logging
from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import Job, JobStatus

logger = logging.getLogger(__name__)

TERMINAL_DELETE_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.TRANSCRIPT_READY,
}


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


async def cleanup_once() -> dict[str, int]:
    now = repo.now_ms()
    audio_cutoff = now - settings.audio_retention_days * 24 * 60 * 60 * 1000
    job_cutoff = now - settings.job_retention_days * 24 * 60 * 60 * 1000
    audio_removed = 0
    jobs_removed = 0

    for job in repo.list_jobs_by_status(TERMINAL_DELETE_STATUSES):
        if job.audio_path and job.updated_at < audio_cutoff:
            delete_job_files(job, audio_only=True)
            repo.clear_audio_path(job.id)
            audio_removed += 1

    expired_jobs = repo.list_jobs_by_status_before(TERMINAL_DELETE_STATUSES, job_cutoff)
    for job in expired_jobs:
        delete_job_files(job)
        jobs_removed += repo.delete_job(job.id)

    return {"audio_removed": audio_removed, "jobs_removed": jobs_removed}


async def cleanup_loop() -> None:
    while True:
        try:
            await cleanup_once()
        except Exception:
            logger.exception("Cleanup loop failed")
        await asyncio.sleep(60 * 60)
