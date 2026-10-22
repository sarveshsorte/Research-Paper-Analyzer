"""Shared fixtures for the backend tests (local embeddings, no network)."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.app.adapters.document_pipeline import DocumentPipelineAdapter
from backend.app.adapters.providers import HashingEmbedder
from backend.app.api.deps import get_store
from backend.app.config import Settings, get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.services.container import build_services
from backend.app.services.runtime import RuntimeStore
from document_pipeline.indexing import BM25Indexer

PAPER_TEXT = (
    "Introduction\n"
    "Low-rank adapters match full fine-tuning on math reasoning benchmarks. "
    "The adapters train three times faster and use far less memory. "
    "Results hold across model sizes and random seeds."
)
OTHER_PAPER_TEXT = (
    "Results\n"
    "Low-rank adapters do not match full fine-tuning on code generation benchmarks. "
    "Full fine-tuning reaches 61.2 percent while adapters reach 48.0 percent. "
    "The gap grows with longer training runs."
)


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 520, 760), text, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


@pytest.fixture
def paper_pdf() -> bytes:
    return make_pdf(PAPER_TEXT)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Explicit values so keys in the developer's environment never leak in.
    return Settings(
        _env_file=None,
        storage_path=str(tmp_path / "claimlens.sqlite3"),
        bm25_index_path=str(tmp_path / "bm25.sqlite3"),
        embedding_base_url=None,
        embedding_api_key=None,
        embedding_model=None,
        nebius_api_key=None,
        nebius_model=None,
        semantic_scholar_api_key=None,
        tavily_api_key=None,
        firebase_project_id="claimlens-test",
    )


@pytest.fixture
def store(settings: Settings) -> RuntimeStore:
    return RuntimeStore(settings.storage_path)


@pytest.fixture
def documents(store: RuntimeStore, settings: Settings) -> DocumentPipelineAdapter:
    return DocumentPipelineAdapter(
        store, HashingEmbedder(), BM25Indexer(settings.bm25_index_path)
    )


@pytest.fixture
def add_user(store: RuntimeStore) -> Callable[[str], None]:
    def add(uid: str) -> None:
        store.upsert_user(
            uid, email=f"{uid}@example.edu", name=uid, picture=None, provider="password"
        )

    return add


@pytest.fixture
def add_ready_document(
    store: RuntimeStore, documents: DocumentPipelineAdapter
) -> Callable[..., str]:
    """Uploads a one-page PDF and runs the teammates' document pipeline over it."""

    def add(
        owner_uid: str | None, text: str = PAPER_TEXT, name: str = "lora-study.pdf"
    ) -> str:
        document = store.create_document(name, make_pdf(text), owner_uid)
        assert asyncio.run(documents.process(document["document_id"]))
        return str(document["document_id"])

    return add


def make_app(settings: Settings, store: RuntimeStore, *routers: APIRouter) -> FastAPI:
    """An app with the given routers and real services built on the test store."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = build_services(settings, store)
        yield
        await app.state.services.close()

    app = FastAPI(lifespan=lifespan)
    register_error_handlers(app)
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def wait_for(check: Callable[[], Any], timeout: float = 30) -> Any:
    """Polls `check` until it returns something truthy (background work runs)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting for background work")


def finished_job(
    client: TestClient, job_id: str, headers: dict[str, str] | None = None
) -> dict:
    def check() -> dict | None:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers or {}).json()
        return job if job.get("status") != "running" else None

    return wait_for(check)
