#!/usr/bin/env python3
"""CLI: restore knowledge backup (manifest verify + copy DB/knowledge/summaries).

Stop the server before a live restore. Does not reindex FTS automatically.

Usage (from server/):
  uv run python scripts/knowledge_restore.py --from data/backups/<ts>
  uv run python scripts/knowledge_restore.py --from data/backups/<ts> --dry-run
  uv run python scripts/knowledge_restore.py --from data/backups/<ts> --force
  uv run python scripts/knowledge_restore.py --from data/backups/<ts> --replace-trees
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from biri_youyaku.knowledge.backup import restore_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore knowledge backup (verify manifest, copy db/knowledge/summaries)"
    )
    parser.add_argument(
        "--from",
        dest="backup_from",
        type=Path,
        required=True,
        help="Backup directory (contains biri_youyaku.db + manifest.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify + print planned destinations without writing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Restore even if manifest hash verify fails",
    )
    parser.add_argument(
        "--replace-trees",
        action="store_true",
        help="Replace knowledge/ and summaries/ dirs entirely (rmtree then copy); default merges",
    )
    parser.add_argument(
        "--dest-db",
        type=Path,
        default=None,
        help="Override destination DB path (default: settings.db_path)",
    )
    parser.add_argument(
        "--dest-knowledge",
        type=Path,
        default=None,
        help="Override KNOWLEDGE_STORAGE_DIR",
    )
    parser.add_argument(
        "--dest-summaries",
        type=Path,
        default=None,
        help="Override SUMMARY_STORAGE_DIR",
    )
    args = parser.parse_args()
    try:
        result = restore_backup(
            args.backup_from,
            dest_db=args.dest_db,
            dest_knowledge=args.dest_knowledge,
            dest_summaries=args.dest_summaries,
            dry_run=args.dry_run,
            force=args.force,
            replace_trees=args.replace_trees,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 1
    if not args.dry_run and not result.get("restored"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
