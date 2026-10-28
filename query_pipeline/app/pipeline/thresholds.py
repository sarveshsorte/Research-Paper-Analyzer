from query_pipeline.app.schemas.retrieval import RetrievalCandidate


def above_relevance_threshold(
    candidates: list[RetrievalCandidate], threshold: float
) -> list[RetrievalCandidate]:
    if not candidates:
        return []

    if threshold <= 0.0:
        return candidates

    def is_candidate_relevant(item: RetrievalCandidate) -> bool:
        if item.rerank_score is not None:
            return item.rerank_score >= threshold
        if item.dense_score is not None:
            return item.dense_score >= min(threshold, 0.35)
        if item.sparse_score is not None:
            return True
        if item.fusion_score is not None:
            return True
        return False

    filtered = [item for item in candidates if is_candidate_relevant(item)]
    return filtered if filtered else candidates[:5]
