"""Shared fixtures for the backend tests."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from backend.app.services.runtime import RuntimeStore

PAPER_TEXT = (
    "Introduction\n"
    "Low-rank adapters match full fine-tuning on math reasoning benchmarks. "
    "The adapters train three times faster and use far less memory. "
    "Results hold across model sizes and random seeds."
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
def store(tmp_path: Path) -> RuntimeStore:
    return RuntimeStore(tmp_path / "claimlens.sqlite3")


@pytest.fixture
def add_user(store: RuntimeStore) -> Callable[[str], None]:
    def add(uid: str) -> None:
        store.upsert_user(
            uid, email=f"{uid}@example.edu", name=uid, picture=None, provider="password"
        )

    return add


@pytest.fixture
def add_ready_document(store: RuntimeStore) -> Callable[[str | None], str]:
    """Uploads a one-page PDF for `owner_uid` and runs the real document pipeline."""

    def add(owner_uid: str | None) -> str:
        document = store.create_document(
            "lora-study.pdf", make_pdf(PAPER_TEXT), owner_uid
        )
        asyncio.run(store.process(document["document_id"]))
        assert store.get_document(document["document_id"], owner_uid)["status"] == (
            "ready"
        )
        return str(document["document_id"])

    return add
