from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_ATTRIBUTION_KEYS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "gclid",
    "landing_path",
    "ts",
    "ph_id",
)
_MAX_VALUE_LENGTH = 200


def parse_attribution_cookie(raw: Optional[str]) -> Optional[dict[str, str]]:
    """Parse the `sensii_attr` cookie value into a sanitized attribution dict.

    The landing writes the cookie as URL-encoded JSON. The server receives it
    already URL-decoded by Starlette, but we tolerate a still-encoded value.
    Malformed or unexpected input yields `None`.
    """
    if not raw:
        return None

    decoded: Any = None
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            decoded = json.loads(unquote(raw))
        except (json.JSONDecodeError, TypeError):
            logger.info("Ignoring malformed sensii_attr cookie")
            return None

    if not isinstance(decoded, dict):
        return None

    result: dict[str, str] = {}
    for key in _ATTRIBUTION_KEYS:
        value = decoded.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            continue
        result[key] = value[:_MAX_VALUE_LENGTH]

    return result or None


def build_signup_properties(acquisition: Optional[dict[str, str]]) -> dict[str, Any]:
    """Shape acquisition data for the PostHog `user_signed_up` event."""
    if not acquisition:
        acquisition = {}
    properties: dict[str, Any] = {}
    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
        if key in acquisition:
            properties[key] = acquisition[key]
    properties["gclid"] = "gclid" in acquisition
    if "landing_path" in acquisition:
        properties["landing_path"] = acquisition["landing_path"]
    return properties
