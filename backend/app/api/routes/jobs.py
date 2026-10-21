import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.services.runtime import Job, store

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _job_body(job: Job) -> dict:
    body = {"job_id": job.job_id, "kind": job.kind, "status": job.status}
    if job.status == "done":
        body["result"] = job.result
    if job.status == "error":
        body["error"] = job.error
    return body


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return _job_body(job)


async def _events(job: Job) -> AsyncIterator[str]:
    yield f"event: step\ndata: {json.dumps({'type': 'started', 'message': 'Processing request'})}\n\n"
    while job.status == "running":
        await asyncio.sleep(0.25)
    if job.status == "error":
        yield f"event: error\ndata: {json.dumps({'error': job.error})}\n\n"
    else:
        yield f"event: done\ndata: {json.dumps({'result': job.result})}\n\n"


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return StreamingResponse(_events(job), media_type="text/event-stream")
