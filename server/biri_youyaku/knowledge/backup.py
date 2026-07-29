"""Local consistent knowledge backup helpers (Phase D, pre-cloud)."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.db import connect
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.knowledge.lifecycle import ACTION_BACKUP, record_audit

logger = logging.getLogger("biri_youyaku.knowledge.backup")


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(path)
    return files


def _relative_key(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path)


def build_file_manifest(paths: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    """List of {path, sha256, bytes} for existing files; missing → sha256 null."""
    entries: list[dict[str, Any]] = []
    for rel, path in paths:
        if path.is_file():
            entries.append(
                {
                    "path": rel,
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
        else:
            entries.append({"path": rel, "sha256": None, "bytes": 0, "missing": True})
    return entries


def create_backup(
    *,
    dry_run: bool = False,
    backup_dir: Path | None = None,
    actor: str = "api",
) -> dict[str, Any]:
    """Create a consistent backup: sqlite backup API + knowledge artifacts + manifest.

    Layout under ``backup_dir/<timestamp>/``:
      - biri_youyaku.db
      - knowledge/  (copy of knowledge_storage_dir when present)
      - summaries/  (optional copy of summary_storage_dir when present)
      - manifest.json

    dry_run: compute hashes of live sources and return planned layout without writing.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(backup_dir or settings.knowledge_backup_dir)
    dest = root / stamp

    db_path = Path(settings.db_path)
    knowledge_root = Path(settings.knowledge_storage_dir)
    summary_root = Path(settings.summary_storage_dir)

    source_entries: list[tuple[str, Path]] = [("biri_youyaku.db", db_path)]
    for path in _iter_files(knowledge_root):
        source_entries.append(
            (f"knowledge/{_relative_key(path, knowledge_root)}", path)
        )
    for path in _iter_files(summary_root):
        source_entries.append(
            (f"summaries/{_relative_key(path, summary_root)}", path)
        )

    live_manifest = build_file_manifest(source_entries)
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "timestamp": stamp,
        "backup_dir": str(dest),
        "manifest": live_manifest,
        "file_count": len([e for e in live_manifest if not e.get("missing")]),
        "total_bytes": sum(int(e.get("bytes") or 0) for e in live_manifest),
    }

    if dry_run:
        record_audit(
            ACTION_BACKUP,
            document_id=None,
            detail={
                "dry_run": True,
                "timestamp": stamp,
                "file_count": result["file_count"],
                "total_bytes": result["total_bytes"],
            },
            actor=actor,
        )
        return result

    dest.mkdir(parents=True, exist_ok=True)
    dest_db = dest / "biri_youyaku.db"

    # Consistent SQLite snapshot via backup API (handles WAL safely).
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    # Prefer live connection backup so we include committed app state.
    src = connect()
    dest_conn = sqlite3.connect(str(dest_db))
    try:
        src.backup(dest_conn)
        dest_conn.commit()
    finally:
        dest_conn.close()

    if knowledge_root.exists():
        shutil.copytree(
            knowledge_root,
            dest / "knowledge",
            dirs_exist_ok=True,
        )
    if summary_root.exists():
        shutil.copytree(
            summary_root,
            dest / "summaries",
            dirs_exist_ok=True,
        )

    # Re-hash written backup tree for restore verification.
    backup_entries: list[tuple[str, Path]] = [("biri_youyaku.db", dest_db)]
    for path in _iter_files(dest / "knowledge"):
        backup_entries.append(
            (f"knowledge/{_relative_key(path, dest / 'knowledge')}", path)
        )
    for path in _iter_files(dest / "summaries"):
        backup_entries.append(
            (f"summaries/{_relative_key(path, dest / 'summaries')}", path)
        )
    backup_manifest = build_file_manifest(backup_entries)
    manifest_payload = {
        "created_at": now_ms(),
        "timestamp": stamp,
        "source_db": str(db_path),
        "source_knowledge": str(knowledge_root),
        "source_summaries": str(summary_root),
        "files": backup_manifest,
        "file_count": len(backup_manifest),
        "total_bytes": sum(int(e.get("bytes") or 0) for e in backup_manifest),
        "restore_hint": (
            "Stop the server. Replace data/biri_youyaku.db with the backup DB "
            "(prefer sqlite3 .backup restore or file replace while stopped). "
            "Restore knowledge/ under KNOWLEDGE_STORAGE_DIR and summaries/ under "
            "SUMMARY_STORAGE_DIR. Restart; run POST /v1/knowledge/reindex if FTS empty."
        ),
    }
    manifest_path = dest / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result["manifest"] = backup_manifest
    result["manifest_path"] = str(manifest_path)
    result["db_path"] = str(dest_db)
    result["file_count"] = manifest_payload["file_count"]
    result["total_bytes"] = manifest_payload["total_bytes"]

    record_audit(
        ACTION_BACKUP,
        document_id=None,
        detail={
            "dry_run": False,
            "timestamp": stamp,
            "backup_dir": str(dest),
            "manifest_path": str(manifest_path),
            "file_count": result["file_count"],
            "total_bytes": result["total_bytes"],
        },
        actor=actor,
    )
    logger.info(
        "knowledge backup written to %s (%d files, %d bytes)",
        dest,
        result["file_count"],
        result["total_bytes"],
    )
    return result
