from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth import service
from app.auth.dependencies import get_session_token, get_current_user
from app.auth.login_success import render_login_success_page
from app.auth.schemas import SessionCreateResponse, SessionStatusResponse, RefreshTokenRequest, RefreshTokenResponse
from app.auth.session_store import SessionStatus, session_store

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
        # One-time marker consumed by the login-success page to fire the
        # "Activated" conversion exactly once per account's first login.
        response.set_cookie(
            key="sensii_activation",
            value="1",
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=True,
        )
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
    fire_conversion = request.cookies.get("sensii_activation") == "1"
    response = HTMLResponse(content=render_login_success_page(fire_conversion))
    if fire_conversion:
        response.delete_cookie("sensii_activation")
    return response
