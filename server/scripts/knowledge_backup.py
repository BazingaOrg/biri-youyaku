#!/usr/bin/env python3
"""CLI: consistent local knowledge backup (sqlite backup + artifacts + manifest).

Usage (from server/):
  uv run python scripts/knowledge_backup.py
  uv run python scripts/knowledge_backup.py --dry-run
  uv run python scripts/knowledge_backup.py --out /path/to/backups

Restore (not automated):
  1. Stop the server.
  2. Replace data/biri_youyaku.db with backup/biri_youyaku.db
     (or use sqlite3: sqlite3 data/biri_youyaku.db ".restore 'backup/biri_youyaku.db'").
  3. Restore knowledge/ → KNOWLEDGE_STORAGE_DIR and summaries/ → SUMMARY_STORAGE_DIR.
  4. Restart; if FTS empty run POST /v1/knowledge/reindex.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as script without installing package path quirks.
_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from biri_youyaku import db  # noqa: E402
from biri_youyaku.knowledge.backup import create_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup knowledge DB + artifacts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hash live sources and print manifest without writing a backup tree",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Backup root directory (default: settings.knowledge_backup_dir)",
    )
    args = parser.parse_args()
    db.init_db()
    result = create_backup(dry_run=args.dry_run, backup_dir=args.out, actor="cli")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
