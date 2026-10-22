"""Documents, chunks and jobs over HTTP belong to the caller's Firebase uid."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth

from backend.app.api.deps import get_store
from backend.app.api.routes import documents, jobs, workflows
from backend.app.config import Settings, get_settings
from backend.app.services import firebase_auth
from backend.app.services.runtime import RuntimeStore

DEMO: dict[str, str] = {}


def as_user(uid: str) -> dict[str, str]:
    # The fake verifier below treats the token as the uid.
    return {"Authorization": f"Bearer {uid}"}


@pytest.fixture
def background(monkeypatch: pytest.MonkeyPatch) -> list[Coroutine[Any, Any, None]]:
    """Collects background work so a test can run it to completion."""
    pending: list[Coroutine[Any, Any, None]] = []
    monkeypatch.setattr(documents, "run_in_background", pending.append)
    monkeypatch.setattr(workflows, "run_in_background", pending.append)
    return pending


@pytest.fixture
def client(
    store: RuntimeStore,
    monkeypatch: pytest.MonkeyPatch,
    background: list[Coroutine[Any, Any, None]],  # no real background tasks
) -> TestClient:
    def verify_id_token(token: str, **_: Any) -> dict[str, Any]:
        if token == "bad":
            raise auth.InvalidIdTokenError("bad")
        return {
            "uid": token,
            "email": f"{token}@example.edu",
            "firebase": {"sign_in_provider": "password"},
        }

    monkeypatch.setattr(firebase_auth, "_firebase_app", lambda *_: object())
    monkeypatch.setattr(auth, "verify_id_token", verify_id_token)
    app = FastAPI()
    for module in (documents, jobs, workflows):
        app.include_router(module.router)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, firebase_project_id="claimlens-test"
    )
    return TestClient(app)


def run_background(pending: list[Coroutine[Any, Any, None]]) -> None:
    while pending:
        asyncio.run(pending.pop(0))


def test_an_upload_belongs_to_the_uploader(
    client: TestClient,
    background: list[Coroutine[Any, Any, None]],
    paper_pdf: bytes,
    store: RuntimeStore,
) -> None:
    response = client.post(
        "/api/v1/upload",
        headers=as_user("ada"),
        files=[("files", ("lora-study.pdf", paper_pdf, "application/pdf"))],
    )
    assert response.status_code == 202
    document_id = response.json()[0]["document_id"]
    run_background(background)

    listed = client.get("/api/v1/documents", headers=as_user("ada")).json()
    assert [(doc["document_id"], doc["status"]) for doc in listed] == [
        (document_id, "ready")
    ]
    assert client.get("/api/v1/documents", headers=as_user("grace")).json() == []
    assert client.get("/api/v1/documents", headers=DEMO).json() == []
    # The first authenticated request saved the user.
    assert store.is_known_user("ada")


def test_other_callers_cannot_reach_a_document(
    client: TestClient,
    add_user: Callable[[str], None],
    add_ready_document: Callable[[str | None], str],
    store: RuntimeStore,
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    chunk_id = store.search("adapters", [document_id])[0]["chunk_id"]
    paths = [
        f"/api/v1/documents/{document_id}",
        f"/api/v1/documents/{document_id}/file",
        f"/api/v1/chunks/{chunk_id}",
    ]

    for headers in (as_user("grace"), DEMO):
        for path in paths:
            assert client.get(path, headers=headers).status_code == 404, path
        response = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
        assert response.status_code == 404

    for path in paths:
        assert client.get(path, headers=as_user("ada")).status_code == 200, path
    assert client.get(paths[1], headers=as_user("ada")).content.startswith(b"%PDF")


def test_jobs_are_private_to_their_owner(
    client: TestClient,
    background: list[Coroutine[Any, Any, None]],
    add_user: Callable[[str], None],
    add_ready_document: Callable[[str | None], str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    body = {"question": "Do adapters save memory?", "document_ids": [document_id]}

    # Someone else cannot ask about Ada's paper.
    response = client.post("/api/v1/query", json=body, headers=as_user("grace"))
    assert response.status_code == 404

    response = client.post("/api/v1/query", json=body, headers=as_user("ada"))
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    run_background(background)

    job = client.get(f"/api/v1/jobs/{job_id}", headers=as_user("ada")).json()
    assert job["status"] == "done"
    assert job["result"]["claims"][0]["evidence"][0]["document_id"] == document_id
    for headers in (as_user("grace"), DEMO):
        assert client.get(f"/api/v1/jobs/{job_id}", headers=headers).status_code == 404
    # EventSource sends no token, so a signed-in user's stream is a 404 (the
    # frontend then polls GET /jobs/{id} with the token).
    assert client.get(f"/api/v1/jobs/{job_id}/stream").status_code == 404


def test_a_demo_job_streams_its_steps_and_result(
    client: TestClient, add_ready_document: Callable[[str | None], str]
) -> None:
    ids = [add_ready_document(None), add_ready_document(None)]
    response = client.post("/api/v1/compare", json={"document_ids": ids})
    job_id = response.json()["job_id"]

    stream = client.get(f"/api/v1/jobs/{job_id}/stream").text

    assert stream.startswith(
        'event: step\ndata: {"type": "started", "message": "Processing request"}\n\n'
    )
    assert "event: done\ndata: " in stream
    assert '"attribute": "Title"' in stream


def test_a_claim_check_reads_only_the_callers_papers(
    client: TestClient,
    add_user: Callable[[str], None],
    add_ready_document: Callable[[str | None], str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    claim = {"claim": "Low-rank adapters match full fine-tuning."}

    def papers(headers: dict[str, str]) -> list[str]:
        response = client.post("/api/v1/check", json=claim, headers=headers)
        job_id = response.json()["job_id"]
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        return [paper["document_id"] for paper in job["result"]["papers"]]

    assert papers(as_user("ada")) == [document_id]
    assert papers(as_user("grace")) == []
    assert papers(DEMO) == []


def test_an_invalid_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/documents", headers=as_user("bad"))

    assert response.status_code == 401
    assert response.json() == {"detail": "The sign-in token is invalid."}
