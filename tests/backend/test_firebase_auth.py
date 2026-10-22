"""Firebase ID-token checks behind GET /api/v1/auth/me."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth
from google.auth.exceptions import DefaultCredentialsError

from backend.app.api.routes.auth import router
from backend.app.config import Settings, get_settings
from backend.app.services import firebase_auth

GOOGLE_CLAIMS: dict[str, Any] = {
    "uid": "user-1",
    "email": "ada@example.edu",
    "name": "Ada Lovelace",
    "picture": "https://example.edu/ada.png",
    "firebase": {"sign_in_provider": "google.com"},
}


def make_client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Token checks are faked below, so no real Firebase app or credentials are needed.
    monkeypatch.setattr(firebase_auth, "_firebase_app", lambda *_: object())
    return make_client(Settings(_env_file=None, firebase_project_id="claimlens-test"))


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
    assert response.json() == {"detail": "Sign in to continue."}


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
    assert response.json() == {"detail": detail}


def test_missing_service_account_file_is_not_configured(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, firebase_credentials_path=str(tmp_path / "missing.json")
    )

    response = make_client(settings).get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer id-token"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Firebase sign-in is not configured on the server."
    }
