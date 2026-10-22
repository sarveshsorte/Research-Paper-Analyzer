import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import Owner, Store
from backend.app.services.runtime import RuntimeStore, run_in_background

router = APIRouter(prefix="/api/v1", tags=["workflows"])
logger = logging.getLogger(__name__)
QUERY_FAILED = {
    "code": "INTERNAL_ERROR",
    "message": "The question could not be answered.",
}


class QueryBody(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1, max_length=20)


class CheckBody(BaseModel):
    claim: str = Field(min_length=3, max_length=4000)
    max_papers: int = Field(default=10, ge=1, le=20)
    sources: list[str] = Field(default_factory=list)


class CompareBody(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=20)
    attributes: list[str] = Field(default_factory=list)


class ContradictionBody(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=20)
    topic: str | None = None


def _ready(
    store: RuntimeStore, ids: list[str], owner: str | None
) -> list[dict[str, Any]]:
    documents = []
    for document_id in ids:
        document = store.get_document(document_id, owner)
        if not document:
            raise HTTPException(404, f"No document with id {document_id}.")
        if document["status"] != "ready":
            raise HTTPException(409, f"{document['title']} is not ready yet.")
        documents.append(document)
    return documents


def _evidence(
    store: RuntimeStore, question: str, document_ids: list[str]
) -> list[dict[str, Any]]:
    return store.search(question, document_ids)


def _query_result(
    store: RuntimeStore, question: str, document_ids: list[str]
) -> dict[str, Any]:
    hits = _evidence(store, question, document_ids)
    if not hits:
        return {
            "answer": "The selected papers do not contain enough matching evidence.",
            "claims": [],
            "highlights": [],
        }
    claims = [
        {
            "claim": hit["quote"],
            "status": "SUPPORTED",
            "confidence": 0.75,
            "evidence": [{
                "chunk_id": hit["chunk_id"],
                "document_id": hit["document_id"],
                "page": hit["page"],
                "section": hit["section"],
                "quote": hit["quote"],
                "highlight": hit["quote"],
            }],
        }
        for hit in hits[:4]
    ]
    return {
        "answer": "Relevant evidence found in the selected papers:\n\n"
        + "\n\n".join(f"- {hit['quote']}" for hit in hits[:3]),
        "claims": claims,
        "highlights": [hit["quote"] for hit in hits[:3]],
    }


async def _finish_query(
    store: RuntimeStore, job_id: str, question: str, document_ids: list[str]
) -> None:
    await asyncio.sleep(0)
    try:
        store.finish_job(job_id, _query_result(store, question, document_ids))
    except Exception:
        logger.exception("Query job %s failed", job_id)
        store.fail_job(job_id, QUERY_FAILED)


def _finished_job(
    store: RuntimeStore, kind: str, owner: str | None, result: Any
) -> str:
    job = store.create_job(kind, owner)
    store.finish_job(job.job_id, result)
    return job.job_id


@router.post("/query", status_code=202)
async def start_query(body: QueryBody, store: Store, owner: Owner) -> dict[str, str]:
    _ready(store, body.document_ids, owner)
    job = store.create_job("query", owner)
    run_in_background(
        _finish_query(store, job.job_id, body.question, body.document_ids)
    )
    return {"job_id": job.job_id}


@router.post("/check", status_code=202)
async def start_check(body: CheckBody, store: Store, owner: Owner) -> dict[str, str]:
    documents = store.list_documents(owner)
    ready = [doc for doc in documents if doc["status"] == "ready"][: body.max_papers]
    ids = [doc["document_id"] for doc in ready]
    hits = _evidence(store, body.claim, ids) if ids else []
    evidence = [
        {
            "chunk_id": hit["chunk_id"],
            "document_id": hit["document_id"],
            "page": hit["page"],
            "section": hit["section"],
            "quote": hit["quote"],
        }
        for hit in hits
    ]
    result = {
        "claim": body.claim,
        "papers": ready,
        "supports": evidence,
        "contradicts": [],
        "partial": [],
        "insufficient": [] if evidence else [{"quote": "No matching evidence found."}],
        "summary": "Evidence was retrieved from the uploaded papers.",
        "verified_quotes": len(evidence),
        "total_quotes": len(evidence),
    }
    return {"job_id": _finished_job(store, "check", owner, result)}


@router.post("/compare", status_code=202)
async def start_compare(
    body: CompareBody, store: Store, owner: Owner
) -> dict[str, str]:
    documents = _ready(store, body.document_ids, owner)
    result = [
        {
            "attribute": attribute,
            "values": {
                doc["document_id"]: {
                    "value": "Compare this attribute against the paper evidence.",
                    "chunk_id": "",
                }
                for doc in documents
            },
        }
        for attribute in (body.attributes or ["Title", "Pages", "Indexed chunks"])
    ]
    for row in result:
        if row["attribute"] == "Title":
            for doc in documents:
                row["values"][doc["document_id"]]["value"] = doc["title"]
        elif row["attribute"] == "Pages":
            for doc in documents:
                row["values"][doc["document_id"]]["value"] = str(doc["pages"])
        elif row["attribute"] == "Indexed chunks":
            for doc in documents:
                row["values"][doc["document_id"]]["value"] = str(doc["chunks"] or 0)
    return {"job_id": _finished_job(store, "compare", owner, result)}


@router.post("/contradiction", status_code=202)
async def start_contradiction(
    body: ContradictionBody, store: Store, owner: Owner
) -> dict[str, str]:
    _ready(store, body.document_ids, owner)
    return {"job_id": _finished_job(store, "contradiction", owner, [])}
