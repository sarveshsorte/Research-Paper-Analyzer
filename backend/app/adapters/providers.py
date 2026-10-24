"""Model clients and retrieval providers that plug into the teammates' protocols.

- Embeddings: an OpenAI-compatible `/embeddings` API (NVIDIA API Catalog or
  Nebius Token Factory), or a local hashing embedder when no key is set.
- Generation: Nemotron through Nebius Token Factory's OpenAI-compatible
  `/chat/completions`.
- Dense retrieval: vectors stored in the backend's SQLite database.
- Sparse retrieval: the document pipeline's SQLite FTS5/BM25 index.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from collections.abc import Sequence
from typing import Any

import httpx
import numpy as np

from backend.app.services.runtime import RuntimeStore, StoredChunk
from backend.app.services.text import content_terms
from document_pipeline.embeddings import EmbeddedChunk
from document_pipeline.indexing import BM25Indexer
from query_pipeline.app.schemas.retrieval import RetrievalCandidate, RetrievalFilters

logger = logging.getLogger(__name__)

# The query pipeline filters every search by one workspace. Ownership is checked
# by the backend before any document id reaches the pipeline.
WORKSPACE_ID = "claimlens"

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class UpstreamError(RuntimeError):
    """A model or search API failed; the message is safe to show to users."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    service: str,
    timeout: float,
    attempts: int = 3,
) -> dict[str, Any]:
    """POSTs JSON with retries on rate limits and server errors."""
    for attempt in range(attempts):
        try:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            if attempt + 1 == attempts:
                raise UpstreamError(f"{service} could not be reached.") from exc
        else:
            if response.status_code < 400:
                return response.json()
            if response.status_code not in RETRYABLE_STATUS or attempt + 1 == attempts:
                logger.warning(
                    "%s_error status=%s body=%s",
                    service.lower().replace(" ", "_"),
                    response.status_code,
                    response.text[:300],
                )
                raise UpstreamError(
                    f"{service} returned an error ({response.status_code}).",
                    status=response.status_code,
                )
        await asyncio.sleep(0.5 * 4**attempt)
    raise UpstreamError(f"{service} could not be reached.")


# Embeddings


class HashingEmbedder:
    """Local, key-free embeddings: hashed word and word-pair counts.

    Only a fallback so the app works without an embedding API; similarity is
    lexical, not semantic.
    """

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension
        self.model_id = f"local-hashing-{dimension}"
        self.label = "local hashing embeddings"

    def embed_sync(self, text: str) -> list[float]:
        terms = content_terms(text)
        features = terms + [f"{a} {b}" for a, b in zip(terms, terms[1:], strict=False)]
        vector = np.zeros(self.dimension, dtype=np.float32)
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        vector = np.sign(vector) * np.log1p(np.abs(vector))
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return (vector / norm).tolist()

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        return self.embed_sync(text)


