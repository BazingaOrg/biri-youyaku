from pathlib import Path

from biri_youyaku.config import settings


def save(job_id: str, summary_md: str) -> Path:
    directory = Path(settings.summary_storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job_id}.md"
    path.write_text(summary_md, encoding="utf-8")
    return path
