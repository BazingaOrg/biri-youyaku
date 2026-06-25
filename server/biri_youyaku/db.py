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
  -- segments_json: 历史遗留列，代码从不写入。新库不再创建；旧库通过 init_db 探测保留以不破坏 SELECT * 兼容。
  summary_path    TEXT,
  options_json    TEXT NOT NULL,
  effective_options_json TEXT,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL,
  completed_at    INTEGER,
  stream_finished_at INTEGER,
  token_usage_json TEXT,
  content_hash    TEXT,
  stage_timings_json TEXT,
  email_error     TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
DROP INDEX IF EXISTS idx_jobs_bvid_cid;
CREATE INDEX IF NOT EXISTS idx_jobs_bvid_cid ON jobs(bvid, cid) WHERE bvid IS NOT NULL;
"""

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
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        migrations = {
            "mid": "ALTER TABLE jobs ADD COLUMN mid INTEGER",
            "chapters_json": "ALTER TABLE jobs ADD COLUMN chapters_json TEXT",
            "transcript_json": "ALTER TABLE jobs ADD COLUMN transcript_json TEXT",
            "effective_options_json": "ALTER TABLE jobs ADD COLUMN effective_options_json TEXT",
            "error_code": "ALTER TABLE jobs ADD COLUMN error_code TEXT",
            "stream_finished_at": "ALTER TABLE jobs ADD COLUMN stream_finished_at INTEGER",
            "token_usage_json": "ALTER TABLE jobs ADD COLUMN token_usage_json TEXT",
            "content_hash": "ALTER TABLE jobs ADD COLUMN content_hash TEXT",
            "stage_timings_json": "ALTER TABLE jobs ADD COLUMN stage_timings_json TEXT",
            "email_error": "ALTER TABLE jobs ADD COLUMN email_error TEXT",
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs(content_hash) WHERE content_hash IS NOT NULL"
        )
