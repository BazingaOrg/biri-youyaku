from pathlib import Path

from biri_youyaku.config import settings


def path_for(job_id: str) -> Path:
    directory = Path(settings.audio_storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / job_id
