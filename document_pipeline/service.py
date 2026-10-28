"""Configured entry point for indexing one PDF in the ResearchLens indexes."""

from pathlib import Path

from backend.app.config import Settings, get_settings
from document_pipeline.ingestion.pdf_loader import PDFSource
from document_pipeline.indexing import BM25Indexer, QdrantVectorIndexer
from document_pipeline.pipeline import IndexingResult, index_prepared_paper, ingest_and_embed_pdf
from query_pipeline.app.providers.embedding_provider import (
    OpenAICompatibleEmbeddingProvider,
)


async def index_pdf(
    source: PDFSource,
    *,
    workspace_id: str,
    paper_id: str,
    paper_title: str | None = None,
    ocr_dpi: int = 300,
    ocr_language: str = "eng",
    settings: Settings | None = None,
) -> IndexingResult:
    """Ingest, embed, and index a PDF using the configured project services.

    This writes to the configured Qdrant collection and local BM25 database.
    It deliberately does not publish paper readiness; the API/repository layer
    must do that only after this function returns successfully.
    """
    settings = settings or get_settings()
    if settings.use_fake_providers:
        raise RuntimeError(
            "Document indexing requires real providers; set APP_ENV=production "
            "or configure USE_FAKE_PROVIDERS=false for an explicit indexing run"
        )
    required = {
        "EMBEDDING_BASE_URL": settings.embedding_base_url,
        "EMBEDDING_API_KEY": settings.embedding_api_key,
        "EMBEDDING_MODEL": settings.embedding_model,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Document indexing is not configured; set " + ", ".join(missing)
        )

    from backend.app.services.qdrant import get_shared_qdrant_client

    client = get_shared_qdrant_client(settings)

    prepared = await ingest_and_embed_pdf(
        source,
        workspace_id=workspace_id,
        paper_id=paper_id,
        paper_title=paper_title,
        ocr_dpi=ocr_dpi,
        ocr_language=ocr_language,
        embedding_provider=OpenAICompatibleEmbeddingProvider(
            settings.embedding_base_url or "",
            settings.embedding_api_key or "",
            settings.embedding_model or "",
        ),
        expected_dimension=settings.embedding_dimension,
    )
    try:
        from backend.app.services.runtime import store_chunks

        store_chunks(
            [
                {
                    "chunk_id": c.chunk_id,
                    "document_id": paper_id,
                    "page": c.page_start,
                    "section": c.section or "",
                    "text": c.text,
                }
                for c in prepared.paper.chunks
            ]
        )
    except Exception:
        pass

    return await index_prepared_paper(
        prepared,
        vector_indexer=QdrantVectorIndexer(
            client,
            collection_name=settings.qdrant_collection,
            vector_dimension=settings.embedding_dimension,
        ),
        bm25_indexer=BM25Indexer(Path(settings.bm25_index_path)),
    )


