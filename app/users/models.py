from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class User(BaseModel):
    id: str = Field(alias="_id")
    email: Optional[str] = None
    display_name: Optional[str] = Field(default=None, alias="displayName")
    picture_url: Optional[str] = Field(default=None, alias="pictureUrl")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_login_at: Optional[datetime] = Field(default=None, alias="lastLoginAt")
    auth0_refresh_token: Optional[str] = Field(default=None, alias="auth0RefreshToken")

    model_config = ConfigDict(
        populate_by_name=True,
    )


class UserProfile(BaseModel):
    sub: str
    email: Optional[str] = None
    name: Optional[str] = None
    nickname: Optional[str] = None
    picture: Optional[str] = None

    model_config = ConfigDict(extra="ignore")
