import sqlite3

from biri_youyaku import db


def test_knowledge_identity_migration_preserves_graph_and_lifecycle(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(db.settings, "db_path", db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE knowledge_documents (
              id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              external_bvid TEXT NOT NULL,
              external_cid INTEGER NOT NULL,
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
              UNIQUE(provider, external_bvid, external_cid)
            );
            CREATE TABLE knowledge_artifacts (
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
              kind TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              storage_path TEXT NOT NULL,
              byte_size INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              UNIQUE(document_id, kind, content_hash)
            );
            CREATE TABLE knowledge_summary_revisions (
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
              artifact_id TEXT NOT NULL REFERENCES knowledge_artifacts(id),
              content_hash TEXT NOT NULL,
              source_job_id TEXT,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE knowledge_job_links (
              job_id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
              summary_revision_id TEXT,
              content_revision_id TEXT,
              linked_at INTEGER NOT NULL,
              unlinked_at INTEGER
            );
            INSERT INTO knowledge_documents VALUES (
              'doc-1', 'bilibili', 'BVlegacy', 2468, 'title', 'author', 42,
              'https://www.bilibili.com/video/BVlegacy', '["tag"]', 12.0, 'tldr',
              100, 200, 300, 'user'
            );
            INSERT INTO knowledge_artifacts VALUES (
              'artifact-1', 'doc-1', 'summary', 'hash', 'summary.md', 7, 100
            );
            INSERT INTO knowledge_summary_revisions VALUES (
              'revision-1', 'doc-1', 'artifact-1', 'hash', 'job-1', 1, 100
            );
            INSERT INTO knowledge_job_links VALUES (
              'job-1', 'doc-1', 'revision-1', NULL, 100, 250
            );
            """
        )

    db.init_db()

    with db.connect() as connection:
        document = connection.execute(
            "SELECT * FROM knowledge_documents WHERE id = 'doc-1'"
        ).fetchone()
        artifact = connection.execute(
            "SELECT * FROM knowledge_artifacts WHERE id = 'artifact-1'"
        ).fetchone()
        revision = connection.execute(
            "SELECT * FROM knowledge_summary_revisions WHERE id = 'revision-1'"
        ).fetchone()
        link = connection.execute(
            "SELECT * FROM knowledge_job_links WHERE job_id = 'job-1'"
        ).fetchone()

    assert document["provider"] == "bilibili"
    assert document["source_id"] == "BVlegacy"
    assert document["source_part"] == "2468"
    assert document["external_bvid"] == "BVlegacy"
    assert document["external_cid"] == 2468
    assert document["deleted_at"] == 300
    assert document["delete_reason"] == "user"
    assert artifact["document_id"] == "doc-1"
    assert revision["document_id"] == "doc-1"
    assert revision["artifact_id"] == "artifact-1"
    assert link["document_id"] == "doc-1"
    assert link["summary_revision_id"] == "revision-1"
    assert link["unlinked_at"] == 250
    db.init_db()
    assert db.connect().execute("PRAGMA foreign_key_check").fetchall() == []


def test_identity_migration_rolls_back_if_table_swap_fails():
    import pytest

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE knowledge_documents (
        id TEXT PRIMARY KEY, provider TEXT NOT NULL, external_bvid TEXT NOT NULL,
        external_cid INTEGER NOT NULL, title TEXT, author TEXT, mid INTEGER,
        source_url TEXT, tags_json TEXT, duration REAL, tldr TEXT,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
        deleted_at INTEGER, delete_reason TEXT)"""
    )
    connection.execute(
        "INSERT INTO knowledge_documents(id,provider,external_bvid,external_cid,title,created_at,updated_at) VALUES ('stable-id','bilibili','BV1',1,'Preserved',1,1)"
    )
    connection.commit()
    connection.set_authorizer(
        lambda action, *args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK
    )
    with pytest.raises(sqlite3.DatabaseError):
        db._migrate_knowledge_document_identity(connection)
    connection.set_authorizer(None)
    row = connection.execute("SELECT id,title FROM knowledge_documents").fetchone()
    assert tuple(row) == ("stable-id", "Preserved")
    assert connection.execute("SELECT name FROM sqlite_master WHERE name='knowledge_documents_v2'").fetchone() is None
    connection.close()
