"""Dependencies shared by the API routes."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from backend.app.config import get_settings
from backend.app.services.container import Services
from backend.app.services.firebase_auth import FirebaseUser, optional_user
from backend.app.services.runtime import RuntimeStore


@lru_cache
def get_store() -> RuntimeStore:
    return RuntimeStore(get_settings().storage_path)


def get_services(request: Request) -> Services:
    """Built once in the app's lifespan (see main.py)."""
    return request.app.state.services


def store_user(store: RuntimeStore, user: FirebaseUser) -> None:
    store.upsert_user(
        user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        provider=user.provider,
    )


def current_owner(
    user: Annotated[FirebaseUser | None, Depends(optional_user)],
    store: Annotated[RuntimeStore, Depends(get_store)],
) -> str | None:
    """The uid that owns the caller's documents and jobs; None for the demo."""
    if user is None:
        return None
    if not store.is_known_user(user.id):
        store_user(store, user)
    return user.id


Store = Annotated[RuntimeStore, Depends(get_store)]
Owner = Annotated[str | None, Depends(current_owner)]
ServicesDep = Annotated[Services, Depends(get_services)]
