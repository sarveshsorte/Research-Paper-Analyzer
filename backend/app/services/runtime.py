"""The backend's data layer: users, documents, chunks, chunk vectors and jobs.

Documents and jobs belong to a Firebase uid. `owner_uid=None` is the shared,
account-free demo.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import uuid
from collections.abc import Coroutine, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.services import database

INTERRUPTED_UPLOAD = (
    "Processing stopped when the server restarted. Upload the PDF again."
)
INTERRUPTED_JOB = {
    "code": "INTERNAL_ERROR",
    "message": "The server restarted before this finished. Try again.",
}

# Background tasks are referenced here until they finish, so they are not
# garbage-collected while still running.
_background_tasks: set[asyncio.Task[None]] = set()


def run_in_background(coroutine: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coroutine)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def title_from_filename(filename: str) -> str:
    title = re.sub(r"[-_]+", " ", Path(filename).stem).strip()
    return title.title() if title else "Untitled paper"


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "running"
    result: Any = None
    error: dict[str, str] | None = None
    created_at: str = ""


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    document_id: str
    title: str
    page_start: int
    page_end: int
    section: str | None
    text: str
    content_hash: str


@dataclass(frozen=True)
class FileRecord:
    title: str
    source: str
    url: str | None
    content: bytes | None


@dataclass(frozen=True)
class ChunkToSave:
    chunk_id: str
    page_start: int
    page_end: int
    section: str | None
    text: str
    content_hash: str


class RuntimeStore:
    """SQLite-backed store shared by the API routes of one application."""

    def __init__(self, path: str | Path = "storage/researchlens.sqlite3") -> None:
        self.path = Path(path)
        self._known_users: set[str] = set()
        database.migrate(self.path)
        self._recover_interrupted_work()

    def _connect(self) -> sqlite3.Connection:
        return database.connect(self.path)

    def ping(self) -> None:
        with self._connect() as db:
            db.execute("SELECT 1").fetchone()

    def _recover_interrupted_work(self) -> None:
        """Uploads and jobs that were running when the server stopped never finish."""
        with self._connect() as db:
            db.execute(
                """UPDATE documents SET status='failed', progress=NULL, error=?
                WHERE status='processing'""",
                (INTERRUPTED_UPLOAD,),
            )
            db.execute(
                """UPDATE jobs SET status='error', error=?, updated_at=?
                WHERE status='running'""",
                (json.dumps(INTERRUPTED_JOB), _now()),
            )

    # Users

    def upsert_user(
        self,
        uid: str,
        *,
        email: str | None,
        name: str,
        picture: str | None,
        provider: str,
    ) -> None:
        now = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO users
                (uid,email,name,picture,provider,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET email=excluded.email,
                name=excluded.name, picture=excluded.picture,
                provider=excluded.provider, updated_at=excluded.updated_at""",
                (uid, email, name, picture, provider, now, now),
            )
        self._known_users.add(uid)

    def is_known_user(self, uid: str) -> bool:
        """True once this process has stored the user (saves a write per request)."""
        return uid in self._known_users

    # Documents

    @staticmethod
    def _document(row: sqlite3.Row) -> dict[str, Any]:
        document = {
            "document_id": row["document_id"],
            "title": row["title"],
            "filename": row["filename"],
            "pages": row["pages"],
            "chunks": row["chunks"] or None,
            "status": row["status"],
            "source": row["source"],
            "progress": row["progress"],
            "error": row["error"],
            "uploaded_at": row["uploaded_at"],
        }
        # Optional fields are left out rather than sent as null.
        for key in ("url", "authors", "year"):
            if row[key] is not None:
                document[key] = row[key]
        return document

    def list_documents(
        self, owner_uid: str | None, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM documents WHERE owner_uid IS ?"
        parameters: list[Any] = [owner_uid]
        if status:
            query += " AND status = ?"
            parameters.append(status)
        with self._connect() as db:
            rows = db.execute(query + " ORDER BY uploaded_at DESC", parameters)
            return [self._document(row) for row in rows]

    def get_document(
        self, document_id: str, owner_uid: str | None
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE document_id = ? AND owner_uid IS ?",
                (document_id, owner_uid),
            ).fetchone()
        return self._document(row) if row else None

    def find_document(
        self,
        owner_uid: str | None,
        *,
        sha256: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any] | None:
        """The caller's existing document with this file hash or source URL."""
        column, value = ("sha256", sha256) if sha256 else ("url", url)
        if not value:
            return None
        with self._connect() as db:
            row = db.execute(
                f"""SELECT * FROM documents WHERE owner_uid IS ? AND {column} = ?
                ORDER BY uploaded_at DESC LIMIT 1""",
                (owner_uid, value),
            ).fetchone()
        return self._document(row) if row else None

    def get_file(self, document_id: str, owner_uid: str | None) -> bytes | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT file_bytes FROM documents
                WHERE document_id = ? AND owner_uid IS ?""",
                (document_id, owner_uid),
            ).fetchone()
        return bytes(row["file_bytes"]) if row and row["file_bytes"] else None

    def file_for_processing(self, document_id: str) -> FileRecord | None:
        """The PDF and its known details for the background pipeline."""
        with self._connect() as db:
            row = db.execute(
                """SELECT title, source, url, file_bytes FROM documents
                WHERE document_id = ?""",
                (document_id,),
            ).fetchone()
        if not row:
            return None
        return FileRecord(
            title=row["title"],
            source=row["source"],
            url=row["url"],
            content=bytes(row["file_bytes"]) if row["file_bytes"] else None,
        )

    def set_file(self, document_id: str, content: bytes, sha256: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE documents SET file_bytes = ?, sha256 = ? WHERE document_id = ?",
                (content, sha256, document_id),
            )

    def fill_metadata(
        self, document_id: str, *, authors: str | None, year: int | None
    ) -> None:
        """Sets authors and year only where they are still unknown."""
        with self._connect() as db:
            db.execute(
                """UPDATE documents SET authors = COALESCE(authors, ?),
                year = COALESCE(year, ?) WHERE document_id = ?""",
                (authors, year, document_id),
            )

    def create_document(
        self,
        filename: str,
        content: bytes | None,
        owner_uid: str | None,
        source: str = "upload",
        *,
        title: str | None = None,
        url: str | None = None,
        authors: str | None = None,
        year: int | None = None,
        sha256: str | None = None,
    ) -> dict[str, Any]:
        document_id = f"DOC-{uuid.uuid4().hex[:12]}"
        with self._connect() as db:
            db.execute(
                """INSERT INTO documents
                (document_id,owner_uid,title,filename,status,source,uploaded_at,
                file_bytes,progress,url,authors,year,sha256)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id,
                    owner_uid,
                    title or title_from_filename(filename),
                    filename,
                    "processing",
                    source,
                    _now(),
                    content,
                    0,
                    url,
                    authors,
                    year,
                    sha256,
                ),
            )
        return self.get_document(document_id, owner_uid) or {}

    def update_document(self, document_id: str, **values: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as db:
            db.execute(
                f"UPDATE documents SET {assignments} WHERE document_id = ?",
                (*values.values(), document_id),
            )

    def mark_ready(
        self, document_id: str, *, title: str, pages: int, chunks: int
    ) -> None:
        self.update_document(
            document_id,
            title=title,
            pages=pages,
            chunks=chunks,
            status="ready",
            progress=None,
            error=None,
        )

    def mark_failed(self, document_id: str, message: str) -> None:
        self.update_document(document_id, status="failed", progress=None, error=message)

    def delete_document(self, document_id: str, owner_uid: str | None) -> bool:
        """Deletes the document and, through foreign keys, its chunks and vectors."""
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM documents WHERE document_id = ? AND owner_uid IS ?",
                (document_id, owner_uid),
            )
        return result.rowcount > 0

    def ready_documents(self, document_ids: Sequence[str]) -> set[str]:
        if not document_ids:
            return set()
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT document_id FROM documents
                WHERE status = 'ready' AND document_id IN ({placeholders})""",
                list(document_ids),
            )
            return {row["document_id"] for row in rows}

    # Chunks

    def save_chunks(self, document_id: str, chunks: Iterable[ChunkToSave]) -> None:
        """Replaces the document's chunks (and so its vectors' meaning)."""
        with self._connect() as db:
            db.execute(
                "DELETE FROM chunk_vectors WHERE document_id = ?", (document_id,)
            )
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            db.executemany(
                """INSERT INTO chunks
                (chunk_id,document_id,page_start,page_end,section,text,content_hash)
                VALUES (?,?,?,?,?,?,?)""",
                [
                    (
                        c.chunk_id,
                        document_id,
                        c.page_start,
                        c.page_end,
                        c.section,
                        c.text,
                        c.content_hash,
                    )
                    for c in chunks
                ],
            )

    def sections(self, document_id: str) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT section FROM chunks
                WHERE document_id = ? AND section IS NOT NULL
                GROUP BY section ORDER BY MIN(page_start)""",
                (document_id,),
            )
            return [row["section"] for row in rows]

    def chunk(self, chunk_id: str, owner_uid: str | None) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT chunks.*, documents.title FROM chunks
                JOIN documents USING (document_id)
                WHERE chunk_id = ? AND documents.owner_uid IS ?""",
                (chunk_id, owner_uid),
            ).fetchone()
        if not row:
            return None
        return {
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "page": row["page_start"],
            "section": row["section"] or "",
            "text": row["text"],
            "title": row["title"],
        }

    @staticmethod
    def _stored_chunk(row: sqlite3.Row) -> StoredChunk:
        return StoredChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            title=row["title"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            section=row["section"],
            text=row["text"],
            content_hash=row["content_hash"],
        )

    def chunks_by_id(self, chunk_ids: Iterable[str]) -> dict[str, StoredChunk]:
        """Chunk text from this database: the reference for the citation guard."""
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT chunks.*, documents.title FROM chunks
                JOIN documents USING (document_id)
                WHERE chunk_id IN ({placeholders})""",
                ids,
            ).fetchall()
        return {row["chunk_id"]: self._stored_chunk(row) for row in rows}

    def first_chunks(self, document_id: str, limit: int) -> list[StoredChunk]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT chunks.*, documents.title FROM chunks
                JOIN documents USING (document_id)
                WHERE document_id = ?
                ORDER BY chunks.page_start, chunks.rowid LIMIT ?""",
                (document_id, limit),
            ).fetchall()
        return [self._stored_chunk(row) for row in rows]

    # Chunk vectors (the vector index lives in this database)

    def save_vectors(
        self, model: str, items: Sequence[tuple[str, str, int, bytes]]
    ) -> int:
        """Upserts (chunk_id, document_id, dimension, float32 bytes) for `model`."""
        with self._connect() as db:
            db.executemany(
                """INSERT INTO chunk_vectors
                (chunk_id,document_id,model,dimension,vector) VALUES (?,?,?,?,?)
                ON CONFLICT(chunk_id) DO UPDATE SET document_id=excluded.document_id,
                model=excluded.model, dimension=excluded.dimension,
                vector=excluded.vector""",
                [
                    (chunk_id, document_id, model, dimension, blob)
                    for chunk_id, document_id, dimension, blob in items
                ],
            )
        return len(items)

    def vectors(
        self, document_ids: Sequence[str], model: str
    ) -> list[tuple[StoredChunk, bytes]]:
        if not document_ids:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT chunks.*, documents.title, chunk_vectors.vector
                FROM chunk_vectors
                JOIN chunks USING (chunk_id)
                JOIN documents ON documents.document_id = chunk_vectors.document_id
                WHERE chunk_vectors.model = ?
                AND chunk_vectors.document_id IN ({placeholders})""",
                [model, *document_ids],
            ).fetchall()
        return [(self._stored_chunk(row), bytes(row["vector"])) for row in rows]

    def documents_with_vectors(
        self, document_ids: Sequence[str], model: str
    ) -> set[str]:
        if not document_ids:
            return set()
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT DISTINCT document_id FROM chunk_vectors
                WHERE model = ? AND document_id IN ({placeholders})""",
                [model, *document_ids],
            )
            return {row["document_id"] for row in rows}

    # Jobs

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"],
            kind=row["kind"],
            status=row["status"],
            result=json.loads(row["result"]) if row["result"] is not None else None,
            error=json.loads(row["error"]) if row["error"] is not None else None,
            created_at=row["created_at"],
        )

    def create_job(self, kind: str, owner_uid: str | None) -> Job:
        job = Job(job_id=f"job_{uuid.uuid4().hex[:10]}", kind=kind, created_at=_now())
        with self._connect() as db:
            db.execute(
                """INSERT INTO jobs
                (job_id,owner_uid,kind,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    job.job_id,
                    owner_uid,
                    kind,
                    job.status,
                    job.created_at,
                    job.created_at,
                ),
            )
        self.add_job_step(
            job.job_id, {"type": "started", "message": "Processing request", "t": 0}
        )
        return job

    def get_job(self, job_id: str, owner_uid: str | None) -> Job | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE job_id = ? AND owner_uid IS ?",
                (job_id, owner_uid),
            ).fetchone()
        return self._job(row) if row else None

    def add_job_step(self, job_id: str, step: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO job_events (job_id,seq,event,data,created_at)
                SELECT ?, COALESCE(MAX(seq), 0) + 1, 'step', ?, ?
                FROM job_events WHERE job_id = ?""",
                (job_id, json.dumps(step), _now(), job_id),
            )

    def job_steps(
        self, job_id: str, after: int = 0
    ) -> list[tuple[int, dict[str, Any]]]:
        """The job's steps with a sequence number above `after`, in order."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT seq, data FROM job_events
                WHERE job_id = ? AND event = 'step' AND seq > ? ORDER BY seq""",
                (job_id, after),
            ).fetchall()
        return [(row["seq"], json.loads(row["data"])) for row in rows]

    def finish_job(self, job_id: str, result: Any) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status='done', result=?, updated_at=? WHERE job_id=?",
                (json.dumps(result), _now(), job_id),
            )

    def fail_job(self, job_id: str, error: dict[str, str]) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status='error', error=?, updated_at=? WHERE job_id=?",
                (json.dumps(error), _now(), job_id),
            )
