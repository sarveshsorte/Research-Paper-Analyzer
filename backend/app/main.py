from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.queries import router as query_router
from backend.app.api.routes.documents import router as document_router
from backend.app.api.routes.jobs import router as job_router
from backend.app.api.routes.workflows import router as workflow_router
from backend.app.api.deps import get_store
from backend.app.api.routes.auth import router as auth_router
from backend.app.config import get_settings
from backend.app.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Open (and migrate) the database before the first request.
    get_store()
    yield


app = FastAPI(title="ResearchLens Query Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_logging(get_settings().log_level)
app.include_router(health_router)
app.include_router(query_router)
app.include_router(document_router)
app.include_router(job_router)
app.include_router(workflow_router)
app.include_router(auth_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "project": "FINPILOT",
        "status": "running",
        "version": "0.1.0",
    }


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    del request
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(ValueError)
async def value_error(request: Request, exc: ValueError) -> JSONResponse:
    del request
    return JSONResponse(status_code=400, content={"detail": str(exc)})