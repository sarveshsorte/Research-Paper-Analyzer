"""Claim mode (/check): search → download open-access PDFs → index → judge."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from backend.app.adapters.document_pipeline import DocumentPipelineAdapter
from backend.app.adapters.query_pipeline import QueryPipelineAdapter
from backend.app.services.jobs import StepEmitter
from backend.app.services.runtime import RuntimeStore
from backend.app.services.search import (
    DownloadError,
    PaperHit,
    PdfDownloader,
    SearchError,
    SearchService,
)
from backend.app.services.search.service import SOURCE_NAMES

logger = logging.getLogger(__name__)

SEARCH_VIA = {
    "semantic_scholar": "graph/v1/paper/search",
    "arxiv": "export.arxiv.org",
    "tavily": "tavily /search",
}
DOWNLOAD_CONCURRENCY = 3


class ClaimChecker:
    def __init__(
        self,
        store: RuntimeStore,
        search: SearchService,
        downloader: PdfDownloader,
        documents: DocumentPipelineAdapter,
        queries: QueryPipelineAdapter,
    ) -> None:
        self.store = store
        self.search = search
        self.downloader = downloader
        self.documents = documents
        self.queries = queries

    async def run(
        self,
        claim: str,
        *,
        max_papers: int,
        sources: Sequence[str],
        owner_uid: str | None,
        emit: StepEmitter,
    ) -> dict[str, Any]:
        queries = await self.queries.search_queries(claim)
        emit(
            "searching",
            f"Rewrote the claim into {len(queries)} search "
            f"quer{'ies' if len(queries) != 1 else 'y'}",
            self.queries.chat.label if self.queries.chat else "keyword extraction",
        )
        hits, counts = await self._search(queries, sources, max_papers, emit)
        candidates = self.search.merge(hits)

        document_ids, chunks = await self._acquire(
            candidates, max_papers, owner_uid, emit
        )
        if not document_ids:
            document_ids = [
                doc["document_id"]
                for doc in self.store.list_documents(owner_uid, status="ready")
            ][:max_papers]
            emit(
                "processing",
                f"No new open-access PDFs; checking the {len(document_ids)} ready "
                "papers in your library",
                "library",
            )
        if not document_ids:
            return self._empty(claim, counts)

        result = await self.queries.judge_claim(claim, document_ids, emit)
        papers = [
            doc
            for doc_id in document_ids
            if (doc := self.store.get_document(doc_id, owner_uid))
        ]
        return {"claim": claim, "papers": papers, **result, "sources": counts}

    async def _search(
        self,
        queries: list[str],
        sources: Sequence[str],
        max_papers: int,
        emit: StepEmitter,
    ) -> tuple[list[PaperHit], list[dict[str, Any]]]:
        limit = max(max_papers * 2, 6)

        async def one(source: str) -> list[PaperHit]:
            name = SOURCE_NAMES.get(source, source)
            if not self.search.available(source):
                emit(
                    "searching",
                    f"Skipped {name} — no API key configured",
                    SEARCH_VIA.get(source),
                )
                return []
            try:
                found = await self.search.search(source, queries, limit)
            except SearchError as exc:
                emit("searching", f"{name} unavailable — {exc}", SEARCH_VIA.get(source))
                return []
            unique = len({hit.key() for hit in found})
            noun = "preprints" if source == "arxiv" else "results"
            emit(
                "searching",
                f"Searched {name} — {unique} {noun}",
                SEARCH_VIA.get(source),
            )
            return found

        ordered = [s for s in ("semantic_scholar", "arxiv", "tavily") if s in sources]
        results = await asyncio.gather(*(one(source) for source in ordered))
        counts = [
            {"name": SOURCE_NAMES[source], "count": len({h.key() for h in found})}
            for source, found in zip(ordered, results, strict=True)
        ]
        # Interleave sources so each contributes to the first papers tried.
        interleaved: list[PaperHit] = []
        for index in range(max((len(r) for r in results), default=0)):
            interleaved.extend(r[index] for r in results if index < len(r))
        return interleaved, counts

    async def _acquire(
        self,
        candidates: list[PaperHit],
        max_papers: int,
        owner_uid: str | None,
        emit: StepEmitter,
    ) -> tuple[list[str], int]:
        """Downloads and indexes up to `max_papers` papers; reuses ones already held."""
        semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
        ready: list[str] = []
        failures = 0

        async def one(hit: PaperHit) -> str | None:
            nonlocal failures
            async with semaphore:
                existing = self.store.find_document(owner_uid, url=hit.pdf_url)
                if existing and existing["status"] == "ready":
                    return existing["document_id"]
                try:
                    content, sha256 = await self.downloader.download(hit.pdf_url or "")
                except DownloadError as exc:
                    failures += 1
                    logger.info(
                        "claim_download_failed url=%s reason=%s", hit.pdf_url, exc
                    )
                    return None
                same_file = self.store.find_document(owner_uid, sha256=sha256)
                if same_file and same_file["status"] == "ready":
                    return same_file["document_id"]
                document = self.store.create_document(
                    f"{hit.arxiv_id or 'paper'}.pdf",
                    content,
                    owner_uid,
                    "search",
                    title=hit.title,
                    url=hit.pdf_url,
                    authors=hit.authors_text(),
                    year=hit.year,
                    sha256=sha256,
                )
            # Indexing has its own concurrency limit in the document adapter.
            if await self.documents.process(document["document_id"]):
                return document["document_id"]
            return None

        # Try more candidates than needed: some links fail.
        batch = candidates[: max_papers * 2]
        for document_id in await asyncio.gather(*(one(hit) for hit in batch)):
            if document_id and document_id not in ready and len(ready) < max_papers:
                ready.append(document_id)
        if batch:
            emit(
                "processing",
                f"Downloaded {len(ready)} open-access "
                f"PDF{'s' if len(ready) != 1 else ''}"
                + (f" ({failures} links failed)" if failures else ""),
                "deduped by DOI / arXiv id",
            )
        chunks = sum(
            (self.store.get_document(doc_id, owner_uid) or {}).get("chunks") or 0
            for doc_id in ready
        )
        if ready:
            emit(
                "processing",
                f"Parsed and indexed {chunks:,} chunks",
                self.queries.retrieval_label,
            )
        return ready, chunks

    @staticmethod
    def _empty(claim: str, counts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "claim": claim,
            "papers": [],
            "supports": [],
            "contradicts": [],
            "partial": [],
            "insufficient": [],
            "summary": "No papers could be retrieved for this claim. Upload papers to "
            "your library or try again later.",
            "summary_highlight": "No papers could be retrieved",
            "verified_quotes": 0,
            "total_quotes": 0,
            "sources": counts,
        }