class RemoteEmbedder:
    """OpenAI-compatible `/embeddings` (one text per call, as the pipeline expects)."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        input_type: str | None,
    ) -> None:
        self.client = client
        self.url = base_url.rstrip("/") + "/embeddings"
        self.api_key = api_key
        self.model_id = model
        self.dimension = dimension
        self.input_type = input_type
        self.label = model

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": [text],
            "encoding_format": "float",
        }
        if self.input_type:
            payload["input_type"] = self.input_type
            payload["truncate"] = "END"
        body = await _post_json(
            self.client,
            self.url,
            payload,
            api_key=self.api_key,
            service="The embedding service",
            timeout=30,
        )
        try:
            return [float(value) for value in body["data"][0]["embedding"]]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise UpstreamError(
                "The embedding service sent an unexpected reply."
            ) from exc


# Generation (Nemotron on Nebius Token Factory)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_json_object(raw: str) -> dict[str, Any]:
    """The JSON object in a model reply (reasoning tags and code fences removed)."""
    text = _THINK.sub("", raw).strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The model reply contains no JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("The model reply is not a JSON object")
    return value


class ChatModel:
    """Nebius Token Factory chat completions, returning parsed JSON objects."""

    def __init__(
        self, client: httpx.AsyncClient, *, base_url: str, api_key: str, model: str
    ) -> None:
        self.client = client
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model_id = model
        self.label = model.split("/")[-1]
        self._json_mode = True

    async def complete_json(
        self, system: str, user: str, *, max_tokens: int = 1500
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            body = await _post_json(
                self.client,
                self.url,
                payload,
                api_key=self.api_key,
                service="Nemotron (Nebius Token Factory)",
                timeout=90,
            )
        except UpstreamError as exc:
            if not self._json_mode or exc.status not in (400, 422):
                raise
            # Some models reject response_format; retry once without it.
            self._json_mode = False
            payload.pop("response_format")
            body = await _post_json(
                self.client,
                self.url,
                payload,
                api_key=self.api_key,
                service="Nemotron (Nebius Token Factory)",
                timeout=90,
            )
        try:
            content = body["choices"][0]["message"]["content"] or ""
            return parse_json_object(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise UpstreamError(
                "Nemotron returned a reply that is not valid JSON."
            ) from exc


# Dense retrieval over vectors stored in SQLite


def _to_blob(vector: Sequence[float]) -> tuple[int, bytes]:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Cannot store a zero or non-finite vector")
    return array.size, (array / norm).tobytes()


class SQLiteVectorIndexer:
    """Stands in for QdrantVectorIndexer in `index_prepared_paper`."""

    def __init__(self, store: RuntimeStore, model_id: str) -> None:
        self.store = store
        self.model_id = model_id

    async def upsert_chunks(self, chunks: Sequence[EmbeddedChunk]) -> int:
        items = []
        for item in chunks:
            dimension, blob = _to_blob(item.vector)
            items.append((item.chunk.chunk_id, item.chunk.paper_id, dimension, blob))
        return await asyncio.to_thread(self.store.save_vectors, self.model_id, items)


def _candidate(chunk: StoredChunk, **scores: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk.chunk_id,
        workspace_id=WORKSPACE_ID,
        paper_id=chunk.document_id,
        paper_title=chunk.title,
        text=chunk.text,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section=chunk.section,
        content_hash=chunk.content_hash,
        **scores,
    )


def _in_filters(chunk: StoredChunk, filters: RetrievalFilters) -> bool:
    if filters.sections and chunk.section not in filters.sections:
        return False
    if filters.page_start and chunk.page_end < filters.page_start:
        return False
    return not (filters.page_end and chunk.page_start > filters.page_end)


class SQLiteDenseRetriever:
    """The query pipeline's DenseRetriever, using cosine similarity in numpy.

    Searches only the selected papers, so a brute-force scan is fast.
    """

    def __init__(self, store: RuntimeStore, model_id: str) -> None:
        self.store = store
        self.model_id = model_id

    async def search(
        self,
        embedding: list[float],
        workspace_id: str,
        paper_ids: list[str],
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievalCandidate]:
        del workspace_id  # one workspace; ownership is enforced by the backend
        rows = await asyncio.to_thread(self.store.vectors, paper_ids, self.model_id)
        rows = [(chunk, blob) for chunk, blob in rows if _in_filters(chunk, filters)]
        if not rows:
            return []
        query = np.asarray(embedding, dtype=np.float32)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        matrix = np.vstack([np.frombuffer(blob, dtype=np.float32) for _, blob in rows])
        if matrix.shape[1] != query.size:
            raise UpstreamError(
                "The stored vectors were made with a different embedding size. "
                "Re-process the papers."
            )
        scores = matrix @ query
        order = np.argsort(-scores)[:limit]
        return [_candidate(rows[i][0], dense_score=float(scores[i])) for i in order]


class BM25SparseRetriever:
    """The query pipeline's SparseRetriever over the document pipeline's BM25 index."""

    def __init__(self, indexer: BM25Indexer, store: RuntimeStore) -> None:
        self.indexer = indexer
        self.store = store

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
        # Titles and text come from the backend database, the source of truth.
        stored = await asyncio.to_thread(
            self.store.chunks_by_id, [hit.chunk.chunk_id for hit in hits]
        )
        return [
            _candidate(stored[hit.chunk.chunk_id], sparse_score=-hit.score)
            for hit in hits
            if hit.chunk.chunk_id in stored
        ]


class TermReranker:
    """The query pipeline's RerankerProvider.

    Score = shared content words (stopwords ignored) + 2 × dense similarity, so
    the pipeline's MIN_RELEVANCE_SCORE (0.65) keeps passages that share at least
    one meaningful word with the question or are semantically close to it.
    """

    async def rerank(
        self, query: str, candidates: list[RetrievalCandidate], limit: int
    ) -> list[RetrievalCandidate]:
        terms = set(content_terms(query))
        scored = []
        for order, candidate in enumerate(candidates):
            shared = len(terms & set(content_terms(candidate.text)))
            score = shared + 2 * max(candidate.dense_score or 0.0, 0.0)
            scored.append(
                (score, -order, candidate.model_copy(update={"rerank_score": score}))
            )
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [candidate for _, _, candidate in scored[:limit]]


# Repositories the query pipeline's validation step reads


class StorePaperRepository:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    async def ready_papers(self, workspace_id: str, paper_ids: list[str]) -> set[str]:
        del workspace_id
        return await asyncio.to_thread(self.store.ready_documents, paper_ids)


class StoreChunkRepository:
    """A paper is indexed when it has vectors from the current embedding model."""

    def __init__(self, store: RuntimeStore, model_id: str) -> None:
        self.store = store
        self.model_id = model_id

    async def indexed_papers(self, workspace_id: str, paper_ids: list[str]) -> set[str]:
        del workspace_id
        return await asyncio.to_thread(
            self.store.documents_with_vectors, paper_ids, self.model_id
        )

    async def has_chunks(self, workspace_id: str, paper_ids: list[str]) -> bool:
        return bool(await self.indexed_papers(workspace_id, paper_ids))
