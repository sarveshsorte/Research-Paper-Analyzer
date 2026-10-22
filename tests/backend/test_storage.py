"""The SQLite store: schema migrations, ownership and durable jobs."""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from backend.app.services import database
from backend.app.services.runtime import (
    INTERRUPTED_JOB,
    INTERRUPTED_UPLOAD,
    RuntimeStore,
)


def test_a_new_database_is_created_at_the_latest_version(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "claimlens.sqlite3"

    RuntimeStore(path)

    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == (
        database.SCHEMA_VERSION
    )
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in rows}
    assert {"users", "documents", "chunks", "jobs", "job_events"} <= tables


def test_an_existing_database_keeps_its_documents(tmp_path: Path) -> None:
    # A database file written before migrations existed (user_version 0).
    path = tmp_path / "claimlens.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(database.MIGRATIONS[0])
    connection.executescript(
        """
        INSERT INTO documents (document_id, title, filename, status, source,
            uploaded_at) VALUES ('DOC-old', 'Old paper', 'old.pdf', 'ready',
            'upload', '2026-10-01T00:00:00+00:00');
        INSERT INTO chunks VALUES ('c1', 'DOC-old', 1, 1, NULL, 'kept', 'h1');
        INSERT INTO chunks VALUES ('c2', 'DOC-gone', 1, 1, NULL, 'orphan', 'h2');
        """
    )
    connection.close()

    store = RuntimeStore(path)

    # Old documents become demo documents; chunks of deleted documents are dropped.
    assert [doc["document_id"] for doc in store.list_documents(None)] == ["DOC-old"]
    assert store.chunk("c1", None) is not None
    assert store.chunk("c2", None) is None


def test_documents_are_visible_only_to_their_owner(
    store: RuntimeStore, add_user: Callable[[str], None]
) -> None:
    add_user("ada")
    add_user("grace")
    ada_doc = store.create_document("a.pdf", b"%PDF", "ada")["document_id"]
    demo_doc = store.create_document("d.pdf", b"%PDF", None)["document_id"]

    assert [d["document_id"] for d in store.list_documents("ada")] == [ada_doc]
    assert [d["document_id"] for d in store.list_documents(None)] == [demo_doc]
    assert store.list_documents("grace") == []

    assert store.get_document(ada_doc, "grace") is None
    assert store.get_document(ada_doc, None) is None
    assert store.get_file(ada_doc, "grace") is None
    assert store.delete_document(ada_doc, "grace") is False
    assert store.get_document(ada_doc, "ada") is not None


def test_deleting_a_document_deletes_its_chunks(
    store: RuntimeStore,
    add_user: Callable[[str], None],
    add_ready_document: Callable[[str | None], str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    chunk_ids = [hit["chunk_id"] for hit in store.search("adapters", [document_id])]
    assert chunk_ids

    assert store.delete_document(document_id, "ada") is True

    assert all(store.chunk(chunk_id, "ada") is None for chunk_id in chunk_ids)
    assert store.search("adapters", [document_id]) == []


def test_chunks_follow_their_document_owner(
    store: RuntimeStore,
    add_user: Callable[[str], None],
    add_ready_document: Callable[[str | None], str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    chunk_id = store.search("adapters", [document_id])[0]["chunk_id"]

    assert store.chunk(chunk_id, "ada") is not None
    assert store.chunk(chunk_id, "grace") is None
    assert store.chunk(chunk_id, None) is None


def test_jobs_and_their_steps_survive_a_restart(
    store: RuntimeStore, add_user: Callable[[str], None]
) -> None:
    add_user("ada")
    job = store.create_job("query", "ada")
    store.add_job_step(job.job_id, {"type": "retrieve", "message": "Found 3 passages"})
    store.finish_job(job.job_id, {"answer": "Yes.", "claims": []})

    restarted = RuntimeStore(store.path)

    saved = restarted.get_job(job.job_id, "ada")
    assert saved is not None
    assert (saved.kind, saved.status, saved.result) == (
        "query",
        "done",
        {"answer": "Yes.", "claims": []},
    )
    assert [step for _, step in restarted.job_steps(job.job_id)] == [
        {"type": "started", "message": "Processing request"},
        {"type": "retrieve", "message": "Found 3 passages"},
    ]
    assert restarted.get_job(job.job_id, None) is None


def test_a_restart_fails_work_that_was_still_running(store: RuntimeStore) -> None:
    job = store.create_job("query", None)
    document_id = store.create_document("a.pdf", b"%PDF", None)["document_id"]

    restarted = RuntimeStore(store.path)

    saved_job = restarted.get_job(job.job_id, None)
    assert saved_job is not None
    assert (saved_job.status, saved_job.error) == ("error", INTERRUPTED_JOB)
    document = restarted.get_document(document_id, None)
    assert document is not None
    assert (document["status"], document["error"]) == ("failed", INTERRUPTED_UPLOAD)
