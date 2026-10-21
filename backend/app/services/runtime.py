"""Runtime storage and deterministic retrieval used until an LLM is configured."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from document_pipeline.ingestion.service import IngestedPaper, ingest_pdf


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "running"
    result: Any = None
    error: dict[str, str] | None = None
    steps: list[dict[str, Any]] | None = None


class RuntimeStore:
    """Small SQLite-backed store shared by API routes in one application."""

    def __init__(self, path: str = "storage/researchlens.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
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
                """
            )

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

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [self._document(row) for row in db.execute(
                "SELECT * FROM documents ORDER BY uploaded_at DESC"
            )]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return self._document(row) if row else None

    def get_file(self, document_id: str) -> bytes | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT file_bytes FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return bytes(row["file_bytes"]) if row and row["file_bytes"] else None

    def create_document(self, filename: str, content: bytes, source: str = "upload") -> dict[str, Any]:
        document_id = f"DOC-{uuid.uuid4().hex[:12]}"
        title = re.sub(r"[-_]+", " ", Path(filename).stem).strip() or "Untitled paper"
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO documents
                (document_id,title,filename,status,source,uploaded_at,file_bytes,progress)
                VALUES (?,?,?,?,?,?,?,?)""",
                (document_id, title.title(), filename, "processing", source, now, content, 0),
            )
        return self.get_document(document_id) or {}

    def update_document(self, document_id: str, **values: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as db:
            db.execute(
                f"UPDATE documents SET {assignments} WHERE document_id = ?",
                (*values.values(), document_id),
            )

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as db:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            result = db.execute(
                "DELETE FROM documents WHERE document_id = ?", (document_id,)
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

    def chunk(self, chunk_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        if not row:
            return None
        doc = self.get_document(row["document_id"])
        return {
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "page": row["page_start"],
            "section": row["section"] or "",
            "text": row["text"],
            "title": doc["title"] if doc else "",
        }

    def search(self, question: str, document_ids: list[str]) -> list[dict[str, Any]]:
        terms = {term for term in re.findall(r"\w+", question.lower()) if len(term) > 2}
        if not terms:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM chunks WHERE document_id IN ({placeholders})",
                document_ids,
            ).fetchall()
        scored = []
        for row in rows:
            text_terms = set(re.findall(r"\w+", row["text"].lower()))
            score = len(terms & text_terms)
            if score:
                doc = self.get_document(row["document_id"])
                scored.append((score, row, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "page": row["page_start"],
                "section": row["section"],
                "quote": row["text"],
                "title": doc["title"] if doc else "",
            }
            for _, row, doc in scored[:8]
        ]

    async def process(self, document_id: str) -> None:
        document = self.get_document(document_id)
        if not document:
            return
        try:
            content = self.get_file(document_id)
            if not content:
                raise ValueError("The uploaded PDF is empty.")
            self.update_document(document_id, progress=20)
            paper = await asyncio.to_thread(
                ingest_pdf,
                content,
                workspace_id="default",
                paper_id=document_id,
                paper_title=document["title"],
                ocr_fallback=False,
            )
            self.update_document(document_id, progress=80)
            self.save_paper(paper)
        except Exception as exc:
            self.update_document(
                document_id, status="failed", progress=None, error=str(exc)
            )

    def create_job(self, kind: str, result: Any = None) -> Job:
        job = Job(
            job_id=f"job_{uuid.uuid4().hex[:10]}",
            kind=kind,
            result=result,
            steps=[],
        )
        self.jobs[job.job_id] = job
        return job


store = RuntimeStore()
