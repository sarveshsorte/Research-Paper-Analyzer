from typing import Protocol

from query_pipeline.app.schemas.retrieval import RetrievalCandidate, RetrievalFilters


class DenseRetriever(Protocol):
    async def search(
        self,
        embedding: list[float],
        workspace_id: str,
        paper_ids: list[str],
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievalCandidate]:
        ...


class QdrantDenseRetriever:
    """Qdrant adapter; payload validation remains owned by RetrievalCandidate."""

    def __init__(self, client: object, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def search(
        self, embedding: list[float], workspace_id: str, paper_ids: list[str],
        filters: RetrievalFilters, limit: int
    ) -> list[RetrievalCandidate]:
        import asyncio
        return await asyncio.to_thread(
            self._search_sync, embedding, workspace_id, paper_ids, filters, limit
        )

    def _search_sync(self, embedding, workspace_id, paper_ids, filters, limit):
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        conditions = [
            FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
            FieldCondition(key="paper_id", match=MatchAny(any=paper_ids)),
        ]
        if filters.sections:
            conditions.append(FieldCondition(
                key="section", match=MatchAny(any=filters.sections)
            ))
        try:
            if hasattr(self.client, "collection_exists") and not self.client.collection_exists(self.collection_name):
                return []
        except Exception:
            pass

        try:
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=embedding,
                    query_filter=Filter(must=conditions),
                    limit=limit,
                    with_payload=True,
                )
                points = response.points
            elif hasattr(self.client, "search"):
                points = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=embedding,
                    query_filter=Filter(must=conditions),
                    limit=limit,
                    with_payload=True,
                )
            else:
                points = []
        except Exception as exc:
            if "not found" in str(exc).lower():
                return []
            raise
        result = []
        for point in points:
            payload = point.payload or {}
            page = int(payload.get("page", 1))
            result.append(RetrievalCandidate(
                chunk_id=str(payload["chunk_id"]),
                workspace_id=str(payload["workspace_id"]),
                paper_id=str(payload["paper_id"]),
                paper_title=str(payload["paper_title"]),
                text=str(payload["text"]),
                page_start=int(payload.get("page_start", page)),
                page_end=int(payload.get("page_end", page)),
                section=payload.get("section"),
                content_type=str(payload.get("content_type", "text")),
                chunk_index=payload.get("chunk_index"),
                content_hash=payload.get("content_hash"),
                dense_score=float(point.score),
            ))
        return result
