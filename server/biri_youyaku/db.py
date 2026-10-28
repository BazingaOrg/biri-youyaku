import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock
from typing import Iterator

from biri_youyaku.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id              TEXT PRIMARY KEY,
  url             TEXT NOT NULL,
  source_provider TEXT NOT NULL DEFAULT 'bilibili',
  source_id       TEXT,
  source_part     TEXT NOT NULL DEFAULT '',
  input_path      TEXT,
  bvid            TEXT,
  cid             INTEGER,
  mid             INTEGER,
  title           TEXT,
  author          TEXT,
  duration        REAL,
  status          TEXT NOT NULL,
  error_stage     TEXT,
  error_message   TEXT,
  error_code      TEXT,
  audio_path      TEXT,
  subtitle_source TEXT,
  subtitle_language TEXT,
  chapters_json   TEXT,
  transcript_json TEXT,
  summary_path    TEXT,
  options_json    TEXT NOT NULL,
  effective_options_json TEXT,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL,
  completed_at    INTEGER,
  stream_finished_at INTEGER,
  token_usage_json TEXT,
  stage_timings_json TEXT,
  email_error     TEXT,
  tags_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_bvid ON jobs(bvid) WHERE bvid IS NOT NULL;

-- 作者蒸馏语料（distill）跑的独立记录：与 jobs 表数据隔离，一个 run 对应
-- data/distill/<mid>/ 下的一份语料包。task_type="distill" 的 job 仍住在 jobs 表，
-- 只是不进主历史列表（见 jobs/repo.py list_jobs 的 json_extract 过滤）。
CREATE TABLE IF NOT EXISTS distill_runs (
  id                TEXT PRIMARY KEY,
  mid               INTEGER NOT NULL,
  up_name           TEXT,
  status            TEXT NOT NULL,
  video_limit       INTEGER NOT NULL,
  dynamics_status   TEXT,
  counters_json     TEXT,
  error             TEXT,
  dir_path          TEXT NOT NULL,
  created_at        INTEGER NOT NULL,
  updated_at        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_distill_runs_mid ON distill_runs(mid);
CREATE INDEX IF NOT EXISTS idx_distill_runs_status ON distill_runs(status);

-- 每次 LLM 请求的供应商用量。金额只存供应商确认的最小货币单位（micros），
-- 不从 token 数或静态价目表推算。
CREATE TABLE IF NOT EXISTS llm_usage_events (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at           INTEGER NOT NULL,
  job_id                TEXT,
  operation             TEXT NOT NULL,
  provider              TEXT NOT NULL,
  key_fingerprint       TEXT NOT NULL,
  requested_model       TEXT,
  settled_model         TEXT,
  input_tokens          INTEGER NOT NULL DEFAULT 0,
  output_tokens         INTEGER NOT NULL DEFAULT 0,
  total_tokens          INTEGER NOT NULL DEFAULT 0,
  cached_tokens         INTEGER NOT NULL DEFAULT 0,
  request_id            TEXT NOT NULL,
  provider_event_id     TEXT,
  actual_cost_micros    INTEGER,
  currency              TEXT,
  cost_status           TEXT NOT NULL,
  UNIQUE(provider, key_fingerprint, provider_event_id)
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_events_occurred ON llm_usage_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_events_job ON llm_usage_events(job_id);

CREATE TABLE IF NOT EXISTS provider_balance_snapshots (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  observed_at           INTEGER NOT NULL,
  provider              TEXT NOT NULL,
  key_fingerprint       TEXT NOT NULL,
  balance_micros        INTEGER NOT NULL,
  currency              TEXT NOT NULL,
  scope                 TEXT NOT NULL DEFAULT 'account_balance'
);
CREATE INDEX IF NOT EXISTS idx_provider_balance_snapshots_latest
  ON provider_balance_snapshots(provider, key_fingerprint, observed_at DESC);

-- 批量删除先提交数据库、再清理磁盘。失败的文件留在此处供后续维护任务重试，
-- 避免把“数据库已删除”误报为“文件已全部删除”。
CREATE TABLE IF NOT EXISTS pending_file_cleanup (
  path            TEXT PRIMARY KEY,
  job_id          TEXT NOT NULL,
  file_type       TEXT NOT NULL,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL,
  attempts        INTEGER NOT NULL DEFAULT 0,
  last_error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_file_cleanup_updated ON pending_file_cleanup(updated_at);

-- A3 knowledge registry: durable summary/transcript artifacts linked from jobs.
-- History delete unlinks jobs only; knowledge files stay until permanent document delete (D).
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_part TEXT NOT NULL DEFAULT '',
  external_bvid TEXT,
  external_cid INTEGER,
  title TEXT,
  author TEXT,
  mid INTEGER,
  source_url TEXT,
  tags_json TEXT,
  duration REAL,
  tldr TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER,
  delete_reason TEXT,
  UNIQUE(provider, source_id, source_part)
);

CREATE TABLE IF NOT EXISTS knowledge_artifacts (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  kind TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(document_id, kind, content_hash)
);

CREATE TABLE IF NOT EXISTS knowledge_content_revisions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  artifact_id TEXT NOT NULL REFERENCES knowledge_artifacts(id),
  content_hash TEXT NOT NULL,
  subtitle_source TEXT,
  created_at INTEGER NOT NULL,
  UNIQUE(document_id, content_hash)
);

CREATE TABLE IF NOT EXISTS knowledge_summary_revisions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  artifact_id TEXT NOT NULL REFERENCES knowledge_artifacts(id),
  content_hash TEXT NOT NULL,
  source_job_id TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_summary_active
  ON knowledge_summary_revisions(document_id, is_active);

CREATE TABLE IF NOT EXISTS knowledge_job_links (
  job_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  summary_revision_id TEXT,
  content_revision_id TEXT,
  linked_at INTEGER NOT NULL,
  unlinked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_knowledge_job_links_document
  ON knowledge_job_links(document_id);

CREATE TABLE IF NOT EXISTS knowledge_reconcile (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

-- B: FTS-first summary chunks (active summary revisions only; rebuildable).
CREATE TABLE IF NOT EXISTS knowledge_rag_chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  summary_revision_id TEXT NOT NULL,
  source_level TEXT NOT NULL DEFAULT 'summary',
  heading_path TEXT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_ord INTEGER NOT NULL,
  start_sec REAL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_rag_chunks_doc ON knowledge_rag_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_rag_chunks_rev ON knowledge_rag_chunks(summary_revision_id);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_rag_chunks_fts USING fts5(
  chunk_id UNINDEXED,
  document_id UNINDEXED,
  summary_revision_id UNINDEXED,
  heading_path,
  body,
  tokenize = 'unicode61'
);

-- C: FTS transcript evidence chunks (raw windows; rebuildable from artifacts).
CREATE TABLE IF NOT EXISTS knowledge_transcript_chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  content_revision_id TEXT NOT NULL,
  source_level TEXT NOT NULL DEFAULT 'transcript',
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  subtitle_source TEXT,
  chunk_text TEXT NOT NULL,
  chunk_ord INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_transcript_chunks_doc
  ON knowledge_transcript_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_transcript_chunks_rev
  ON knowledge_transcript_chunks(content_revision_id);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_transcript_chunks_fts USING fts5(
  chunk_id UNINDEXED,
  document_id UNINDEXED,
  content_revision_id UNINDEXED,
  body,
  tokenize = 'unicode61'
);

-- D: document lifecycle audit (soft_delete | restore | purge | backup).
CREATE TABLE IF NOT EXISTS knowledge_audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at INTEGER NOT NULL,
  action TEXT NOT NULL,
  document_id TEXT,
  detail_json TEXT,
  actor TEXT
);
CREATE INDEX IF NOT EXISTS idx_knowledge_audit_occurred
  ON knowledge_audit_events(occurred_at DESC);
"""

# 已废弃的旧列：去重改走 bvid 查询（不再用 content_hash），旧 SELECT * 兼容列也不再需要。
# 启动时尽力 DROP 掉；老版本 sqlite（<3.35）不支持 DROP COLUMN 就留着，反正没代码读它。
_LEGACY_COLUMNS = ("content_hash", "segments_json")
_LEGACY_INDEXES = ("idx_jobs_content_hash", "idx_jobs_bvid_cid")

_connection: sqlite3.Connection | None = None
_connection_path: Path | None = None
_connection_lock = Lock()
_write_lock = RLock()


@contextmanager
def exclusive_write() -> Iterator[None]:
    """Serialize register and purge. They share one SQLite connection."""
    with _write_lock:
        yield


def connect() -> sqlite3.Connection:
    global _connection, _connection_path
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connection_lock:
        if _connection is not None and _connection_path != db_path:
            _connection.close()
            _connection = None
        if _connection is None:
            _connection = sqlite3.connect(db_path, check_same_thread=False)
            _connection_path = db_path
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode=WAL")
            _connection.execute("PRAGMA synchronous=NORMAL")
            _connection.execute("PRAGMA busy_timeout=5000")
        return _connection


def _backfill_knowledge_document_meta(
    connection: sqlite3.Connection, *, tldr_limit: int = 200
) -> None:
    """Copy tags/duration from latest completed jobs; parse tldr from summary files.

    Only fills empty document columns. Safe to re-run. tldr file reads are capped.
    """
    knowledge_doc_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(knowledge_documents)").fetchall()
    }
    if not knowledge_doc_columns:
        return
    jobs_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
    if "bvid" not in jobs_columns:
        return
    if "tags_json" in knowledge_doc_columns and "tags_json" in jobs_columns:
        connection.execute(
            """
            UPDATE knowledge_documents
            SET tags_json = (
              SELECT j.tags_json FROM jobs j
              WHERE j.bvid = knowledge_documents.external_bvid
                AND j.cid = knowledge_documents.external_cid
                AND j.status = 'COMPLETED'
                AND IFNULL(j.summary_path, '') != ''
                AND IFNULL(j.tags_json, '') != ''
              ORDER BY j.completed_at DESC, j.created_at DESC
              LIMIT 1
            )
            WHERE provider = 'bilibili'
              AND (tags_json IS NULL OR tags_json = '')
              AND EXISTS (
                SELECT 1 FROM jobs j
                WHERE j.bvid = knowledge_documents.external_bvid
                  AND j.cid = knowledge_documents.external_cid
                  AND j.status = 'COMPLETED'
                  AND IFNULL(j.summary_path, '') != ''
                  AND IFNULL(j.tags_json, '') != ''
              )
            """
        )
    if "duration" in knowledge_doc_columns and "duration" in jobs_columns:
        connection.execute(
            """
            UPDATE knowledge_documents
            SET duration = (
              SELECT j.duration FROM jobs j
              WHERE j.bvid = knowledge_documents.external_bvid
                AND j.cid = knowledge_documents.external_cid
                AND j.status = 'COMPLETED'
                AND IFNULL(j.summary_path, '') != ''
                AND j.duration IS NOT NULL
              ORDER BY j.completed_at DESC, j.created_at DESC
              LIMIT 1
            )
            WHERE provider = 'bilibili'
              AND duration IS NULL
              AND EXISTS (
                SELECT 1 FROM jobs j
                WHERE j.bvid = knowledge_documents.external_bvid
                  AND j.cid = knowledge_documents.external_cid
                  AND j.status = 'COMPLETED'
                  AND IFNULL(j.summary_path, '') != ''
                  AND j.duration IS NOT NULL
              )
            """
        )
    if "tldr" not in knowledge_doc_columns:
        return
    from biri_youyaku.knowledge.summary_meta import extract_tldr
    from biri_youyaku.modules.storage import summary as summary_storage

    connection.commit()
    rows = connection.execute(
        """
        SELECT id, external_bvid, external_cid
        FROM knowledge_documents
        WHERE provider = 'bilibili'
          AND tldr IS NULL
        LIMIT ?
        """,
        (int(tldr_limit),),
    ).fetchall()
    for row in rows:
        job = connection.execute(
            """
            SELECT summary_path FROM jobs
            WHERE bvid = ? AND cid = ?
              AND status = 'COMPLETED'
              AND IFNULL(summary_path, '') != ''
            ORDER BY completed_at DESC, created_at DESC
            LIMIT 1
            """,
            (row["external_bvid"], row["external_cid"]),
        ).fetchone()
        tldr = ""
        if job is not None:
            path = summary_storage.resolve_stored_path(job["summary_path"])
            try:
                if path.is_file():
                    tldr = extract_tldr(path.read_text(encoding="utf-8")) or ""
            except OSError:
                tldr = ""
        connection.execute(
            """
            UPDATE knowledge_documents
            SET tldr = ?
            WHERE id = ? AND tldr IS NULL
            """,
            (tldr, row["id"]),
        )
        connection.commit()


def _backfill_rag_chunk_start_sec(connection: sqlite3.Connection, *, limit: int = 100) -> None:
    rag_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(knowledge_rag_chunks)").fetchall()
    }
    if "start_sec" not in rag_columns:
        return
    from biri_youyaku.knowledge.chunker import parse_chunk_start_sec

    rows = connection.execute(
        """
        SELECT c.id AS id, c.heading_path AS heading_path, c.chunk_text AS chunk_text
        FROM knowledge_rag_chunks c
        JOIN knowledge_summary_revisions sr
          ON sr.id = c.summary_revision_id AND sr.is_active = 1
        WHERE c.start_sec IS NULL
          AND (
            c.heading_path GLOB '[0-9]*:[0-9][0-9]*'
            OR c.chunk_text GLOB '*## [0-9]*:[0-9][0-9]*'
            OR c.chunk_text GLOB '*### [0-9]*:[0-9][0-9]*'
          )
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    for row in rows:
        start_sec = parse_chunk_start_sec(row["heading_path"], row["chunk_text"])
        if start_sec is None:
            continue
        connection.execute(
            "UPDATE knowledge_rag_chunks SET start_sec = ? WHERE id = ? AND start_sec IS NULL",
            (float(start_sec), row["id"]),
        )


@contextmanager
def maintenance_connection() -> Iterator[sqlite3.Connection]:
    """为可能在线程中运行的维护操作创建并关闭独立连接。"""
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        yield connection
        connection.commit()
    finally:
        connection.close()


def _migrate_knowledge_document_identity(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(knowledge_documents)")
    }
    if not columns or {"source_id", "source_part"}.issubset(columns):
        return
    connection.execute("SAVEPOINT source_identity_migration")
    try:
        before = connection.execute("SELECT COUNT(*) AS n FROM knowledge_documents").fetchone()["n"]
        connection.execute("DROP TABLE IF EXISTS knowledge_documents_v2")
        connection.execute(
            """
            CREATE TABLE knowledge_documents_v2 (
              id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              source_id TEXT NOT NULL,
              source_part TEXT NOT NULL DEFAULT '',
              external_bvid TEXT,
              external_cid INTEGER,
              title TEXT,
              author TEXT,
              mid INTEGER,
              source_url TEXT,
              tags_json TEXT,
              duration REAL,
              tldr TEXT,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              deleted_at INTEGER,
              delete_reason TEXT,
              UNIQUE(provider, source_id, source_part)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO knowledge_documents_v2 (
              id, provider, source_id, source_part, external_bvid, external_cid,
              title, author, mid, source_url, tags_json, duration, tldr,
              created_at, updated_at, deleted_at, delete_reason
            )
            SELECT
              id, provider, external_bvid, CAST(external_cid AS TEXT), external_bvid, external_cid,
              title, author, mid, source_url, tags_json, duration, tldr,
              created_at, updated_at, deleted_at, delete_reason
            FROM knowledge_documents
            """
        )
        after = connection.execute("SELECT COUNT(*) AS n FROM knowledge_documents_v2").fetchone()["n"]
        if before != after:
            raise RuntimeError("knowledge document identity migration lost rows")
        common_columns = ", ".join(sorted(columns))
        mismatch = connection.execute(
            f"SELECT {common_columns} FROM knowledge_documents EXCEPT SELECT {common_columns} FROM knowledge_documents_v2 LIMIT 1"
        ).fetchone()
        if mismatch is not None:
            raise RuntimeError("knowledge document identity migration changed existing metadata")
        connection.execute("DROP TABLE knowledge_documents")
        connection.execute("ALTER TABLE knowledge_documents_v2 RENAME TO knowledge_documents")
        connection.execute("RELEASE SAVEPOINT source_identity_migration")
    except BaseException:
        connection.execute("ROLLBACK TO SAVEPOINT source_identity_migration")
        connection.execute("RELEASE SAVEPOINT source_identity_migration")
        raise


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        # 2026-08 减法：周总结功能已删除，老库清理孤儿表（代码不再读写）。
        connection.execute("DROP TABLE IF EXISTS weekly_summary_sources")
        connection.execute("DROP TABLE IF EXISTS weekly_summaries")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = {
            "subtitle_language": "ALTER TABLE jobs ADD COLUMN subtitle_language TEXT",
            "source_provider": (
                "ALTER TABLE jobs ADD COLUMN source_provider TEXT NOT NULL DEFAULT 'bilibili'"
            ),
            "source_id": "ALTER TABLE jobs ADD COLUMN source_id TEXT",
            "source_part": "ALTER TABLE jobs ADD COLUMN source_part TEXT NOT NULL DEFAULT ''",
            "input_path": "ALTER TABLE jobs ADD COLUMN input_path TEXT",
            "mid": "ALTER TABLE jobs ADD COLUMN mid INTEGER",
            "chapters_json": "ALTER TABLE jobs ADD COLUMN chapters_json TEXT",
            "transcript_json": "ALTER TABLE jobs ADD COLUMN transcript_json TEXT",
            "effective_options_json": "ALTER TABLE jobs ADD COLUMN effective_options_json TEXT",
            "error_code": "ALTER TABLE jobs ADD COLUMN error_code TEXT",
            "stream_finished_at": "ALTER TABLE jobs ADD COLUMN stream_finished_at INTEGER",
            "token_usage_json": "ALTER TABLE jobs ADD COLUMN token_usage_json TEXT",
            "stage_timings_json": "ALTER TABLE jobs ADD COLUMN stage_timings_json TEXT",
            "email_error": "ALTER TABLE jobs ADD COLUMN email_error TEXT",
            "tags_json": "ALTER TABLE jobs ADD COLUMN tags_json TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)
        connection.execute(
            """
            UPDATE jobs
            SET source_provider = 'bilibili'
            WHERE source_provider IS NULL OR source_provider = ''
            """
        )
        connection.execute(
            """
            UPDATE jobs
            SET source_id = bvid
            WHERE source_id IS NULL AND bvid IS NOT NULL AND bvid != ''
            """
        )
        connection.execute(
            """
            UPDATE jobs
            SET source_part = CAST(cid AS TEXT)
            WHERE (source_part IS NULL OR source_part = '') AND cid IS NOT NULL
            """
        )
        usage_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(llm_usage_events)").fetchall()
        }
        if "request_id" not in usage_columns:
            connection.execute("ALTER TABLE llm_usage_events ADD COLUMN request_id TEXT")
            connection.execute(
                "UPDATE llm_usage_events SET request_id = 'legacy-' || id WHERE request_id IS NULL"
            )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_usage_events_request_id ON llm_usage_events(request_id)"
        )
        balance_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(provider_balance_snapshots)"
            ).fetchall()
        }
        if "scope" not in balance_columns:
            connection.execute(
                "ALTER TABLE provider_balance_snapshots ADD COLUMN scope TEXT NOT NULL DEFAULT 'account_balance'"
            )
        knowledge_doc_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(knowledge_documents)").fetchall()
        }
        if knowledge_doc_columns:
            if "deleted_at" not in knowledge_doc_columns:
                connection.execute("ALTER TABLE knowledge_documents ADD COLUMN deleted_at INTEGER")
            if "delete_reason" not in knowledge_doc_columns:
                connection.execute("ALTER TABLE knowledge_documents ADD COLUMN delete_reason TEXT")
            if "tags_json" not in knowledge_doc_columns:
                connection.execute("ALTER TABLE knowledge_documents ADD COLUMN tags_json TEXT")
            if "duration" not in knowledge_doc_columns:
                connection.execute("ALTER TABLE knowledge_documents ADD COLUMN duration REAL")
            if "tldr" not in knowledge_doc_columns:
                connection.execute("ALTER TABLE knowledge_documents ADD COLUMN tldr TEXT")
        _migrate_knowledge_document_identity(connection)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_job_links_document
              ON knowledge_job_links(document_id)
            """
        )
        rag_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(knowledge_rag_chunks)").fetchall()
        }
        if rag_columns and "start_sec" not in rag_columns:
            connection.execute("ALTER TABLE knowledge_rag_chunks ADD COLUMN start_sec REAL")
        _backfill_knowledge_document_meta(connection)
        _backfill_rag_chunk_start_sec(connection, limit=100)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_audit_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occurred_at INTEGER NOT NULL,
              action TEXT NOT NULL,
              document_id TEXT,
              detail_json TEXT,
              actor TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_audit_occurred
              ON knowledge_audit_events(occurred_at DESC)
            """
        )
        connection.execute(
            """
            UPDATE jobs
            SET effective_options_json = options_json
            WHERE effective_options_json IS NULL
            """
        )
        # 清掉废弃索引 + 列（尽力，DROP COLUMN 需 sqlite ≥3.35）。
        for index in _LEGACY_INDEXES:
            connection.execute(f"DROP INDEX IF EXISTS {index}")
        for column in _LEGACY_COLUMNS:
            if column in columns:
                try:
                    connection.execute(f"ALTER TABLE jobs DROP COLUMN {column}")
                except sqlite3.OperationalError:
                    pass  # 老 sqlite 不支持 DROP COLUMN，留着无害（没代码读它）
