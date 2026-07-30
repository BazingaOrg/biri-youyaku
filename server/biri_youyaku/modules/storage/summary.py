from pathlib import Path

from biri_youyaku.config import settings
from biri_youyaku.modules.storage.atomic import atomic_write_text


def summary_root() -> Path:
    return Path(settings.summary_storage_dir)


def to_stored_path(path: Path | str, *, root: Path | None = None) -> str:
    """Return POSIX path relative to summary root when under root; else absolute POSIX."""
    base = (root or summary_root()).resolve()
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_stored_path(stored: str | Path, *, root: Path | None = None) -> Path:
    """If stored is absolute → use as-is (legacy). If relative → summary_root() / stored."""
    path = Path(stored)
    if path.is_absolute():
        return path
    base = root if root is not None else summary_root()
    return Path(base) / path


def rewrite_summary_paths_in_db() -> dict[str, int]:
    """Rewrite absolute jobs.summary_path under summary root to relative.

    Returns counts: total, rewritten, already_relative, outside_root, null_skipped.
    """
    from biri_youyaku.db import connect

    root = summary_root().resolve()
    total = 0
    rewritten = 0
    already_relative = 0
    outside_root = 0
    null_skipped = 0
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, summary_path FROM jobs WHERE summary_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            total += 1
            stored = row["summary_path"]
            if not stored:
                null_skipped += 1
                continue
            path = Path(stored)
            if not path.is_absolute():
                already_relative += 1
                continue
            try:
                rel = path.expanduser().resolve().relative_to(root).as_posix()
            except ValueError:
                outside_root += 1
                continue
            if rel == stored:
                already_relative += 1
                continue
            connection.execute(
                "UPDATE jobs SET summary_path = ? WHERE id = ?",
                (rel, row["id"]),
            )
            rewritten += 1
    return {
        "total": total,
        "rewritten": rewritten,
        "already_relative": already_relative,
        "outside_root": outside_root,
        "null_skipped": null_skipped,
    }


def save(job_id: str, summary_md: str) -> Path:
    directory = summary_root()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job_id}.md"
    atomic_write_text(path, summary_md)
    return path
