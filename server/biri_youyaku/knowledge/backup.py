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
            "Stop the server. From server/: "
            "uv run python scripts/knowledge_restore.py --from <this_dir> "
            "(or --dry-run / --force). Then restart; POST /v1/knowledge/reindex if FTS empty."
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


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    """Load manifest.json under backup_dir and re-hash each listed file.

    Returns ok, checked, ok_count, mismatches, missing, and optional error.
    """
    backup_dir = Path(backup_dir)
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        return {
            "ok": False,
            "error": f"manifest.json not found under {backup_dir}",
            "checked": 0,
            "ok_count": 0,
            "mismatches": [],
            "missing": [],
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": f"failed to read manifest: {exc}",
            "checked": 0,
            "ok_count": 0,
            "mismatches": [],
            "missing": [],
        }

    files = payload.get("files") or []
    mismatches: list[dict[str, Any]] = []
    missing: list[str] = []
    ok_count = 0
    for entry in files:
        rel = str(entry.get("path") or "")
        if not rel:
            continue
        expected = entry.get("sha256")
        path = backup_dir / rel
        if not path.is_file():
            missing.append(rel)
            continue
        actual = _sha256_file(path)
        if expected is None:
            if entry.get("missing"):
                # Manifest marked source missing; file now present is odd but not a hash fail.
                ok_count += 1
            else:
                mismatches.append(
                    {"path": rel, "expected": None, "actual": actual, "reason": "no_expected_hash"}
                )
            continue
        if actual != expected:
            mismatches.append({"path": rel, "expected": expected, "actual": actual})
        else:
            ok_count += 1

    return {
        "ok": len(mismatches) == 0 and len(missing) == 0,
        "checked": len(files),
        "ok_count": ok_count,
        "mismatches": mismatches,
        "missing": missing,
        "backup_dir": str(backup_dir),
        "manifest_path": str(manifest_path),
    }


def restore_backup(
    backup_dir: Path,
    *,
    dest_db: Path | None = None,
    dest_knowledge: Path | None = None,
    dest_summaries: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Restore DB + knowledge + summaries from a backup directory.

    Operator must stop the server first (no lock file enforced here).

    dry_run: verify + report planned targets only.
    live: verify first (fail on hash mismatch/missing unless force); then copy.
    Does not start reindex automatically.
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"backup dir not found: {backup_dir}")

    dest_db = Path(dest_db or settings.db_path)
    dest_knowledge = Path(dest_knowledge or settings.knowledge_storage_dir)
    dest_summaries = Path(dest_summaries or settings.summary_storage_dir)

    src_db = backup_dir / "biri_youyaku.db"
    src_knowledge = backup_dir / "knowledge"
    src_summaries = backup_dir / "summaries"

    verification = verify_backup(backup_dir)
    planned = {
        "dest_db": str(dest_db),
        "dest_knowledge": str(dest_knowledge),
        "dest_summaries": str(dest_summaries),
        "src_db": str(src_db),
        "src_knowledge": str(src_knowledge) if src_knowledge.exists() else None,
        "src_summaries": str(src_summaries) if src_summaries.exists() else None,
    }

    result: dict[str, Any] = {
        "ok": verification.get("ok", False),
        "dry_run": dry_run,
        "force": force,
        "backup_dir": str(backup_dir),
        "verify": verification,
        "planned": planned,
        "restored": False,
    }

    if dry_run:
        # Keep verify outcome in ok so CLI/operators see hash failures.
        result["message"] = (
            "dry_run: no files written; stop the server before a live restore"
        )
        return result

    if not verification.get("ok") and not force:
        result["error"] = "manifest verify failed; pass force=True to restore anyway"
        return result

    if not src_db.is_file():
        result["ok"] = False
        result["error"] = f"backup database missing: {src_db}"
        return result

    dest_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_db, dest_db)

    if src_knowledge.is_dir():
        dest_knowledge.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_knowledge, dest_knowledge, dirs_exist_ok=True)

    if src_summaries.is_dir():
        dest_summaries.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_summaries, dest_summaries, dirs_exist_ok=True)

    result["ok"] = True
    result["restored"] = True
    result["message"] = (
        "restore complete; restart server; run POST /v1/knowledge/reindex if FTS empty"
    )
    logger.info(
        "knowledge restore from %s → db=%s knowledge=%s summaries=%s",
        backup_dir,
        dest_db,
        dest_knowledge,
        dest_summaries,
    )
    return result
