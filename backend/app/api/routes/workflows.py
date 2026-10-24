from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import Owner, ServicesDep, Store
from backend.app.services.runtime import RuntimeStore

router = APIRouter(prefix="/api/v1", tags=["workflows"])

SearchSource = Literal["semantic_scholar", "arxiv", "tavily"]


class QueryBody(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1, max_length=20)


class CheckBody(BaseModel):
    claim: str = Field(min_length=3, max_length=4000)
    max_papers: int = Field(default=6, ge=1, le=10)
    sources: list[SearchSource] = Field(
        default_factory=lambda: ["semantic_scholar", "arxiv", "tavily"]
    )


class CompareBody(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=10)
    attributes: list[str] = Field(default_factory=list, max_length=10)


class ContradictionBody(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=10)
    topic: str | None = Field(default=None, max_length=200)


def _ready(
    store: RuntimeStore, ids: list[str], owner: str | None, *, minimum: int = 1
) -> list[str]:
    """The caller's documents, in request order, all ready to query."""
    unique = list(dict.fromkeys(i.strip() for i in ids if i.strip()))
    if len(unique) < minimum:
        raise HTTPException(400, f"Select at least {minimum} different papers.")
    for document_id in unique:
        document = store.get_document(document_id, owner)
        if not document:
            raise HTTPException(404, f"No document with id {document_id}.")
        if document["status"] != "ready":
            raise HTTPException(409, f"“{document['title']}” is not ready yet.")
    return unique


@router.post("/query", status_code=202)
async def start_query(
    body: QueryBody, store: Store, owner: Owner, services: ServicesDep
) -> dict[str, str]:
    ids = _ready(store, body.document_ids, owner)
    job_id = services.jobs.start(
        "query", owner, lambda emit: services.queries.query(body.question, ids, emit)
    )
    return {"job_id": job_id}


@router.post("/compare", status_code=202)
async def start_compare(
    body: CompareBody, store: Store, owner: Owner, services: ServicesDep
) -> dict[str, str]:
    ids = _ready(store, body.document_ids, owner, minimum=2)
    attributes = [a.strip()[:60] for a in body.attributes if a.strip()]
    job_id = services.jobs.start(
        "compare", owner, lambda emit: services.queries.compare(ids, attributes, emit)
    )
    return {"job_id": job_id}


@router.post("/contradiction", status_code=202)
async def start_contradiction(
    body: ContradictionBody, store: Store, owner: Owner, services: ServicesDep
) -> dict[str, str]:
    ids = _ready(store, body.document_ids, owner, minimum=2)
    topic = body.topic.strip() if body.topic and body.topic.strip() else None
    job_id = services.jobs.start(
        "contradiction",
        owner,
        lambda emit: services.queries.contradiction(ids, topic, emit),
    )
    return {"job_id": job_id}


@router.post("/check", status_code=202)
async def start_check(
    body: CheckBody, owner: Owner, services: ServicesDep
) -> dict[str, str]:
    sources = list(dict.fromkeys(body.sources))
    if not sources:
        raise HTTPException(400, "Choose at least one source.")
    job_id = services.jobs.start(
        "check",
        owner,
        lambda emit: services.claims.run(
            body.claim.strip(),
            max_papers=body.max_papers,
            sources=sources,
            owner_uid=owner,
            emit=emit,
        ),
        timeout=services.settings.check_timeout_seconds,
    )
    return {"job_id": job_id}
