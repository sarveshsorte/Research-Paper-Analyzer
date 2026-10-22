import os
from pathlib import Path

from fastapi import APIRouter, Request

from backend.app.adapters.providers import HashingEmbedder

router = APIRouter(tags=["health"])
VERSION = "0.2.0"


def _check(run) -> str:
    try:
        return run()
    except Exception:
        return "error"


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Process liveness for Docker and the query service's own tests."""
    return {"status": "ok"}


@router.get("/api/v1/health")
async def health(request: Request) -> dict:
    """{status, version, mock_ai} per the contract, plus what each part is using.

    Never raises: a failing check is reported as "error".
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        return {"status": "starting", "version": VERSION, "mock_ai": True, "checks": {}}

    def database() -> str:
        services.store.ping()
        return "ok"

    def bm25() -> str:
        path = Path(services.documents.bm25.database_path)
        folder = path.parent if path.parent.exists() else Path.cwd()
        return "ok" if os.access(folder, os.W_OK) else "not writable"

    embedder = services.documents.embedder
    settings = services.settings
    checks = {
        "database": _check(database),
        "bm25_index": _check(bm25),
        "embeddings": (
            "local fallback"
            if isinstance(embedder, HashingEmbedder)
            else embedder.model_id
        ),
        "nemotron": services.queries.chat.model_id
        if services.queries.chat
        else "not configured",
        "semantic_scholar": "api key"
        if settings.semantic_scholar_api_key
        else "public",
        "arxiv": "public",
        "tavily": "configured" if settings.tavily_api_key else "not configured",
        "firebase": (
            "configured"
            if settings.firebase_credentials_path
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            else "not configured"
        ),
    }
    healthy = checks["database"] == "ok" and checks["bm25_index"] == "ok"
    return {
        "status": "ok" if healthy else "degraded",
        "version": VERSION,
        "mock_ai": services.mock_ai,
        "checks": checks,
    }
