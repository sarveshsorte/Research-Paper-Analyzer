from pathlib import Path
import sqlite3
from typing import Any
from database.repositories.chunk_repository import InMemoryChunkRepository
from database.repositories.paper_repository import InMemoryPaperRepository

paper_repository = InMemoryPaperRepository({})
chunk_repository = InMemoryChunkRepository(set())
chunks_store: dict[str, dict[str, Any]] = {}


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
