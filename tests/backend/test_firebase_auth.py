"""Firebase ID-token checks behind GET /api/v1/auth/me."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth
from google.auth.exceptions import DefaultCredentialsError

from backend.app.api.deps import get_store
from backend.app.api.routes.auth import router
from backend.app.config import Settings, get_settings
from backend.app.core.errors import CODE_BY_STATUS, register_error_handlers
from backend.app.services import firebase_auth
from backend.app.services.runtime import RuntimeStore

GOOGLE_CLAIMS: dict[str, Any] = {
    "uid": "user-1",
    "email": "ada@example.edu",
    "name": "Ada Lovelace",
    "picture": "https://example.edu/ada.png",
    "firebase": {"sign_in_provider": "google.com"},
}


def make_client(settings: Settings, store: RuntimeStore) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, store: RuntimeStore) -> TestClient:
    # Token checks are faked below, so no real Firebase app or credentials are needed.
    monkeypatch.setattr(firebase_auth, "_firebase_app", lambda *_: object())
    return make_client(
        Settings(_env_file=None, firebase_project_id="claimlens-test"), store
    )


def fake_verify(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any] | Exception
) -> list[str]:
    """Makes token verification return `result` (or raise it); records tokens."""
    tokens: list[str] = []

    def verify_id_token(token: str, **_: Any) -> dict[str, Any]:
        tokens.append(token)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(auth, "verify_id_token", verify_id_token)
    return tokens


def test_returns_the_signed_in_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = fake_verify(monkeypatch, GOOGLE_CLAIMS)

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer id-token"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": "user-1",
            "email": "ada@example.edu",
            "name": "Ada Lovelace",
            "picture": "https://example.edu/ada.png",
            "provider": "google.com",
        }
    }
    assert tokens == ["id-token"]


def test_saves_the_profile_on_sign_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, store: RuntimeStore
) -> None:
    fake_verify(monkeypatch, GOOGLE_CLAIMS)

    client.get("/api/v1/auth/me", headers={"Authorization": "Bearer id-token"})

    assert store.is_known_user("user-1")
    # Documents can now be owned by the user (the foreign key needs the row).
    assert store.create_document("a.pdf", b"%PDF", "user-1")["document_id"]


def test_name_falls_back_to_the_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_verify(
        monkeypatch,
        {
            "uid": "user-2",
            "email": "grace@example.edu",
            "firebase": {"sign_in_provider": "password"},
        },
    )

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer id-token"}
    )

    assert response.json()["user"] == {
        "id": "user-2",
        "email": "grace@example.edu",
        "name": "grace@example.edu",
        "picture": None,
        "provider": "password",
    }


def test_missing_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "error": {"code": "UNAUTHENTICATED", "message": "Sign in to continue."}
    }


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (
            auth.ExpiredIdTokenError("expired", None),
            401,
            "Your sign-in has expired. Sign in again.",
        ),
        (auth.InvalidIdTokenError("bad"), 401, "The sign-in token is invalid."),
        (
            auth.CertificateFetchError("offline", None),
            503,
            "Firebase sign-in verification is unavailable.",
        ),
        (
            DefaultCredentialsError("no credentials"),
            503,
            "Firebase sign-in is not configured on the server.",
        ),
        (
            ValueError("no project ID"),
            503,
            "Firebase sign-in is not configured on the server.",
        ),
    ],
)
def test_verification_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    detail: str,
) -> None:
    fake_verify(monkeypatch, error)

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer id-token"}
    )

    assert response.status_code == status
    assert response.json() == {
        "error": {"code": CODE_BY_STATUS[status], "message": detail}
    }


def test_missing_service_account_file_is_not_configured(
    tmp_path: Path, store: RuntimeStore
) -> None:
    settings = Settings(
        _env_file=None, firebase_credentials_path=str(tmp_path / "missing.json")
    )

    response = make_client(settings, store).get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer id-token"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Firebase sign-in is not configured on the server.",
        }
    }
