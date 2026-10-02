from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth import service
from app.auth.attribution import build_activation_properties, parse_attribution_cookie
from app.auth.dependencies import get_session_token, get_current_user
from app.auth.login_success import (
    activation_transaction_id,
    render_login_success_page,
    valid_transaction_id,
)
from app.auth.schemas import SessionCreateResponse, SessionStatusResponse, RefreshTokenRequest, RefreshTokenResponse
from app.auth.session_store import SessionStatus, session_store
from app.analytics.posthog import record_user_activated
from app.users import repository as user_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
public_router = APIRouter(prefix="/auth", tags=["auth-public"])


@router.post("/session", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_auth_session() -> SessionCreateResponse:
    data = await service.create_session()
    return SessionCreateResponse(session_id=data["session_id"], login_url=data["login_url"])  # type: ignore[arg-type]


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str) -> SessionStatusResponse:
    session = await session_store.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        session_token=session.session_token if session.status is SessionStatus.COMPLETE else None,
        refresh_token=session.refresh_token if session.status is SessionStatus.COMPLETE else None,
        error=session.error,
    )


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing state")

    if error:
        message = error_description or error or "Login failed"
        await service.mark_session_failed_by_state(state, message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")

    session, is_first_login = await service.complete_auth_flow(code, state)
    response = RedirectResponse(service.get_success_page_url())
    if is_first_login:
        user_id = session.user_id or ""
        if not user_id:
            logger.warning(
                "First login completed with no user id; skipping activation side effects"
            )
            return response

        # One-time marker consumed by the login-success page to fire the
        # "Activated" conversion exactly once per account's first login.
        # The value is a per-account transaction id so Google Ads dedupes it.
        response.set_cookie(
            key="sensii_activation",
            value=activation_transaction_id(user_id),
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=True,
        )

        # Attribution and PostHog are best-effort: never fail the login redirect.
        try:
            acquisition = parse_attribution_cookie(request.cookies.get("sensii_attr"))
            if acquisition:
                await user_repository.set_acquisition(user_id, acquisition)

            if request.cookies.get("sensii_consent") == "granted":
                ph_id = acquisition.get("ph_id") if acquisition else None
                record_user_activated(
                    user_id,
                    build_activation_properties(acquisition),
                    ph_id=ph_id,
                )
        except Exception:
            logger.exception("Attribution tracking failed during first login")

    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(_: str = Depends(get_session_token)) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> RefreshTokenResponse:
    """Get new session and refresh tokens using a valid refresh token.

    This endpoint does NOT require Authorization header - only the refresh token
    in the request body. This allows clients to refresh even after the session
    token has expired (e.g., after overnight disconnect).

    The refresh token is rotated on each use for security.
    """
    new_session_token, new_refresh_token = await service.refresh_session_token(request.refresh_token)
    return RefreshTokenResponse(session_token=new_session_token, refresh_token=new_refresh_token)


@public_router.get("/login")
async def login_entry(session_id: str = Query(..., alias="session_id")) -> RedirectResponse:
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session identifier")
    authorize_url = await service.build_authorize_url(session_id)
    return RedirectResponse(authorize_url)


@public_router.get("/login-success", response_class=HTMLResponse)
async def login_success(request: Request) -> HTMLResponse:
    transaction_id = valid_transaction_id(request.cookies.get("sensii_activation"))
    response = HTMLResponse(content=render_login_success_page(transaction_id))
    if transaction_id:
        response.delete_cookie("sensii_activation")
    return response
