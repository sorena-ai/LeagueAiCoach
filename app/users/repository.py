from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument

from app.core.mongodb import get_database
from app.users.models import User, UserProfile


def _get_collection() -> AsyncIOMotorCollection:
    db = get_database()
    return db["users"]


async def upsert_user(profile: UserProfile) -> User:
    now = datetime.now(timezone.utc)
    collection = _get_collection()
    update = {
        "$set": {
            "email": profile.email,
            "displayName": profile.name or profile.nickname,
            "pictureUrl": profile.picture,
            "updatedAt": now,
            "lastLoginAt": now,
        },
        "$setOnInsert": {
            "createdAt": now,
        },
    }
    document = await collection.find_one_and_update(
        {"_id": profile.sub},
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return User(**document)


async def get_user_by_id(user_id: str) -> Optional[User]:
    collection = _get_collection()
    document = await collection.find_one({"_id": user_id})
    if not document:
        return None
    return User(**document)


async def update_auth0_refresh_token(user_id: str, auth0_refresh_token: str) -> Optional[User]:
    """Update the Auth0 refresh token for a user."""
    collection = _get_collection()
    document = await collection.find_one_and_update(
        {"_id": user_id},
        {"$set": {"auth0RefreshToken": auth0_refresh_token, "updatedAt": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        return None
    return User(**document)

