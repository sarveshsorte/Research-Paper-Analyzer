import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.app.config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
github_states: set[str] = set()


class GoogleTokenRequest(BaseModel):
    credential: str


@router.post("/google")
async def authenticate_google(body: GoogleTokenRequest) -> dict[str, object]:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(503, "Google OAuth is not configured on the server.")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": body.credential},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Google OAuth verification is unavailable.") from exc
    if response.status_code != 200:
        raise HTTPException(401, "Google credential is invalid or expired.")

    claims = response.json()
    if claims.get("aud") != settings.google_client_id:
        raise HTTPException(401, "Google credential was issued for another client.")
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(401, "Google credential issuer is invalid.")
    if not claims.get("sub") or not claims.get("email"):
        raise HTTPException(401, "Google credential is missing required identity claims.")

    return {
        "access_token": body.credential,
        "user": {
            "id": claims["sub"],
            "email": claims["email"],
            "name": claims.get("name") or claims["email"],
            "picture": claims.get("picture"),
        },
    }


@router.get("/github/login")
async def github_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "GitHub OAuth is not configured on the server.")
    state = secrets.token_urlsafe(32)
    github_states.add(state)
    params = urlencode({
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.backend_url}/api/v1/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
async def github_callback(
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
) -> RedirectResponse:
    settings = get_settings()
    if state not in github_states:
        raise HTTPException(401, "GitHub OAuth state is invalid or expired.")
    github_states.remove(state)
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "GitHub OAuth is not configured on the server.")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": f"{settings.backend_url}/api/v1/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if token_response.status_code != 200 or not access_token:
                raise HTTPException(401, "GitHub authorization code is invalid.")
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            user = user_response.json()
            email = user.get("email")
            if not email:
                emails_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                emails = emails_response.json()
                email = next(
                    (item["email"] for item in emails if item.get("primary") and item.get("verified")),
                    None,
                )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "GitHub OAuth verification is unavailable.") from exc
    if not user_response.is_success or not user.get("id") or not email:
        raise HTTPException(401, "GitHub account identity could not be verified.")

    params = urlencode({
        "provider": "github",
        "access_token": access_token,
        "user_id": str(user["id"]),
        "email": email,
        "name": user.get("name") or user.get("login") or email,
        "picture": user.get("avatar_url") or "",
    })
    return RedirectResponse(f"{settings.frontend_url}/login?{params}")
