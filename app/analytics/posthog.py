from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        import posthog

        _client = posthog.Posthog(settings.posthog_key, host=settings.posthog_host)
    return _client


def _send_user_activated(
    distinct_id: str,
    properties: dict[str, Any],
    ph_id: Optional[str],
) -> None:
    try:
        client = _get_client()
        if ph_id and ph_id != distinct_id:
            client.alias(previous_id=ph_id, distinct_id=distinct_id)
        client.capture(event="user_activated", distinct_id=distinct_id, properties=properties)
    except Exception:  # noqa: BLE001 - must never fail the login flow
        logger.exception("PostHog user_activated event failed")


def record_user_activated(
    distinct_id: str,
    properties: dict[str, Any],
    ph_id: Optional[str] = None,
) -> None:
    """Fire-and-forget the `user_activated` PostHog event off the request path."""
    if not settings.posthog_key or not settings.posthog_host:
        return
    try:
        _get_client()  # lazy-create on the event loop so the worker sees a ready client
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _send_user_activated, distinct_id, properties, ph_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to schedule PostHog user_activated event")


def shutdown() -> None:
    """Flush and shut down the lazily created PostHog client."""
    global _client
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:  # noqa: BLE001
            logger.exception("PostHog shutdown failed")
        finally:
            _client = None
