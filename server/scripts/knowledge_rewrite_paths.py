#!/usr/bin/env python3
"""CLI: rewrite absolute knowledge/summary storage paths in DB to relative form.

Usage (from server/):
  uv run python scripts/knowledge_rewrite_paths.py
  uv run python scripts/knowledge_rewrite_paths.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from biri_youyaku import db  # noqa: E402
from biri_youyaku.knowledge.artifacts import rewrite_artifact_paths_in_db  # noqa: E402
from biri_youyaku.modules.storage.summary import rewrite_summary_paths_in_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite absolute artifact/summary paths under storage roots to relative"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing (counts via temp inspection)",
    )
    args = parser.parse_args()
    db.init_db()

    if args.dry_run:
        # Dry-run: count candidates without UPDATE by reusing rewrite logic on a
        # transaction that is rolled back is awkward; re-implement count-only.
        from pathlib import Path as P

        from biri_youyaku.config import settings
        from biri_youyaku.db import connect
        from biri_youyaku.knowledge.artifacts import knowledge_root
        from biri_youyaku.modules.storage.summary import summary_root

        def _count(table: str, col: str, root: P) -> dict[str, int]:
            base = root.resolve()
            total = rewritten = already_relative = outside_root = 0
            with connect() as connection:
                rows = connection.execute(
                    f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
                ).fetchall()
            for row in rows:
                total += 1
                stored = row[col]
                path = P(stored)
                if not path.is_absolute():
                    already_relative += 1
                    continue
                try:
                    path.expanduser().resolve().relative_to(base)
                except ValueError:
                    outside_root += 1
                    continue
                rewritten += 1
            return {
                "total": total,
                "rewritten": rewritten,
                "already_relative": already_relative,
                "outside_root": outside_root,
            }

        result = {
            "dry_run": True,
            "artifacts": _count(
                "knowledge_artifacts", "storage_path", knowledge_root()
            ),
            "summaries": _count("jobs", "summary_path", summary_root()),
            "knowledge_root": str(settings.knowledge_storage_dir),
            "summary_root": str(settings.summary_storage_dir),
        }
    else:
        result = {
            "dry_run": False,
            "artifacts": rewrite_artifact_paths_in_db(),
            "summaries": rewrite_summary_paths_in_db(),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
