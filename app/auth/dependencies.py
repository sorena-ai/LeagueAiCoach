from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_session_token
from app.users import repository as user_repository
from app.users.models import User
from app.utils.log_context import bind_log_context


def _parse_authorization_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header") from exc
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth scheme")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return token


def get_session_token(authorization: str | None = Header(default=None)) -> str:
    return _parse_authorization_header(authorization)


async def get_current_user(token: str = Depends(get_session_token)) -> User:
    payload = decode_session_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # Bind before the lookup so a "User not found" 401 still names the subject.
    bind_log_context(user_id=user_id)
    user = await user_repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Every log line for the rest of this request now carries the user.
    bind_log_context(user_email=user.email, user_name=user.display_name)
    return user
