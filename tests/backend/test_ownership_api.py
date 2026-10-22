"""Documents, chunks and jobs over HTTP belong to the caller's Firebase uid."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from conftest import finished_job, make_app, wait_for
from fastapi.testclient import TestClient
from firebase_admin import auth

from backend.app.api.routes import documents, jobs, workflows
from backend.app.config import Settings
from backend.app.services import firebase_auth
from backend.app.services.runtime import RuntimeStore

DEMO: dict[str, str] = {}


def as_user(uid: str) -> dict[str, str]:
    # The fake verifier below treats the token as the uid.
    return {"Authorization": f"Bearer {uid}"}


@pytest.fixture
def client(
    settings: Settings, store: RuntimeStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
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
    app = make_app(settings, store, documents.router, jobs.router, workflows.router)
    with TestClient(app) as test_client:
        yield test_client


def test_an_upload_belongs_to_the_uploader(
    client: TestClient, paper_pdf: bytes, store: RuntimeStore
) -> None:
    response = client.post(
        "/api/v1/upload",
        headers=as_user("ada"),
        files=[("files", ("lora-study.pdf", paper_pdf, "application/pdf"))],
    )
    assert response.status_code == 202
    document_id = response.json()[0]["document_id"]

    def ready() -> list[dict]:
        listed = client.get("/api/v1/documents", headers=as_user("ada")).json()
        return listed if listed and listed[0]["status"] == "ready" else []

    listed = wait_for(ready)
    assert [doc["document_id"] for doc in listed] == [document_id]
    assert client.get("/api/v1/documents", headers=as_user("grace")).json() == []
    assert client.get("/api/v1/documents", headers=DEMO).json() == []
    # The first authenticated request saved the user.
    assert store.is_known_user("ada")


def test_other_callers_cannot_reach_a_document(
    client: TestClient,
    add_user: Callable[[str], None],
    add_ready_document: Callable[..., str],
    store: RuntimeStore,
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    chunk_id = store.first_chunks(document_id, 1)[0].chunk_id
    paths = [
        f"/api/v1/documents/{document_id}",
        f"/api/v1/documents/{document_id}/file",
        f"/api/v1/chunks/{chunk_id}",
    ]

    for headers in (as_user("grace"), DEMO):
        for path in paths:
            response = client.get(path, headers=headers)
            assert response.status_code == 404, path
            assert response.json()["error"]["code"] == "NOT_FOUND"
        response = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
        assert response.status_code == 404

    for path in paths:
        assert client.get(path, headers=as_user("ada")).status_code == 200, path
    assert client.get(paths[1], headers=as_user("ada")).content.startswith(b"%PDF")


def test_jobs_are_private_to_their_owner(
    client: TestClient,
    add_user: Callable[[str], None],
    add_ready_document: Callable[..., str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    body = {"question": "Do adapters save memory?", "document_ids": [document_id]}

    # Someone else cannot ask about Ada's paper.
    response = client.post("/api/v1/query", json=body, headers=as_user("grace"))
    assert response.status_code == 404

    response = client.post("/api/v1/query", json=body, headers=as_user("ada"))
    assert response.status_code == 202
    job = finished_job(client, response.json()["job_id"], as_user("ada"))

    assert job["status"] == "done"
    evidence = job["result"]["claims"][0]["evidence"][0]
    assert evidence["document_id"] == document_id
    for headers in (as_user("grace"), DEMO):
        response = client.get(f"/api/v1/jobs/{job['job_id']}", headers=headers)
        assert response.status_code == 404
    # EventSource sends no token, so a signed-in user's stream is a 404 (the
    # frontend then polls GET /jobs/{id} with the token).
    assert client.get(f"/api/v1/jobs/{job['job_id']}/stream").status_code == 404


def test_a_demo_job_streams_its_steps_and_result(
    client: TestClient, add_ready_document: Callable[..., str]
) -> None:
    ids = [add_ready_document(None), add_ready_document(None, name="other.pdf")]
    job_id = client.post("/api/v1/compare", json={"document_ids": ids}).json()["job_id"]
    finished_job(client, job_id)

    stream = client.get(f"/api/v1/jobs/{job_id}/stream").text

    assert stream.startswith(
        'event: step\ndata: {"type": "started", "message": "Processing request", '
        '"t": 0}\n\n'
    )
    assert '"type": "retrieving"' in stream
    assert "event: done\ndata: " in stream
    assert '"attribute": "Method"' in stream


def test_a_claim_check_reads_only_the_callers_papers(
    client: TestClient,
    add_user: Callable[[str], None],
    add_ready_document: Callable[..., str],
) -> None:
    add_user("ada")
    document_id = add_ready_document("ada")
    # Tavily has no key in tests, so the check falls back to the caller's library.
    claim = {
        "claim": "Low-rank adapters match full fine-tuning.",
        "sources": ["tavily"],
    }

    def papers(headers: dict[str, str]) -> list[str]:
        response = client.post("/api/v1/check", json=claim, headers=headers)
        job = finished_job(client, response.json()["job_id"], headers)
        return [paper["document_id"] for paper in job["result"]["papers"]]

    assert papers(as_user("ada")) == [document_id]
    assert papers(as_user("grace")) == []
    assert papers(DEMO) == []


def test_an_invalid_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/documents", headers=as_user("bad"))

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHENTICATED", "message": "The sign-in token is invalid."}
    }
