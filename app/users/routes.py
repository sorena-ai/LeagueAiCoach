from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.users.models import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=User)
async def get_current_user_profile(user: User = Depends(get_current_user)) -> User:
    return user
