from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: Optional[AsyncIOMotorClient] = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Return a singleton AsyncIOMotorClient."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """Return the configured MongoDB database."""
    client = get_mongo_client()
    return client[settings.mongodb_db_name]


def close_mongo_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
