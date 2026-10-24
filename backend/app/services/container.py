"""Builds the long-lived services once per process (in the app's lifespan)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from backend.app.adapters.document_pipeline import DocumentPipelineAdapter
from backend.app.adapters.providers import (
    BM25SparseRetriever,
    ChatModel,
    HashingEmbedder,
    RemoteEmbedder,
)
from backend.app.adapters.query_pipeline import QueryPipelineAdapter
from backend.app.config import Settings
from backend.app.services.claim_check import ClaimChecker
from backend.app.services.jobs import JobRunner
from backend.app.services.runtime import RuntimeStore
from backend.app.services.search import PdfDownloader, SearchService
from document_pipeline.indexing import BM25Indexer

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    store: RuntimeStore
    http: httpx.AsyncClient
    documents: DocumentPipelineAdapter
    queries: QueryPipelineAdapter
    jobs: JobRunner
    search: SearchService
    downloader: PdfDownloader
    claims: ClaimChecker

    @property
    def mock_ai(self) -> bool:
        """True while a local fallback stands in for the embedding or language model."""
        return (
            isinstance(self.documents.embedder, HashingEmbedder)
            or self.queries.chat is None
        )

    async def close(self) -> None:
        await self.http.aclose()


def _input_types(settings: Settings) -> tuple[str | None, str | None]:
    mode = settings.embedding_input_type
    host = (urlsplit(settings.embedding_base_url or "").hostname or "").lower()
    if mode == "on" or (mode == "auto" and host.endswith("nvidia.com")):
        return "passage", "query"
    return None, None


def build_services(settings: Settings, store: RuntimeStore) -> Services:
    http = httpx.AsyncClient(
        headers={"User-Agent": "ClaimLens/0.2 (research paper analyzer)"},
        limits=httpx.Limits(max_connections=20),
    )
    if (
        settings.embedding_base_url
        and settings.embedding_api_key
        and settings.embedding_model
    ):
        passage_type, query_type = _input_types(settings)

        def remote(input_type: str | None) -> RemoteEmbedder:
            return RemoteEmbedder(
                http,
                base_url=settings.embedding_base_url or "",
                api_key=settings.embedding_api_key or "",
                model=settings.embedding_model or "",
                dimension=settings.embedding_dimension,
                input_type=input_type,
            )

        passage_embedder, query_embedder = remote(passage_type), remote(query_type)
        logger.info("embeddings=remote model=%s", settings.embedding_model)
    else:
        passage_embedder = query_embedder = HashingEmbedder()
        logger.warning("embeddings=local (set EMBEDDING_BASE_URL/API_KEY/MODEL)")

    chat = None
    if settings.nebius_api_key and settings.nebius_model:
        chat = ChatModel(
            http,
            base_url=settings.nebius_base_url,
            api_key=settings.nebius_api_key,
            model=settings.nebius_model,
        )
        logger.info("generation=nebius model=%s", settings.nebius_model)
    else:
        logger.warning("generation=extractive (set NEBIUS_API_KEY and NEBIUS_MODEL)")

    bm25 = BM25Indexer(settings.bm25_index_path)
    documents = DocumentPipelineAdapter(
        store, passage_embedder, bm25, concurrency=settings.process_concurrency
    )
    queries = QueryPipelineAdapter(
        store, settings, query_embedder, BM25SparseRetriever(bm25, store), chat
    )
    downloader = PdfDownloader(http, settings.download_allowed_hosts)
    search = SearchService(
        http,
        downloader,
        semantic_scholar_key=settings.semantic_scholar_api_key,
        tavily_key=settings.tavily_api_key,
    )
    return Services(
        settings=settings,
        store=store,
        http=http,
        documents=documents,
        queries=queries,
        jobs=JobRunner(
            store,
            concurrency=settings.job_concurrency,
            timeout=settings.job_timeout_seconds,
        ),
        search=search,
        downloader=downloader,
        claims=ClaimChecker(store, search, downloader, documents, queries),
    )
