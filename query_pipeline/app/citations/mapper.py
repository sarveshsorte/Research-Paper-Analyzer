from query_pipeline.app.schemas.citation import ClaimResponse, citation_from_candidate
from query_pipeline.app.schemas.generation import GeneratedClaim
from query_pipeline.app.schemas.retrieval import EvidenceSource
from query_pipeline.app.citations.validator import validate_claim
from query_pipeline.app.citations.support_checker import check_claim_support


def map_claim(
    claim: GeneratedClaim, evidence: list[EvidenceSource]
) -> ClaimResponse:
    source_map = {item.source_id: item for item in evidence}
    status = validate_claim(claim, evidence)
    support_status = check_claim_support(claim, evidence)
    if status == "valid" and support_status != "entails":
        # Check if another evidence source actually supports this claim
        for src in evidence:
            alt_claim = GeneratedClaim(text=claim.text, source_ids=[src.source_id])
            if check_claim_support(alt_claim, evidence) == "entails":
                claim.source_ids = [src.source_id]
                status = "valid"
                support_status = "entails"
                break
        else:
            status = "unsupported"

    if status != "valid":
        return ClaimResponse(
            text=claim.text,
            source_ids=claim.source_ids,
            citation_text="",
            validation_status=status,
        )
    citations = [source_map[source_id] for source_id in claim.source_ids if source_id in source_map]
    if not citations and evidence:
        citations = [evidence[0]]
        claim.source_ids = [evidence[0].source_id]
    labels = ", ".join(
        f"{item.candidate.paper_title}, p. {item.candidate.page_start}"
        for item in citations
    )
    return ClaimResponse(
        text=claim.text,
        source_ids=claim.source_ids,
        citation_text=f"[{labels}]",
        validation_status="valid",
    )


def map_citations(evidence: list[EvidenceSource]):
    return [
        citation_from_candidate(source.source_id, source.candidate, "valid")
        for source in evidence
    ]