import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator

from biri_youyaku.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id              TEXT PRIMARY KEY,
  url             TEXT NOT NULL,
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

-- 周总结是派生缓存，和单条总结文件分开保存；来源快照用于检测新来源和删除失效。
CREATE TABLE IF NOT EXISTS weekly_summaries (
  week_start       TEXT PRIMARY KEY,
  week_end         TEXT NOT NULL,
  timezone         TEXT NOT NULL,
  status           TEXT NOT NULL,
  content          TEXT,
  references_json  TEXT,
  sources_fingerprint TEXT,
  generation_token  TEXT,
  generation_expires_at INTEGER,
  error            TEXT,
  generated_at     INTEGER,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weekly_summaries_status ON weekly_summaries(status);

CREATE TABLE IF NOT EXISTS weekly_summary_sources (
  week_start       TEXT NOT NULL REFERENCES weekly_summaries(week_start) ON DELETE CASCADE,
  job_id           TEXT NOT NULL,
  PRIMARY KEY (week_start, job_id)
);
CREATE INDEX IF NOT EXISTS idx_weekly_summary_sources_job ON weekly_summary_sources(job_id);

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
  external_bvid TEXT NOT NULL,
  external_cid INTEGER NOT NULL,
  title TEXT,
  author TEXT,
  mid INTEGER,
  source_url TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(provider, external_bvid, external_cid)
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
"""

# 已废弃的旧列：去重改走 bvid 查询（不再用 content_hash），旧 SELECT * 兼容列也不再需要。
# 启动时尽力 DROP 掉；老版本 sqlite（<3.35）不支持 DROP COLUMN 就留着，反正没代码读它。
_LEGACY_COLUMNS = ("content_hash", "segments_json")
_LEGACY_INDEXES = ("idx_jobs_content_hash", "idx_jobs_bvid_cid")

_connection: sqlite3.Connection | None = None
_connection_path: Path | None = None
_connection_lock = Lock()


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


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = {
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
        weekly_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(weekly_summaries)").fetchall()
        }
        if "generation_token" not in weekly_columns:
            connection.execute("ALTER TABLE weekly_summaries ADD COLUMN generation_token TEXT")
        if "generation_expires_at" not in weekly_columns:
            connection.execute(
                "ALTER TABLE weekly_summaries ADD COLUMN generation_expires_at INTEGER"
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
