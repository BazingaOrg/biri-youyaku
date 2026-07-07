import sqlite3
from pathlib import Path
from threading import Lock

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
