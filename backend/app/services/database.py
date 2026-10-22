"""The backend's SQLite database: connections and schema migrations.

The API runs as a single process, so one SQLite file (in WAL mode) is enough.
"""

import sqlite3
from pathlib import Path

# Each step moves the schema up one version (PRAGMA user_version). Append new
# steps; never edit one that has shipped.
MIGRATIONS: tuple[str, ...] = (
    # 1: documents and their chunks, as first shipped.
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY, title TEXT NOT NULL,
        filename TEXT NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
        chunks INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
        source TEXT NOT NULL, url TEXT, progress INTEGER,
        error TEXT, uploaded_at TEXT NOT NULL, file_bytes BLOB
    );
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
        page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
        section TEXT, text TEXT NOT NULL, content_hash TEXT NOT NULL
    );
    """,
    # 2: Firebase users own documents and jobs (NULL owner = the account-free
    # demo); jobs and their step events are stored; chunks go with their document.
    """
    CREATE TABLE users (
        uid TEXT PRIMARY KEY, email TEXT, name TEXT NOT NULL,
        picture TEXT, provider TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );

    ALTER TABLE documents
        ADD COLUMN owner_uid TEXT REFERENCES users(uid) ON DELETE CASCADE;
    CREATE INDEX documents_by_owner ON documents(owner_uid, uploaded_at);

    CREATE TABLE chunks_v2 (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL
            REFERENCES documents(document_id) ON DELETE CASCADE,
        page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
        section TEXT, text TEXT NOT NULL, content_hash TEXT NOT NULL
    );
    INSERT INTO chunks_v2
        SELECT chunk_id, document_id, page_start, page_end, section, text,
               content_hash
        FROM chunks WHERE document_id IN (SELECT document_id FROM documents);
    DROP TABLE chunks;
    ALTER TABLE chunks_v2 RENAME TO chunks;
    CREATE INDEX chunks_by_document ON chunks(document_id);

    CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY,
        owner_uid TEXT REFERENCES users(uid) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'done', 'error')),
        result TEXT, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX jobs_by_owner ON jobs(owner_uid, created_at);

    CREATE TABLE job_events (
        job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
        seq INTEGER NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (job_id, seq)
    );
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate(path: Path) -> None:
    """Creates the database, or upgrades it, to SCHEMA_VERSION."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        for number, step in enumerate(MIGRATIONS[version:], start=version + 1):
            try:
                connection.executescript(
                    f"BEGIN IMMEDIATE;\n{step}\n"
                    f"PRAGMA user_version = {number};\nCOMMIT;"
                )
            except sqlite3.Error:
                connection.rollback()
                raise
    finally:
        connection.close()
