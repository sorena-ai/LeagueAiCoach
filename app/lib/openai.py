from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Return a process-wide AsyncOpenAI client.

    The client holds an httpx connection pool. One instance per process reuses
    those connections across transcription and speech synthesis.
    """
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def close_openai_client() -> None:
    """Close the shared client. Safe to call when it was never created."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
