import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.dependencies import get_orchestrator
from query_pipeline.app.pipeline.orchestrator import QueryOrchestrator
from query_pipeline.app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}",
    tags=["queries"],
)


@router.post("/query", response_model=QueryResponse)
async def query_workspace(
    workspace_id: str,
    request: QueryRequest,
    x_user_id: str | None = Header(default=None),
    orchestrator: QueryOrchestrator = Depends(get_orchestrator),
) -> QueryResponse:
    try:
        return await orchestrator.run(workspace_id, request, user_id=x_user_id)
    except (TimeoutError, ConnectionError) as exc:
        raise HTTPException(
            status_code=503, detail="A query provider is unavailable"
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/query/stream")
async def stream_query_workspace(
    workspace_id: str,
    request: QueryRequest,
    x_user_id: str | None = Header(default=None),
    orchestrator: QueryOrchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        yield "event: status\ndata: " + json.dumps(
            {"status": "running", "message": "Retrieving evidence"}
        ) + "\n\n"
        try:
            response = await orchestrator.run(workspace_id, request, user_id=x_user_id)
        except PermissionError as exc:
            yield "event: error\ndata: " + json.dumps(
                {"code": "FORBIDDEN", "message": str(exc)}
            ) + "\n\n"
            return
        except (TimeoutError, ConnectionError) as exc:
            yield "event: error\ndata: " + json.dumps(
                {"code": "UPSTREAM_ERROR", "message": str(exc)}
            ) + "\n\n"
            return
        except ValueError as exc:
            yield "event: error\ndata: " + json.dumps(
                {"code": "INVALID_REQUEST", "message": str(exc)}
            ) + "\n\n"
            return
        yield "event: status\ndata: " + json.dumps(
            {"status": response.pipeline_status, "message": "Answer generated"}
        ) + "\n\n"
        yield "event: done\ndata: " + json.dumps(
            {"result": response.model_dump()}
        ) + "\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )