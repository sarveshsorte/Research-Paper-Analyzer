"""DocumentPipelineAdapter: one PDF through the teammates' Document Pipeline.

ingest_pdf (extract, sections, chunks) → embed_chunks (our embedder) →
index_prepared_paper (vectors into SQLite, text into their BM25 index).
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from backend.app.adapters.providers import (
    WORKSPACE_ID,
    SQLiteVectorIndexer,
    UpstreamError,
)
from backend.app.services.runtime import ChunkToSave, FileRecord, RuntimeStore
from document_pipeline.embeddings import EmbeddingError, embed_chunks
from document_pipeline.indexing import BM25Indexer
from document_pipeline.ingestion import (
    EncryptedPDFError,
    IngestedPaper,
    NoExtractableTextError,
    OCRProcessingError,
    PDFLoadError,
    ingest_pdf,
)
from document_pipeline.pipeline import PreparedPaper, index_prepared_paper

logger = logging.getLogger(__name__)

_YEAR = re.compile(r"(19|20)\d{2}")
_BAD_TITLE = re.compile(
    r"\.(docx?|tex|pdf|dvi)$|^untitled|microsoft word|^arxiv:|^doi:|^\d+$", re.I
)


def _good_title(value: str | None) -> bool:
    return bool(
        value
        and 8 <= len(value) <= 250
        and re.search(r"[A-Za-z]{3}", value)
        and not _BAD_TITLE.search(value.strip())
    )


def failure_message(exc: BaseException, *, ocr_available: bool) -> str:
    """A short, human message for a failed document."""
    if isinstance(exc, EncryptedPDFError):
        return "The PDF is password-protected."
    if isinstance(exc, NoExtractableTextError):
        if ocr_available:
            return "No text could be extracted from this PDF."
        return "No text could be extracted. The PDF may be scanned and need OCR."
    if isinstance(exc, OCRProcessingError):
        return "This PDF needs OCR, which is not installed on the server."
    if isinstance(exc, PDFLoadError):
        return "The file is not a readable PDF."
    if isinstance(exc, UpstreamError):
        return str(exc)
    if isinstance(exc, EmbeddingError):
        return "The embedding service returned unusable vectors."
    return "Processing failed. Try again."


class _CountingEmbedder:
    """Reports progress as the pipeline embeds each chunk."""

    def __init__(self, embedder, total: int, on_count) -> None:
        self.embedder = embedder
        self.total = max(total, 1)
        self.done = 0
        self.on_count = on_count

    async def embed(self, text: str) -> list[float]:
        vector = await self.embedder.embed(text)
        self.done += 1
        self.on_count(self.done, self.total)
        return vector


class DocumentPipelineAdapter:
    def __init__(
        self,
        store: RuntimeStore,
        embedder,
        bm25: BM25Indexer,
        *,
        concurrency: int = 2,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.bm25 = bm25
        self.ocr_available = shutil.which("tesseract") is not None
        self._semaphore = asyncio.Semaphore(concurrency)

    @property
    def model_id(self) -> str:
        return self.embedder.model_id

    async def process(self, document_id: str) -> bool:
        """Runs the pipeline; the document ends `ready` or `failed`. True if ready."""
        async with self._semaphore:
            try:
                await self._process(document_id)
                return True
            except Exception as exc:
                message = failure_message(exc, ocr_available=self.ocr_available)
                if message == "Processing failed. Try again.":
                    logger.exception("document_failed document_id=%s", document_id)
                else:
                    logger.warning(
                        "document_failed document_id=%s reason=%s",
                        document_id,
                        type(exc).__name__,
                    )
                self.store.mark_failed(document_id, message)
                return False

    async def _process(self, document_id: str) -> None:
        record = self.store.file_for_processing(document_id)
        if record is None:
            return  # deleted before processing started
        if not record.content:
            raise PDFLoadError("The PDF file is missing.")
        self.store.update_document(
            document_id, status="processing", progress=5, error=None
        )

        paper = await asyncio.to_thread(
            ingest_pdf,
            record.content,
            workspace_id=WORKSPACE_ID,
            paper_id=document_id,
            ocr_fallback=self.ocr_available,
        )
        self.store.save_chunks(
            document_id,
            (
                ChunkToSave(
                    chunk_id=chunk.chunk_id,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section=chunk.section,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                )
                for chunk in paper.chunks
            ),
        )
        self.store.update_document(document_id, progress=25)

        last_reported = [25]

        def report(done: int, total: int) -> None:
            progress = 25 + int(65 * done / total)
            if progress - last_reported[0] >= 5:
                last_reported[0] = progress
                self.store.update_document(document_id, progress=progress)

        embedded = await embed_chunks(
            paper.chunks,
            _CountingEmbedder(self.embedder, len(paper.chunks), report),
            expected_dimension=self.embedder.dimension,
            max_concurrency=4,
        )
        await self.delete_index(document_id)  # a retry may chunk differently
        await index_prepared_paper(
            PreparedPaper(paper=paper, embedded_chunks=embedded),
            vector_indexer=SQLiteVectorIndexer(self.store, self.model_id),
            bm25_indexer=self.bm25,
        )
        self.store.fill_metadata(
            document_id, authors=self._authors(paper), year=self._year(paper)
        )
        self.store.mark_ready(
            document_id,
            title=self._title(paper, record),
            pages=len(paper.pages),
            chunks=len(paper.chunks),
        )
        if self.store.file_for_processing(document_id) is None:
            await self.delete_index(document_id)  # deleted while processing

    @staticmethod
    def _title(paper: IngestedPaper, record: FileRecord) -> str:
        # Uploads take the PDF's own title when it looks like one; papers found
        # by search or link already carry the title from their source.
        if record.source == "upload" and _good_title(paper.metadata.title):
            return str(paper.metadata.title).strip()
        return record.title

    @staticmethod
    def _authors(paper: IngestedPaper) -> str | None:
        author = paper.metadata.author
        return author.strip() if author and 2 < len(author.strip()) <= 200 else None

    @staticmethod
    def _year(paper: IngestedPaper) -> int | None:
        match = _YEAR.search(paper.metadata.created_at or "")
        return int(match.group(0)) if match else None

    async def delete_index(self, document_id: str) -> None:
        """Removes the paper from the BM25 index (vectors go with the document row).

        The document pipeline has no delete function, so this deletes the rows
        from its FTS table directly.
        """
        path = Path(self.bm25.database_path)
        if not path.exists():
            return

        def delete() -> None:
            with closing(sqlite3.connect(path, timeout=30)) as connection, connection:
                try:
                    connection.execute(
                        "DELETE FROM chunks_fts "
                        "WHERE workspace_id = ? AND paper_id = ?",
                        (WORKSPACE_ID, document_id),
                    )
                except sqlite3.OperationalError:
                    pass  # the index has not been created yet

        await asyncio.to_thread(delete)
