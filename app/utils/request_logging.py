"""
Request logging middleware.

Assigns each request an id, binds the basics to the logging context, and logs a
single completion line carrying status and duration.

Deliberately a raw ASGI middleware rather than a ``BaseHTTPMiddleware``.
BaseHTTPMiddleware runs the downstream app in a separate anyio task, so
ContextVar values bound *inside* the request - the authenticated user, the
champion - would not be visible here afterwards, and the completion line would
be the one log entry missing the user. Calling the app directly keeps
everything in one task, and leaves StreamingResponse untouched.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.utils.log_context import bind_log_context, elapsed_ms, get_log_context, reset_log_context

logger = logging.getLogger(__name__)

# Probed constantly by the load balancer; logging them buries everything else.
QUIET_PATHS = frozenset({"/api/v1/health", "/api/v1/ready"})


class RequestContextMiddleware:
    """Bind per-request logging context and log request completion."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        reset_log_context()

        path = scope.get("path", "")
        request_id = _incoming_request_id(scope) or uuid4().hex[:12]
        bind_log_context(
            request_id=request_id,
            http_method=scope.get("method"),
            http_path=path,
            client_ip=_client_ip(scope),
        )

        quiet = path in QUIET_PATHS
        started = time.perf_counter()
        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append(
                    (b"x-request-id", request_id.encode("latin-1", "ignore"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            bind_log_context(duration_ms=elapsed_ms(started))
            # The user context bound downstream is still here, so this line
            # says who the failure happened to.
            logger.exception(
                "Request failed - %s %s after %.0f ms",
                scope.get("method"),
                path,
                elapsed_ms(started),
            )
            raise

        duration_ms = elapsed_ms(started)
        bind_log_context(status_code=status_code, duration_ms=duration_ms)

        if not quiet:
            logger.info(
                "Request completed - %s %s -> %s in %.0f ms",
                scope.get("method"),
                path,
                status_code,
                duration_ms,
            )

    @staticmethod
    def current_request_id() -> str | None:
        """The id of the request being handled, if any."""
        return get_log_context().get("request_id")


def _incoming_request_id(scope) -> str | None:
    """Reuse an upstream request id (traefik, a client retry) when present."""
    for name, value in scope.get("headers", ()):
        if name == b"x-request-id":
            return value.decode("latin-1", "ignore")[:64] or None
    return None


def _client_ip(scope) -> str | None:
    """Prefer the forwarded client over the proxy's own address."""
    for name, value in scope.get("headers", ()):
        if name == b"x-forwarded-for":
            forwarded = value.decode("latin-1", "ignore").split(",")[0].strip()
            if forwarded:
                return forwarded
    client = scope.get("client")
    return client[0] if client else None
