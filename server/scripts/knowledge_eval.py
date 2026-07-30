#!/usr/bin/env python3
"""CLI: knowledge retrieval eval on synthetic (or private) fixtures.

Uses an isolated temp DB by default so production data/ is never touched.

Usage (from server/):
  uv run python scripts/knowledge_eval.py
  uv run python scripts/knowledge_eval.py --fixtures path
  uv run python scripts/knowledge_eval.py --split holdout
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from biri_youyaku.knowledge.eval import (  # noqa: E402
    default_fixtures_dir,
    run_synthetic_eval,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run knowledge FTS eval (isolated temp DB by default)"
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="Fixtures directory (default: tests/fixtures/knowledge_eval)",
    )
    parser.add_argument(
        "--split",
        action="append",
        dest="splits",
        default=None,
        help="Limit to split (repeatable: train, holdout). Default: all",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Work dir for DB/knowledge/summaries (default: temp dir, deleted after)",
    )
    parser.add_argument(
        "--keep-root",
        action="store_true",
        help="Do not delete temp root after run (only applies when --root omitted)",
    )
    args = parser.parse_args()

    fixtures = args.fixtures or default_fixtures_dir()
    if not fixtures.is_dir():
        print(json.dumps({"error": f"fixtures not found: {fixtures}"}, ensure_ascii=False))
        return 1

    cleanup_root: Path | None = None
    root = args.root
    if root is None:
        root = Path(tempfile.mkdtemp(prefix="knowledge_eval_"))
        if not args.keep_root:
            cleanup_root = root
    else:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)

    try:
        result = run_synthetic_eval(
            fixtures_dir=fixtures,
            root=root,
            splits=args.splits,
            init_db=True,
            configure_settings=True,
        )
        # Compact CLI output: drop full per_query unless useful for debugging.
        out = {
            "corpus": result.get("corpus"),
            "fixtures_dir": result.get("fixtures_dir"),
            "seed": {
                "registered_count": result.get("seed", {}).get("registered_count"),
                "failure_count": result.get("seed", {}).get("failure_count"),
            },
            "metrics": result.get("metrics"),
            "split_metrics": result.get("split_metrics"),
            "gates_met": result.get("gates_met"),
            "gates": result.get("gates"),
            "thresholds": result.get("thresholds"),
            "splits": result.get("splits"),
            "note": result.get("note"),
            "production_gates_ref": result.get("production_gates_ref"),
            "work_root": str(root),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if result.get("gates_met") else 1
    finally:
        if cleanup_root is not None:
            shutil.rmtree(cleanup_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
