"""Reranker providers.

- ``NvidiaNemotronReranker``  — Real cross-encoder reranker using NVIDIA's
  Nemotron-3.5-Rerank-8B-BF16 model. Called after Reciprocal-Rank Fusion
  (dense + BM25) to score and filter the most relevant chunks before they
  are fed to the LLM.

- ``ScoreBasedReranker`` — Lightweight keyword-overlap fallback kept for
  unit-testing without network access.
"""

from __future__ import annotations

import logging
import math
from typing import Protocol

import httpx

from query_pipeline.app.schemas.retrieval import RetrievalCandidate

logger = logging.getLogger(__name__)


class RerankerProvider(Protocol):
    async def rerank(
        self, query: str, candidates: list[RetrievalCandidate], limit: int
    ) -> list[RetrievalCandidate]:
        ...


def _logit_to_relevance_score(logit: float) -> float:
    """Map unnormalized reranker logits to a calibrated [0, 1] relevance score.

    Nemotron-3.5-Rerank produces logits typically centered around -2.5.
    - Strong matches (logit > -1.8) map to > 0.80
    - Moderate matches (logit ~ -2.5) map to ~ 0.50
    - Irrelevant noise (logit < -3.5) map to < 0.12
    """
    z = 2.0 * (logit + 2.5)
    z = max(-50.0, min(50.0, z))
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# Real NVIDIA Nemotron reranker
# ---------------------------------------------------------------------------

class NvidiaNemotronReranker:
    """Cross-encoder reranker backed by Nemotron-3.5-Rerank-8B-BF16.

    Supports both:
    1. NVIDIA Hosted API Catalog (https://ai.api.nvidia.com)
       Endpoint: POST /v1/retrieval/{model}/reranking
    2. Self-hosted NVIDIA NIM container
       Endpoint: POST /v1/ranking

    Request format:
        {
          "model": "nvidia/nemotron-3.5-rerank-8b",
          "query": {"text": "<question>"},
          "passages": [{"text": "<chunk_text>"}, ...]
        }

    Response:
        {
          "rankings": [{"index": 0, "logit": -1.38, ...}, ...]
        }
    """

    # Maximum passages evaluated per rerank call (NVIDIA limit is 32-512)
    _MAX_PASSAGES = 32
    # Maximum characters per passage sent to the API
    _MAX_PASSAGE_CHARS = 2000

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.raw_base_url = base_url
        self.api_key = api_key
        self.raw_model = model
        self.endpoint_url, self.resolved_model = self._resolve_endpoint_and_model(
            base_url, model
        )

    @staticmethod
    def _resolve_endpoint_and_model(base_url: str, model: str) -> tuple[str, str]:
        """Normalize model name and construct the correct endpoint URL."""
        clean_model = model.strip()
        # Strip common trailing precision tags if present
        if clean_model.lower().endswith("-bf16"):
            clean_model = clean_model[:-5]
        if not clean_model.startswith("nvidia/"):
            clean_model = f"nvidia/{clean_model}"

        b = base_url.rstrip("/")
        # If user passed full path already
        if "/reranking" in b or "/ranking" in b:
            return b, clean_model

        # NVIDIA cloud-hosted API
        if "api.nvidia.com" in b:
            return (
                f"https://ai.api.nvidia.com/v1/retrieval/{clean_model}/reranking",
                clean_model,
            )

        # Local or self-hosted NIM
        b = b.removesuffix("/v1")
        return f"{b}/v1/ranking", clean_model

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []

        # Batch to at most _MAX_PASSAGES; the rest keep their fusion score
        batch = candidates[: self._MAX_PASSAGES]
        rest = candidates[self._MAX_PASSAGES :]

        passages = [
            {"text": c.text[: self._MAX_PASSAGE_CHARS]}
            for c in batch
        ]

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    self.endpoint_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "model": self.resolved_model,
                        "query": {"text": query},
                        "passages": passages,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "nvidia_reranker HTTP %s – falling back to fusion order: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return candidates[:limit]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "nvidia_reranker error – falling back to fusion order: %s", exc
            )
            return candidates[:limit]

        # Map index → calibrated relevance score in [0, 1]
        rankings: list[dict] = data.get("rankings", [])
        score_map: dict[int, float] = {
            r["index"]: _logit_to_relevance_score(float(r.get("logit", 0.0)))
            for r in rankings
        }

        # Annotate the batch with calibrated rerank scores
        scored_batch = [
            c.model_copy(update={"rerank_score": score_map.get(i, 0.0)})
            for i, c in enumerate(batch)
        ]

        # Sort batch by rerank score descending
        scored_batch.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)

        top_score = scored_batch[0].rerank_score if scored_batch else 0.0
        logger.info(
            "nvidia_nemotron_reranker scored %d/%d candidates, top score=%.3f",
            len(scored_batch),
            len(candidates),
            top_score,
        )

        return (scored_batch + rest)[:limit]


# ---------------------------------------------------------------------------
# Keyword-overlap fallback (no network)
# ---------------------------------------------------------------------------

class ScoreBasedReranker:
    """Simple keyword-overlap ranker — used in tests and dev without a reranker key."""

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        limit: int,
    ) -> list[RetrievalCandidate]:
        terms = set(query.lower().split())
        ranked = [
            c.model_copy(
                update={
                    "rerank_score": float(
                        sum(term in c.text.lower() for term in terms)
                    )
                }
            )
            for c in candidates
        ]
        return sorted(ranked, key=lambda c: c.rerank_score or 0, reverse=True)[:limit]
