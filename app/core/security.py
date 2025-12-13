from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt

from fastapi import HTTPException, status

from app.config import settings

ALGORITHM = "HS256"

def create_session_token(user_id: str, session_id: str) -> str:
    """Create a signed JWT token for desktop sessions."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.session_token_expires_minutes)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "iss": settings.session_token_issuer,
        "aud": settings.session_token_audience,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.session_token_secret, algorithm=ALGORITHM)


def decode_session_token(token: str) -> Dict[str, Any]:
    """Decode and validate a session token."""
    try:
        return jwt.decode(
            token,
            settings.session_token_secret,
            algorithms=[ALGORITHM],
            audience=settings.session_token_audience,
            issuer=settings.session_token_issuer,
        )
    except JWTError as exc:  # pragma: no cover - treated uniformly
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token for the client to store.

    This token is used to obtain new session tokens without re-authenticating.
    It has a much longer expiration (30 days) than the session token.
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.refresh_token_expires_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iss": settings.session_token_issuer,
        "aud": settings.session_token_audience,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.session_token_secret, algorithm=ALGORITHM)


def decode_refresh_token(token: str) -> Dict[str, Any]:
    """Decode and validate a refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.session_token_secret,
            algorithms=[ALGORITHM],
            audience=settings.session_token_audience,
            issuer=settings.session_token_issuer,
        )
        # Verify it's actually a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

