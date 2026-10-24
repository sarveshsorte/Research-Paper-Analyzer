import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.deps import get_store
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.documents import router as document_router
from backend.app.api.routes.health import VERSION
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.jobs import router as job_router
from backend.app.api.routes.queries import router as query_router
from backend.app.api.routes.workflows import router as workflow_router
from backend.app.config import get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.observability.logging import configure_logging
from backend.app.services.container import build_services

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Open (and migrate) the database and build the pipeline adapters once.
    started = time.perf_counter()
    app.state.services = build_services(get_settings(), get_store())
    logger.info("services_ready in %.0f ms", (time.perf_counter() - started) * 1000)
    yield
    await app.state.services.close()


app = FastAPI(title="ClaimLens API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_logging(get_settings().log_level)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(query_router)
app.include_router(document_router)
app.include_router(job_router)
app.include_router(workflow_router)
app.include_router(auth_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"project": "ClaimLens", "status": "running", "version": VERSION}
