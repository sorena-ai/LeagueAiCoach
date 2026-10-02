from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _send_user_activated(distinct_id: str, properties: dict[str, Any]) -> None:
    try:
        import posthog

        posthog.api_key = settings.posthog_key
        posthog.host = settings.posthog_host
        posthog.capture(distinct_id=distinct_id, event="user_activated", properties=properties)
    except Exception:  # noqa: BLE001 - must never fail the login flow
        logger.exception("PostHog user_activated event failed")


def record_user_activated(distinct_id: str, properties: dict[str, Any]) -> None:
    """Fire-and-forget the `user_activated` PostHog event off the request path."""
    if not settings.posthog_key or not settings.posthog_host:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _send_user_activated, distinct_id, properties)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to schedule PostHog user_activated event")
