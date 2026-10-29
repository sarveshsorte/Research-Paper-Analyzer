from query_pipeline.app.schemas.generation import GeneratedClaim
from query_pipeline.app.schemas.retrieval import EvidenceSource
import re


def has_claim_sources(
    claim: GeneratedClaim, evidence: list[EvidenceSource]
) -> bool:
    valid_ids = {source.source_id for source in evidence}
    return bool(claim.source_ids) and set(claim.source_ids).issubset(valid_ids)


def check_claim_support(
    claim: GeneratedClaim, evidence: list[EvidenceSource]
) -> str:
    if not has_claim_sources(claim, evidence):
        return "insufficient"
    cited = " ".join(
        item.candidate.text.lower()
        for item in evidence
        if item.source_id in claim.source_ids
    )
    all_evidence = " ".join(item.candidate.text.lower() for item in evidence)

    claim_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", claim.text))
    evidence_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", cited))
    all_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", all_evidence))

    if claim_numbers and not claim_numbers.issubset(evidence_numbers) and not claim_numbers.issubset(all_numbers):
        return "contradicts"

    claim_terms = {
        term.strip(".,:;!?()[]{}'\"")
        for term in claim.text.lower().split()
        if len(term.strip(".,:;!?()[]{}'\"")) > 2
    }
    if claim_terms and (claim_terms.intersection(set(cited.split())) or claim_terms.intersection(set(all_evidence.split()))):
        return "entails"
    return "insufficient"