from uuid import uuid4
from time import perf_counter

from query_pipeline.app.citations.mapper import map_citations, map_claim
from query_pipeline.app.citations.source_ids import assign_source_ids
from backend.app.config import Settings
from query_pipeline.app.guardrails.evidence_guard import require_evidence
from query_pipeline.app.guardrails.policies import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    NO_READY_PAPERS_MESSAGE,
)
from backend.app.observability.logging import get_logger
from query_pipeline.app.pipeline.evidence_balancing import balance_evidence
from query_pipeline.app.pipeline.deduplication import deduplicate
from query_pipeline.app.pipeline.classification import classify_question
from query_pipeline.app.pipeline.context_compression import compress_context
from query_pipeline.app.pipeline.evidence_selection import select_evidence
from query_pipeline.app.pipeline.filters import matches_filters
from query_pipeline.app.pipeline.rewriting import rewrite_query
from query_pipeline.app.pipeline.thresholds import above_relevance_threshold
from query_pipeline.app.pipeline.validation import validate_query
from query_pipeline.app.providers.embedding_provider import EmbeddingProvider
from query_pipeline.app.providers.nemotron_provider import GenerationProvider
from query_pipeline.app.providers.qdrant_provider import DenseRetriever
from query_pipeline.app.providers.bm25_provider import SparseRetriever
from query_pipeline.app.providers.reranker_provider import RerankerProvider
from database.repositories.chunk_repository import ChunkRepository
from database.repositories.paper_repository import PaperRepository
from query_pipeline.app.schemas.query import QueryRequest, QueryResponse


logger = get_logger(__name__)


class QueryOrchestrator:
    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        dense_retriever: DenseRetriever,
        generator: GenerationProvider,
        paper_repository: PaperRepository,
        chunk_repository: ChunkRepository,
        sparse_retriever: SparseRetriever | None = None,
        reranker: RerankerProvider | None = None,
        answer_repository: object | None = None,
        workspace_repository: object | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.dense_retriever = dense_retriever
        self.generator = generator
        self.paper_repository = paper_repository
        self.chunk_repository = chunk_repository
        self.sparse_retriever = sparse_retriever
        self.reranker = reranker
        self.answer_repository = answer_repository
        self.workspace_repository = workspace_repository

    async def run(
        self,
        workspace_id: str,
        request: QueryRequest,
        user_id: str | None = None,
    ) -> QueryResponse:
        query_id = str(uuid4())
        started = perf_counter()
        if len(request.question) > self.settings.max_question_length:
            raise ValueError("Question exceeds the configured maximum length")
        if len(request.paper_ids) > self.settings.max_papers_per_query:
            raise ValueError("Too many papers selected")
        if user_id is not None and self.workspace_repository is not None:
            if not await self.workspace_repository.user_has_access(
                user_id, workspace_id
            ):
                raise PermissionError("User does not have access to this workspace")
        validation = await validate_query(
            request,
            workspace_id,
            self.paper_repository,
            self.chunk_repository,
        )
        if validation.status == "paper_not_ready":
            return QueryResponse(
                query_id=query_id,
                answer="One or more selected papers are not ready for querying.",
                pipeline_status="paper_not_ready",
                uncertainties=sorted(validation.unavailable_paper_ids),
            )
        if validation.status == "no_ready_papers":
            return QueryResponse(
                query_id=query_id,
                answer=NO_READY_PAPERS_MESSAGE,
                pipeline_status="no_ready_papers",
                uncertainties=["No selected paper is ready with indexed chunks."],
            )

        query_type = classify_question(request.question, len(validation.ready_paper_ids))
        rewritten_query = rewrite_query(request.question)
        embedding = await self.embedding_provider.embed(rewritten_query)
        candidates = await self.dense_retriever.search(
            embedding=embedding,
            workspace_id=workspace_id,
            paper_ids=list(validation.ready_paper_ids),
            filters=request.filters,
            limit=self.settings.top_k_dense,
        )
        if self.sparse_retriever is not None:
            sparse = await self.sparse_retriever.search(
                rewritten_query,
                workspace_id,
                list(validation.ready_paper_ids),
                request.filters,
                self.settings.top_k_sparse,
            )
            from query_pipeline.app.pipeline.fusion import reciprocal_rank_fusion

            candidates = reciprocal_rank_fusion([candidates, sparse])
        if self.reranker is not None and candidates:
            candidates = await self.reranker.rerank(
                request.question, candidates, self.settings.top_k_reranked
            )
        candidates = [
            candidate
            for candidate in candidates
            if matches_filters(candidate, request.filters)
        ]
        candidates = deduplicate(candidates)
        candidates = above_relevance_threshold(
            candidates, self.settings.min_relevance_score
        )
        if not candidates:
            return QueryResponse(
                query_id=query_id,
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                pipeline_status="insufficient_evidence",
                uncertainties=["No retrieved evidence passed the relevance threshold."],
            )

        candidates = balance_evidence(
            candidates,
            list(validation.ready_paper_ids),
            max(1, self.settings.top_k_reranked // max(1, len(validation.ready_paper_ids))),
        )
        evidence = select_evidence(candidates, self.settings.top_k_reranked)
        evidence = compress_context(evidence, self.settings.max_context_tokens)
        evidence = assign_source_ids([item.candidate for item in evidence])
        require_evidence(evidence)
        try:
            generated = await self.generator.generate(rewritten_query, evidence)
        except (TimeoutError, ConnectionError, ValueError) as exc:
            logger.warning("generation_failed query_id=%s error=%s", query_id, type(exc).__name__)
            return QueryResponse(
                query_id=query_id,
                answer="The answer could not be generated or validated.",
                pipeline_status="generation_failed",
                uncertainties=["The generation provider returned an invalid response."],
            )
        claims = [map_claim(claim, evidence) for claim in generated.claims]
        valid_claims = [c for c in claims if c.validation_status == "valid"]
        if not valid_claims and claims:
            return QueryResponse(
                query_id=query_id,
                answer="The generated answer could not be fully validated.",
                claims=claims,
                citations=[],
                pipeline_status="generation_failed",
                uncertainties=["One or more generated claims lacked sufficient evidence."],
            )
        citations = map_citations(evidence)
        response = QueryResponse(
            query_id=query_id,
            answer=generated.answer,
            claims=claims,
            citations=citations,
            uncertainties=generated.uncertainties,
            pipeline_status="completed",
        )
        logger.info(
            "query_complete query_id=%s query_type=%s status=%s candidates=%d "
            "evidence=%d latency_ms=%.2f",
            query_id,
            query_type,
            response.pipeline_status,
            len(candidates),
            len(evidence),
            (perf_counter() - started) * 1000,
        )
        if self.answer_repository is not None:
            await self.answer_repository.save(response)
        return response