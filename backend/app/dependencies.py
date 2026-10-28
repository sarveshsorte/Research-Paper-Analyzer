from functools import lru_cache

from backend.app.config import Settings, get_settings
from query_pipeline.app.pipeline.orchestrator import QueryOrchestrator
from query_pipeline.app.providers.fake_providers import FakeDenseRetriever, FakeGenerator, FakeEmbeddingProvider
from query_pipeline.app.providers.embedding_provider import OpenAICompatibleEmbeddingProvider
from query_pipeline.app.providers.nemotron_provider import OpenAICompatibleGenerationProvider
from query_pipeline.app.providers.qdrant_provider import QdrantDenseRetriever
from query_pipeline.app.providers.bm25_provider import SQLiteBM25Retriever
from query_pipeline.app.providers.reranker_provider import NvidiaNemotronReranker, ScoreBasedReranker
from database.repositories.workspace_repository import InMemoryWorkspaceRepository
from backend.app.services.runtime import chunk_repository, paper_repository
from query_pipeline.app.schemas.retrieval import RetrievalCandidate


@lru_cache
def get_orchestrator() -> QueryOrchestrator:
    settings: Settings = get_settings()
    candidates: list[RetrievalCandidate] = []
    if not settings.use_fake_providers:
        from qdrant_client import QdrantClient

        if not settings.embedding_api_key or not settings.embedding_base_url:
            raise RuntimeError("Real embedding provider is not configured")
        if not settings.nvidia_api_key or not settings.nvidia_model:
            raise RuntimeError("Real generation provider is not configured")
        from backend.app.services.qdrant import get_shared_qdrant_client

        qdrant = get_shared_qdrant_client(settings)

        # ── Reranker: use Nemotron-3.5-Rerank if credentials are present,
        #    fall back to the lightweight keyword scorer otherwise.
        if settings.reranker_api_key and settings.reranker_base_url and settings.reranker_model:
            reranker = NvidiaNemotronReranker(
                base_url=settings.reranker_base_url,
                api_key=settings.reranker_api_key,
                model=settings.reranker_model,
            )
        else:
            reranker = ScoreBasedReranker()

        return QueryOrchestrator(
            settings=settings,
            embedding_provider=OpenAICompatibleEmbeddingProvider(
                settings.embedding_base_url,
                settings.embedding_api_key,
                settings.embedding_model or "",
            ),
            dense_retriever=QdrantDenseRetriever(
                qdrant, settings.qdrant_collection
            ),
            sparse_retriever=SQLiteBM25Retriever(settings.bm25_index_path),
            reranker=reranker,
            generator=OpenAICompatibleGenerationProvider(
                settings.nvidia_base_url,
                settings.nvidia_api_key,
                settings.nvidia_model,
            ),
            paper_repository=paper_repository,
            chunk_repository=chunk_repository,
            workspace_repository=InMemoryWorkspaceRepository(set()),
        )
    return QueryOrchestrator(
        settings=settings,
        embedding_provider=FakeEmbeddingProvider(),
        dense_retriever=FakeDenseRetriever(candidates),
        generator=FakeGenerator(),
        paper_repository=paper_repository,
        chunk_repository=chunk_repository,
        workspace_repository=InMemoryWorkspaceRepository(set()),
    )
