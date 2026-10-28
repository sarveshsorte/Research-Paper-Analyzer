from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.frontend_compat import router as frontend_compat_router
from backend.app.api.routes.queries import router as query_router
from backend.app.config import get_settings
from backend.app.observability.logging import configure_logging

settings = get_settings()
app = FastAPI(title="ResearchLens Query Service", version="0.1.0")
configured_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_logging(settings.log_level)
app.include_router(health_router)
app.include_router(query_router)
app.include_router(frontend_compat_router)


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