from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.modules.storage.atomic import atomic_write_text


def save(job_id: str, summary_md: str) -> Path:
    directory = Path(settings.summary_storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job_id}.md"
    atomic_write_text(path, summary_md)
    return path
