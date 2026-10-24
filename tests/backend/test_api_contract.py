"""The HTTP contract the React app relies on (§4), with search and downloads mocked."""

import hashlib
import json
from collections.abc import Iterator

import pytest
from conftest import (
    OTHER_PAPER_TEXT,
    PAPER_TEXT,
    finished_job,
    make_app,
    make_pdf,
    wait_for,
)
from fastapi.testclient import TestClient

from backend.app.api.routes import documents, health, jobs, workflows
from backend.app.config import Settings
from backend.app.services.runtime import RuntimeStore
from backend.app.services.search import PaperHit, SearchError


@pytest.fixture
def client(settings: Settings, store: RuntimeStore) -> Iterator[TestClient]:
    app = make_app(
        settings, store, health.router, documents.router, jobs.router, workflows.router
    )
    with TestClient(app) as test_client:
        yield test_client


def upload(client: TestClient, *files: tuple[str, bytes]):
    return client.post(
        "/api/v1/upload",
        files=[
            ("files", (name, content, "application/pdf")) for name, content in files
        ],
    )


def ready(client: TestClient, document_id: str) -> dict:
    return wait_for(
        lambda: (
            (d := client.get(f"/api/v1/documents/{document_id}").json())["status"]
            != "processing"
            and d
        )
    )


def test_health_reports_what_each_part_uses(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["mock_ai"] is True
    assert body["checks"]["embeddings"] == "local fallback"
    assert body["checks"]["nemotron"] == "not configured"
    assert body["version"]


@pytest.mark.parametrize(
    ("files", "status", "code"),
    [
        ([("notes.txt", b"hello")], 415, "UNSUPPORTED_TYPE"),
        ([("fake.pdf", b"<html></html>")], 415, "UNSUPPORTED_TYPE"),
        ([(f"p{i}.pdf", b"%PDF-1") for i in range(6)], 400, "INVALID_REQUEST"),
    ],
)
def test_upload_rejections_use_the_error_shape(
    client: TestClient, files, status: int, code: str
) -> None:
    response = upload(client, *files)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_an_oversize_upload_is_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "MAX_BYTES", 10)

    response = upload(client, ("big.pdf", b"%PDF-" + b"x" * 20))

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "FILE_TOO_LARGE",
        "message": "big.pdf is over 25 MB.",
    }


def test_validation_errors_are_400(client: TestClient) -> None:
    response = client.post("/api/v1/query", json={"question": "", "document_ids": []})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_the_same_file_twice_is_one_document(client: TestClient) -> None:
    pdf = make_pdf(PAPER_TEXT)
    first = upload(client, ("a.pdf", pdf)).json()[0]
    ready(client, first["document_id"])

    second = upload(client, ("renamed.pdf", pdf)).json()[0]

    assert second == {
        "document_id": first["document_id"],
        "filename": "renamed.pdf",
        "status": "ready",
    }
    assert len(client.get("/api/v1/documents").json()) == 1
    assert len(client.get("/api/v1/documents?status=ready").json()) == 1
    assert client.get("/api/v1/documents?status=failed").json() == []


