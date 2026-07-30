# Knowledge eval fixtures (Phase F)

Synthetic corpus used by CI and `scripts/knowledge_eval.py` to measure FTS
summary / transcript retrieval (Recall@5, MRR@10, no-answer empty rate).

## Layout

```
knowledge_eval/
  manifest.json      # version + CI thresholds (synthetic; not production gates)
  corpus/docs.json   # synthetic documents
  queries.json       # labeled queries (train / holdout)
```

## Run

From `server/`:

```bash
uv run python scripts/knowledge_eval.py
uv run python scripts/knowledge_eval.py --split holdout
uv run pytest tests/test_knowledge_eval.py -q
```

## Private / real corpus (later)

Point the CLI at a **local** directory with the same layout:

```bash
uv run python scripts/knowledge_eval.py --fixtures /path/to/private_knowledge_eval
```

Suggested local path (gitignored; do not commit real user content):

- `server/tests/fixtures/knowledge_eval_private/` (optional; create yourself)

Private fixtures must provide:

| File | Required fields |
| --- | --- |
| `manifest.json` | `ci_thresholds` (same keys as synthetic) |
| `corpus/docs.json` | list of docs with `doc_key`, `bvid`, `cid`, `title`, `summary_md`, `transcript` |
| `queries.json` | `{ "version", "queries": [ { id, query, split, kind, layer, gold_doc_keys, category } ] }` |

Production numeric gates (full corpus) remain documented in
`docs/plans/2026-07-29-personal-knowledge-base-rag.md` and are **not** claimed
by the synthetic CI thresholds in `manifest.json`.

## Notes

- Chat stays default-off (`KNOWLEDGE_CHAT_ENABLED=false`); this harness only
  exercises register + FTS retrieve.
- Synthetic thresholds are lower / separate from production holdout gates.
