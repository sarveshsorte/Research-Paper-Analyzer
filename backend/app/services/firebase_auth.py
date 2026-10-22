"""Firebase Authentication: verifies the ID token sent as `Authorization: Bearer`."""

import logging
from functools import lru_cache
from typing import Annotated, Any

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from google.auth.exceptions import DefaultCredentialsError
from pydantic import BaseModel

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)

# Tolerates small clock differences between this server and Firebase.
CLOCK_SKEW_SECONDS = 10


class FirebaseUser(BaseModel):
    id: str
    email: str | None
    name: str
    picture: str | None
    provider: str


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


def _not_configured() -> HTTPException:
    return HTTPException(503, "Firebase sign-in is not configured on the server.")


@lru_cache
def _firebase_app(
    credentials_path: str | None, project_id: str | None
) -> firebase_admin.App:
    credential = (
        credentials.Certificate(credentials_path)
        if credentials_path
        else credentials.ApplicationDefault()
    )
    options = {"projectId": project_id} if project_id else {}
    return firebase_admin.initialize_app(
        credential, options, name=f"claimlens:{credentials_path}:{project_id}"
    )


def verify_firebase_token(token: str, settings: Settings) -> FirebaseUser:
    try:
        app = _firebase_app(
            settings.firebase_credentials_path, settings.firebase_project_id
        )
        claims: dict[str, Any] = auth.verify_id_token(
            token, app=app, clock_skew_seconds=CLOCK_SKEW_SECONDS
        )
    except auth.ExpiredIdTokenError as exc:
        raise _unauthorized("Your sign-in has expired. Sign in again.") from exc
    except auth.InvalidIdTokenError as exc:
        raise _unauthorized("The sign-in token is invalid.") from exc
    except auth.CertificateFetchError as exc:
        raise HTTPException(
            503, "Firebase sign-in verification is unavailable."
        ) from exc
    except (DefaultCredentialsError, OSError, ValueError) as exc:
        # No credentials, an unreadable service-account file, or no project ID.
        logger.error("Firebase is misconfigured: %s", exc)
        raise _not_configured() from exc

    email = claims.get("email")
    return FirebaseUser(
        id=claims["uid"],
        email=email,
        name=claims.get("name") or email or "ClaimLens user",
        picture=claims.get("picture"),
        provider=claims.get("firebase", {}).get("sign_in_provider", "unknown"),
    )


def current_user(
    authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FirebaseUser:
    """The signed-in Firebase user; 401 without a valid ID token."""
    if authorization is None:
        raise _unauthorized("Sign in to continue.")
    return verify_firebase_token(authorization.credentials, settings)
