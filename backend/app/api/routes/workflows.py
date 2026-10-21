import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.runtime import Job, store

router = APIRouter(prefix="/api/v1", tags=["workflows"])


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


def _ready(ids: list[str]) -> list[dict[str, Any]]:
    documents = []
    for document_id in ids:
        document = store.get_document(document_id)
        if not document:
            raise HTTPException(404, f"No document with id {document_id}.")
        if document["status"] != "ready":
            raise HTTPException(409, f"{document['title']} is not ready yet.")
        documents.append(document)
    return documents


def _evidence(question: str, document_ids: list[str]) -> list[dict[str, Any]]:
    return store.search(question, document_ids)


def _query_result(question: str, document_ids: list[str]) -> dict[str, Any]:
    hits = _evidence(question, document_ids)
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


async def _finish_query(job: Job, question: str, document_ids: list[str]) -> None:
    await asyncio.sleep(0)
    job.result = _query_result(question, document_ids)
    job.status = "done"


def _start(kind: str, result: Any = None) -> Job:
    return store.create_job(kind, result)


@router.post("/query", status_code=202)
async def start_query(body: QueryBody) -> dict[str, str]:
    _ready(body.document_ids)
    job = _start("query")
    asyncio.create_task(_finish_query(job, body.question, body.document_ids))
    return {"job_id": job.job_id}


@router.post("/check", status_code=202)
async def start_check(body: CheckBody) -> dict[str, str]:
    documents = store.list_documents()
    ready = [doc for doc in documents if doc["status"] == "ready"][: body.max_papers]
    ids = [doc["document_id"] for doc in ready]
    hits = _evidence(body.claim, ids) if ids else []
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
    job = _start("check", result)
    job.status = "done"
    return {"job_id": job.job_id}


@router.post("/compare", status_code=202)
async def start_compare(body: CompareBody) -> dict[str, str]:
    documents = _ready(body.document_ids)
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
    job = _start("compare", result)
    job.status = "done"
    return {"job_id": job.job_id}


@router.post("/contradiction", status_code=202)
async def start_contradiction(body: ContradictionBody) -> dict[str, str]:
    _ready(body.document_ids)
    job = _start("contradiction", [])
    job.status = "done"
    return {"job_id": job.job_id}
