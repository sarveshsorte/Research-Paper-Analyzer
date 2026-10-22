import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.api.deps import Owner, Store
from backend.app.services.runtime import Job, RuntimeStore

router = APIRouter(prefix="/api/v1", tags=["jobs"])
POLL_SECONDS = 0.25


def _job_body(job: Job) -> dict:
    body = {"job_id": job.job_id, "kind": job.kind, "status": job.status}
    if job.status == "done":
        body["result"] = job.result
    if job.status == "error":
        body["error"] = job.error
    return body


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, store: Store, owner: Owner) -> dict:
    job = store.get_job(job_id, owner)
    if not job:
        raise HTTPException(404, "Job not found.")
    return _job_body(job)


def _event(name: str, data: object) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def _events(
    store: RuntimeStore, job_id: str, owner: str | None
) -> AsyncIterator[str]:
    seen = 0
    while True:
        job = store.get_job(job_id, owner)
        for seq, step in store.job_steps(job_id, after=seen):
            seen = seq
            yield _event("step", step)
        if job is None:
            return
        if job.status == "error":
            yield _event("error", {"error": job.error})
            return
        if job.status == "done":
            yield _event("done", {"result": job.result})
            return
        await asyncio.sleep(POLL_SECONDS)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, store: Store, owner: Owner) -> StreamingResponse:
    # EventSource cannot send the Authorization header, so a signed-in user's
    # stream is a 404 and the frontend polls GET /jobs/{id} with the token.
    if not store.get_job(job_id, owner):
        raise HTTPException(404, "Job not found.")
    return StreamingResponse(
        _events(store, job_id, owner), media_type="text/event-stream"
    )
