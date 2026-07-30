"""Path helpers + atomic byte write + sha256 for knowledge artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from biri_youyaku.config import settings
from biri_youyaku.knowledge.model import ARTIFACT_KIND_SUMMARY, ARTIFACT_KIND_TRANSCRIPT_RAW


def knowledge_root() -> Path:
    return Path(settings.knowledge_storage_dir)


def to_stored_path(path: Path, *, root: Path | None = None) -> str:
    """Return POSIX path relative to knowledge root when path is under root; else absolute POSIX."""
    base = (root or knowledge_root()).resolve()
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_stored_path(stored: str | Path, *, root: Path | None = None) -> Path:
    """If stored is absolute → use as-is (legacy). If relative → knowledge_root() / stored."""
    path = Path(stored)
    if path.is_absolute():
        return path
    base = root if root is not None else knowledge_root()
    return Path(base) / path


def rewrite_artifact_paths_in_db() -> dict[str, int]:
    """Rewrite absolute knowledge_artifacts.storage_path under root to relative.

    Returns counts: total, rewritten, already_relative, outside_root.
    """
    from biri_youyaku.db import connect

    root = knowledge_root().resolve()
    total = 0
    rewritten = 0
    already_relative = 0
    outside_root = 0
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, storage_path FROM knowledge_artifacts"
        ).fetchall()
        for row in rows:
            total += 1
            stored = row["storage_path"]
            if not stored:
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
                "UPDATE knowledge_artifacts SET storage_path = ? WHERE id = ?",
                (rel, row["id"]),
            )
            rewritten += 1
    return {
        "total": total,
        "rewritten": rewritten,
        "already_relative": already_relative,
        "outside_root": outside_root,
    }


def artifacts_root() -> Path:
    return knowledge_root() / "artifacts"


def document_dir(document_id: str) -> Path:
    return artifacts_root() / document_id


def summary_artifact_path(document_id: str, content_hash: str) -> Path:
    return document_dir(document_id) / "summary" / f"{content_hash}.md"


def transcript_artifact_path(document_id: str, content_hash: str) -> Path:
    return document_dir(document_id) / "transcript" / f"{content_hash}.json"


def path_for_kind(document_id: str, kind: str, content_hash: str) -> Path:
    if kind == ARTIFACT_KIND_SUMMARY:
        return summary_artifact_path(document_id, content_hash)
    if kind == ARTIFACT_KIND_TRANSCRIPT_RAW:
        return transcript_artifact_path(document_id, content_hash)
    raise ValueError(f"unknown artifact kind: {kind}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via same-dir temp file + os.replace (mirrors distill storage)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as file:
            temp_path = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def ensure_bytes_on_disk(path: Path, data: bytes) -> None:
    """Write data if path missing; if present, leave as-is (hash is in filename)."""
    if path.is_file():
        return
    atomic_write_bytes(path, data)


def build_transcript_payload(
    segments: list[dict[str, Any]] | None,
    *,
    subtitle_source: str | None,
) -> dict[str, Any]:
    """Build the durable transcript_raw JSON object (before canonical encode)."""
    source = subtitle_source
    items: list[dict[str, Any]] = []
    for item in segments or []:
        items.append(
            {
                "end": float(item.get("end") or 0.0),
                "raw_text": str(item.get("text") or item.get("raw_text") or ""),
                "source": source,
                "start": float(item.get("start") or 0.0),
            }
        )
    return {
        "segments": items,
        "subtitle_source": source,
    }


def encode_transcript_bytes(payload: dict[str, Any]) -> bytes:
    """Canonical UTF-8 JSON bytes for hashing and storage.

    Outer object keys sorted; segment list order preserved; compact separators;
    ensure_ascii=False so CJK stays multi-byte UTF-8.
    """
    text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")
