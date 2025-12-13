from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.auth.session_store import SessionStatus


class SessionCreateResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    login_url: str = Field(..., alias="loginUrl")

    model_config = ConfigDict(populate_by_name=True)


class SessionStatusResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    status: SessionStatus
    session_token: Optional[str] = Field(None, alias="sessionToken")
    refresh_token: Optional[str] = Field(None, alias="refreshToken")
    error: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class RefreshTokenResponse(BaseModel):
    session_token: str = Field(..., alias="sessionToken")
    refresh_token: str = Field(..., alias="refreshToken")  # New refresh token (rotation)

    model_config = ConfigDict(populate_by_name=True)

