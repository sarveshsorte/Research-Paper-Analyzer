from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.services.firebase_auth import FirebaseUser, current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class CurrentUserResponse(BaseModel):
    user: FirebaseUser


@router.get("/me")
def read_current_user(
    user: Annotated[FirebaseUser, Depends(current_user)],
) -> CurrentUserResponse:
    """Confirms a Firebase ID token and returns who it belongs to."""
    return CurrentUserResponse(user=user)
