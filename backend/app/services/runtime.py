from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from database.repositories.chunk_repository import InMemoryChunkRepository
from database.repositories.paper_repository import InMemoryPaperRepository

paper_repository = InMemoryPaperRepository({})
chunk_repository = InMemoryChunkRepository(set())
chunks_store: dict[str, dict[str, Any]] = {}


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


@dataclass(frozen=True)
class ChunkToSave:
    chunk_id: str
    page_start: int
    page_end: int
    section: str | None
    text: str
    content_hash: str


class RuntimeStore:
    """Store for persisting user accounts and sessions."""

    def __init__(self, path: str = "storage/data.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._known_users: set[str] = set()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    email TEXT,
                    name TEXT NOT NULL,
                    picture TEXT,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert_user(
        self,
        uid: str,
        *,
        email: str | None,
        name: str,
        picture: str | None,
        provider: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO users
                (uid, email, name, picture, provider, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    email=excluded.email,
                    name=excluded.name,
                    picture=excluded.picture,
                    provider=excluded.provider,
                    updated_at=excluded.updated_at""",
                (uid, email, name, picture, provider, now, now),
            )
        self._known_users.add(uid)

    def is_known_user(self, uid: str) -> bool:
        return uid in self._known_users

    def get_user(self, uid: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None


def publish_indexed_paper(workspace_id: str, paper_id: str) -> None:
    paper_repository.ready_by_workspace.setdefault(workspace_id, set()).add(paper_id)
    chunk_repository.indexed.add((workspace_id, paper_id))


def store_chunks(chunks: list[dict[str, Any]]) -> None:
    for c in chunks:
        chunks_store[c["chunk_id"]] = c


def sync_persisted_papers(bm25_index_path: str = "storage/bm25/index.sqlite3") -> None:
    path = Path(bm25_index_path)
    if not path.exists():
        return
    try:
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        cur.execute("SELECT DISTINCT workspace_id, paper_id FROM chunks_fts")
        for ws, pid in cur.fetchall():
            publish_indexed_paper(ws, pid)
        cur.execute("SELECT chunk_id, paper_id, page_start, section, text FROM chunks_fts")
        for cid, pid, pstart, sec, txt in cur.fetchall():
            chunks_store[cid] = {
                "chunk_id": cid,
                "document_id": pid,
                "page": int(pstart or 1),
                "section": sec or "Evidence Passage",
                "text": txt or "",
            }
        con.close()
    except Exception:
        pass


# Automatically discover persisted papers on start
sync_persisted_papers()