def test_query_needs_ready_papers(client: TestClient, store: RuntimeStore) -> None:
    document = store.create_document("slow.pdf", b"%PDF-1", None)

    response = client.post(
        "/api/v1/query",
        json={"question": "Why?", "document_ids": [document["document_id"]]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_READY"


def test_fetch_by_link_downloads_and_indexes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = client.app.state.services
    pdf = make_pdf(PAPER_TEXT)

    async def resolve_link(text: str) -> PaperHit:
        return PaperHit(
            source="arxiv",
            title="Adapters at Scale",
            arxiv_id="2401.00001",
            pdf_url="https://arxiv.org/pdf/2401.00001",
            authors=["A. Lovelace"],
            year=2024,
        )

    async def fetch(url: str) -> tuple[bytes, str]:
        return pdf, hashlib.sha256(pdf).hexdigest()

    monkeypatch.setattr(services.search, "resolve_link", resolve_link)
    monkeypatch.setattr(services.downloader, "download", fetch)

    response = client.post(
        "/api/v1/documents/fetch", json={"url": "arxiv.org/abs/2401.00001"}
    )

    assert response.status_code == 202
    document = response.json()
    assert (document["source"], document["title"], document["status"]) == (
        "link",
        "Adapters at Scale",
        "processing",
    )
    assert ready(client, document["document_id"])["status"] == "ready"
    listed = client.get("/api/v1/documents").json()[0]
    assert (listed["authors"], listed["year"]) == ("A. Lovelace", 2024)


def test_fetch_by_link_explains_a_bad_link(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def resolve_link(text: str) -> PaperHit:
        raise SearchError("Enter an arXiv URL, DOI or Semantic Scholar link.")

    monkeypatch.setattr(client.app.state.services.search, "resolve_link", resolve_link)

    response = client.post("/api/v1/documents/fetch", json={"url": "hello"})

    assert response.status_code == 400
    assert response.json()["error"]["message"].startswith("Enter an arXiv URL")


def test_retry_reprocesses_a_failed_document(
    client: TestClient, store: RuntimeStore
) -> None:
    document = store.create_document("a.pdf", make_pdf(PAPER_TEXT), None)
    store.mark_failed(document["document_id"], "Processing failed. Try again.")

    response = client.post(f"/api/v1/documents/{document['document_id']}/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert ready(client, document["document_id"])["status"] == "ready"


def test_claim_check_searches_downloads_indexes_and_judges(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = client.app.state.services
    pdfs = {
        "https://arxiv.org/pdf/1": make_pdf(PAPER_TEXT),
        "https://arxiv.org/pdf/2": make_pdf(OTHER_PAPER_TEXT),
    }

    async def search(source: str, queries: list[str], limit: int) -> list[PaperHit]:
        if source == "arxiv":
            raise SearchError("arXiv returned 503.")
        return [
            PaperHit(
                source=source,
                title="Adapters on math",
                pdf_url="https://arxiv.org/pdf/1",
                arxiv_id="1",
                authors=["A. Lovelace"],
                year=2024,
            ),
            PaperHit(
                source=source,
                title="Adapters on code",
                pdf_url="https://arxiv.org/pdf/2",
                arxiv_id="2",
            ),
        ]

    async def fetch(url: str) -> tuple[bytes, str]:
        return pdfs[url], hashlib.sha256(pdfs[url]).hexdigest()

    monkeypatch.setattr(services.search, "search", search)
    monkeypatch.setattr(services.downloader, "download", fetch)

    response = client.post(
        "/api/v1/check",
        json={
            "claim": "Low-rank adapters match full fine-tuning",
            "sources": ["semantic_scholar", "arxiv", "tavily"],
            "max_papers": 2,
        },
    )
    job = finished_job(client, response.json()["job_id"])

    assert job["status"] == "done", job
    result = job["result"]
    assert {paper["title"] for paper in result["papers"]} == {
        "Adapters on math",
        "Adapters on code",
    }
    assert {paper["source"] for paper in result["papers"]} == {"search"}
    assert result["supports"] and result["contradicts"]
    assert result["verified_quotes"] == result["total_quotes"]
    assert result["sources"] == [
        {"name": "Semantic Scholar", "count": 2},
        {"name": "arXiv", "count": 0},
        {"name": "Tavily", "count": 0},
    ]
    stream = client.get(f"/api/v1/jobs/{job['job_id']}/stream").text
    messages = [
        json.loads(line[6:])["message"]
        for line in stream.splitlines()
        if line.startswith("data: ") and '"message"' in line
    ]
    assert "Searched Semantic Scholar — 2 results" in messages
    assert "arXiv unavailable — arXiv returned 503." in messages
    assert "Skipped Tavily — no API key configured" in messages
    assert "Downloaded 2 open-access PDFs" in messages


def test_health_says_when_the_firebase_key_file_is_missing(tmp_path) -> None:
    assert health._firebase_status(str(tmp_path / "missing.json")) == (
        "credentials file missing"
    )
    key = tmp_path / "firebase-service-account.json"
    key.write_text("{}")
    assert health._firebase_status(str(key)) == "configured"
