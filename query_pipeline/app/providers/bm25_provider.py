import asyncio
from pathlib import Path
from typing import Protocol

from document_pipeline.indexing.bm25_indexer import BM25Indexer
from query_pipeline.app.pipeline.filters import matches_filters
from query_pipeline.app.schemas.retrieval import RetrievalCandidate, RetrievalFilters


class SparseRetriever(Protocol):
    async def search(
        self,
        query: str,
        workspace_id: str,
        paper_ids: list[str],
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievalCandidate]:
        ...


class InMemoryBM25Retriever:
    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self.candidates = candidates

    async def search(
        self, query: str, workspace_id: str, paper_ids: list[str],
        filters: RetrievalFilters, limit: int
    ) -> list[RetrievalCandidate]:
        terms = set(query.lower().split())
        scored = []
        for candidate in self.candidates:
            if candidate.workspace_id != workspace_id or candidate.paper_id not in paper_ids:
                continue
            if not matches_filters(candidate, filters):
                continue
            score = sum(term in candidate.text.lower() for term in terms)
            if score:
                scored.append(candidate.model_copy(update={"sparse_score": float(score)}))
        return sorted(scored, key=lambda item: item.sparse_score or 0, reverse=True)[:limit]


class SQLiteBM25Retriever:
    """Search the persistent SQLite FTS index written by document ingestion."""

    def __init__(self, database_path: str | Path) -> None:
        self.indexer = BM25Indexer(database_path)

    async def search(
        self,
        query: str,
        workspace_id: str,
        paper_ids: list[str],
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievalCandidate]:
        hits = await asyncio.to_thread(
            self.indexer.search,
            query,
            workspace_id=workspace_id,
            paper_ids=paper_ids,
            limit=limit,
            sections=filters.sections,
            page_start=filters.page_start,
            page_end=filters.page_end,
            content_types=filters.content_types,
        )
        return [
            RetrievalCandidate(
                chunk_id=hit.chunk.chunk_id,
                workspace_id=hit.chunk.workspace_id,
                paper_id=hit.chunk.paper_id,
                paper_title=hit.chunk.paper_title,
                text=hit.chunk.text,
                page_start=hit.chunk.page_start,
                page_end=hit.chunk.page_end,
                section=hit.chunk.section,
                content_type=hit.chunk.content_type,
                content_hash=hit.chunk.content_hash,
                sparse_score=hit.score,
            )
            for hit in hits
        ]
