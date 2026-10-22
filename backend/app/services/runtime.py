"""Runtime storage and deterministic retrieval used until an LLM is configured.

Documents and jobs belong to a Firebase uid. `owner_uid=None` is the shared,
account-free demo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.services import database
from document_pipeline.ingestion.service import IngestedPaper, ingest_pdf

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


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "running"
    result: Any = None
    error: dict[str, str] | None = None


class RuntimeStore:
    """SQLite-backed store shared by the API routes of one application."""

    def __init__(self, path: str | Path = "storage/researchlens.sqlite3") -> None:
        self.path = Path(path)
        self._known_users: set[str] = set()
        database.migrate(self.path)
        self._recover_interrupted_work()

    def _connect(self) -> sqlite3.Connection:
        return database.connect(self.path)

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
        return {
            "document_id": row["document_id"],
            "title": row["title"],
            "filename": row["filename"],
            "pages": row["pages"],
            "chunks": row["chunks"] or None,
            "status": row["status"],
            "source": row["source"],
            "url": row["url"],
            "progress": row["progress"],
            "error": row["error"],
            "uploaded_at": row["uploaded_at"],
        }

    def list_documents(self, owner_uid: str | None) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [self._document(row) for row in db.execute(
                """SELECT * FROM documents WHERE owner_uid IS ?
                ORDER BY uploaded_at DESC""",
                (owner_uid,),
            )]

    def get_document(
        self, document_id: str, owner_uid: str | None
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE document_id = ? AND owner_uid IS ?",
                (document_id, owner_uid),
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

    def create_document(
        self,
        filename: str,
        content: bytes,
        owner_uid: str | None,
        source: str = "upload",
    ) -> dict[str, Any]:
        document_id = f"DOC-{uuid.uuid4().hex[:12]}"
        title = re.sub(r"[-_]+", " ", Path(filename).stem).strip() or "Untitled paper"
        with self._connect() as db:
            db.execute(
                """INSERT INTO documents
                (document_id,owner_uid,title,filename,status,source,uploaded_at,
                file_bytes,progress)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (document_id, owner_uid, title.title(), filename, "processing",
                 source, _now(), content, 0),
            )
        return self.get_document(document_id, owner_uid) or {}

    def update_document(self, document_id: str, **values: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as db:
            db.execute(
                f"UPDATE documents SET {assignments} WHERE document_id = ?",
                (*values.values(), document_id),
            )

    def delete_document(self, document_id: str, owner_uid: str | None) -> bool:
        """Deletes the document and, through the foreign key, its chunks."""
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM documents WHERE document_id = ? AND owner_uid IS ?",
                (document_id, owner_uid),
            )
        return result.rowcount > 0

    def save_paper(self, paper: IngestedPaper) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (paper.paper_id,))
            for chunk in paper.chunks:
                db.execute(
                    """INSERT INTO chunks
                    (chunk_id,document_id,page_start,page_end,section,text,content_hash)
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        chunk.chunk_id,
                        paper.paper_id,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.section,
                        chunk.text,
                        chunk.content_hash or hashlib.sha256(chunk.text.encode()).hexdigest(),
                    ),
                )
            db.execute(
                """UPDATE documents SET title=?, pages=?, chunks=?, status=?,
                progress=?, error=? WHERE document_id=?""",
                (paper.paper_title, len(paper.pages), len(paper.chunks),
                 "ready", None, None, paper.paper_id),
            )

    def sections(self, document_id: str) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT DISTINCT section FROM chunks WHERE document_id = ? AND section IS NOT NULL",
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

    def search(self, question: str, document_ids: list[str]) -> list[dict[str, Any]]:
        """Searches documents the caller has already been checked to own."""
        terms = {term for term in re.findall(r"\w+", question.lower()) if len(term) > 2}
        if not terms:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT chunks.*, documents.title FROM chunks
                JOIN documents USING (document_id)
                WHERE document_id IN ({placeholders})""",
                document_ids,
            ).fetchall()
        scored = []
        for row in rows:
            text_terms = set(re.findall(r"\w+", row["text"].lower()))
            score = len(terms & text_terms)
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "page": row["page_start"],
                "section": row["section"],
                "quote": row["text"],
                "title": row["title"],
            }
            for _, row in scored[:8]
        ]

    async def process(self, document_id: str) -> None:
        with self._connect() as db:
            row = db.execute(
                "SELECT title, file_bytes FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if not row:
            return
        try:
            if not row["file_bytes"]:
                raise ValueError("The uploaded PDF is empty.")
            self.update_document(document_id, progress=20)
            paper = await asyncio.to_thread(
                ingest_pdf,
                bytes(row["file_bytes"]),
                workspace_id="default",
                paper_id=document_id,
                paper_title=row["title"],
                ocr_fallback=False,
            )
            self.update_document(document_id, progress=80)
            self.save_paper(paper)
        except Exception as exc:
            self.update_document(
                document_id, status="failed", progress=None, error=str(exc)
            )

    # Jobs

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"],
            kind=row["kind"],
            status=row["status"],
            result=json.loads(row["result"]) if row["result"] is not None else None,
            error=json.loads(row["error"]) if row["error"] is not None else None,
        )

    def create_job(self, kind: str, owner_uid: str | None) -> Job:
        job = Job(job_id=f"job_{uuid.uuid4().hex[:10]}", kind=kind)
        now = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO jobs
                (job_id,owner_uid,kind,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?)""",
                (job.job_id, owner_uid, kind, job.status, now, now),
            )
        self.add_job_step(
            job.job_id, {"type": "started", "message": "Processing request"}
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
