from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.auth.session_store import SessionData, SessionStatus, session_store
from app.config import settings
from app.core.security import create_session_token, create_refresh_token, decode_refresh_token
from app.users import repository as user_repository
from app.users.models import User, UserProfile

logger = logging.getLogger(__name__)


def _base_login_url() -> str:
    return settings.login_base_url.rstrip("/")


def _auth0_base_url() -> str:
    domain = settings.auth0_domain.rstrip("/")
    if not domain:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 domain not configured")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    return domain


def _generate_pkce_pair() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def build_login_redirect(session_id: str) -> str:
    base = settings.login_base_url.rstrip("/")
    return f"{base}/auth/login?session_id={session_id}"


def get_success_page_url() -> str:
    return settings.login_success_url.rstrip("/")


async def create_session() -> Dict[str, str]:
    session_id = uuid.uuid4().hex
    await session_store.create_session(settings.auth_session_ttl_seconds, session_id)
    logger.info("Created auth session %s", session_id)
    return {"session_id": session_id, "login_url": build_login_redirect(session_id)}


async def build_authorize_url(session_id: str) -> str:
    session = await session_store.get_by_id(session_id)
    if session is None or session.status is not SessionStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    await session_store.attach_pkce(session_id, state, code_verifier)

    params = {
        "client_id": settings.auth0_client_id,
        "audience": settings.auth0_audience,
        "response_type": "code",
        "redirect_uri": settings.auth0_callback_url,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }

    if not settings.auth0_client_id or not settings.auth0_callback_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 not configured")

    authorize_url = f"{_auth0_base_url()}/authorize?{urlencode(params)}"
    logger.info("Session %s redirecting browser to Auth0", session_id)
    return authorize_url


async def complete_auth_flow(code: str, state: str) -> SessionData:
    session = await session_store.get_by_state(state)
    if session is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown session state")
    if not session.code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session missing PKCE data")

    logger.info("Session %s exchanging authorization code", session.session_id)
    tokens = await _exchange_code_for_tokens(code, session.code_verifier)
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Auth0 token exchange failed")

    profile = await _fetch_user_profile(access_token)
    user = await user_repository.upsert_user(profile)

    # Store Auth0 refresh token for later verification
    auth0_refresh_token = tokens.get("refresh_token")
    if auth0_refresh_token:
        await user_repository.update_auth0_refresh_token(user.id, auth0_refresh_token)
        logger.info("Stored Auth0 refresh token for user %s", user.id)

    session_token = create_session_token(user.id, session.session_id)
    refresh_token = create_refresh_token(user.id)
    await session_store.mark_complete(session.session_id, session_token, refresh_token, user.id)
    return session


async def mark_session_failed_by_state(state: str, message: str) -> Optional[SessionData]:
    session = await session_store.get_by_state(state)
    if session is None:
        return None
    await session_store.mark_failed(session.session_id, message)
    return session


async def _exchange_code_for_tokens(code: str, code_verifier: str) -> Dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.auth0_client_id,
        "client_secret": settings.auth0_client_secret,
        "code": code,
        "redirect_uri": settings.auth0_callback_url,
        "code_verifier": code_verifier,
    }

    if not settings.auth0_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 secret not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{_auth0_base_url()}/oauth/token", data=payload)
        if response.status_code >= 400:
            body = response.text
            logger.error(
                "Auth0 token exchange failed: status=%s body=%s",
                response.status_code,
                body,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Auth0 token exchange failed")
        return response.json()


async def _fetch_user_profile(access_token: str) -> UserProfile:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{_auth0_base_url()}/userinfo", headers=headers)
        if response.status_code >= 400:
            logger.error("Auth0 userinfo failed: status=%s body=%s", response.status_code, response.text)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to fetch user profile")
        data = response.json()

    return UserProfile(**data)


async def refresh_session_token(refresh_token_str: str) -> tuple[str, str]:
    """Use the client-provided refresh token to get new session and refresh tokens.

    Verifies the user is still valid in Auth0 before issuing new tokens.

    Args:
        refresh_token_str: The refresh token provided by the client

    Returns:
        Tuple of (new_session_token, new_refresh_token)
    """
    # Decode and validate the refresh token
    payload = decode_refresh_token(refresh_token_str)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload"
        )

    # Verify user still exists
    user = await user_repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Verify with Auth0 using stored refresh token
    if not user.auth0_refresh_token:
        logger.warning("User %s has no Auth0 refresh token", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No Auth0 refresh token. Please login again."
        )

    logger.info("Verifying user %s with Auth0", user_id)
    auth0_tokens = await _verify_with_auth0(user.auth0_refresh_token)

    # Update stored Auth0 refresh token if rotated
    new_auth0_refresh_token = auth0_tokens.get("refresh_token")
    if new_auth0_refresh_token and new_auth0_refresh_token != user.auth0_refresh_token:
        logger.info("Auth0 refresh token rotated for user %s", user_id)
        await user_repository.update_auth0_refresh_token(user_id, new_auth0_refresh_token)

    # Generate new tokens
    new_session_id = uuid.uuid4().hex
    new_session_token = create_session_token(user_id, new_session_id)
    new_refresh_token = create_refresh_token(user_id)  # Rotate refresh token

    logger.info("Created new session token for user %s", user_id)

    return new_session_token, new_refresh_token


async def _verify_with_auth0(auth0_refresh_token: str) -> Dict[str, Any]:
    """Verify user is still valid in Auth0 by exchanging refresh token.

    If the user is blocked or deleted in Auth0, the refresh token exchange will fail.
    """
    payload = {
        "grant_type": "refresh_token",
        "client_id": settings.auth0_client_id,
        "client_secret": settings.auth0_client_secret,
        "refresh_token": auth0_refresh_token,
    }

    if not settings.auth0_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 secret not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{_auth0_base_url()}/oauth/token", data=payload)
        if response.status_code >= 400:
            logger.warning("Auth0 verification failed: status=%s body=%s", response.status_code, response.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Auth0 verification failed. User may be blocked or deleted. Please login again."
            )
        return response.json()

