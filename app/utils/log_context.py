"""
Request-scoped logging context.

Binds identity and request metadata to a ContextVar so every log record emitted
while handling a request carries it, without threading arguments through every
function call. Anything bound here reaches two places:

- the console line, as a compact ``[key=value ...]`` suffix
- Datadog, as structured attributes (see :mod:`app.utils.datadog_logging`)

Bind with :func:`bind_log_context` as soon as a fact is known - the
authenticated user in the auth dependency, the champion once a session is
resolved - and every subsequent log line in that request picks it up.
"""

from __future__ import annotations

import contextvars
import logging
import time
from typing import Any, Dict, Optional

_log_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "log_context", default=None
)

# Keys rendered onto the console line, in this order. Everything bound is still
# shipped to Datadog in full; this list only keeps stdout readable.
CONSOLE_KEYS = (
    "request_id",
    "user_email",
    "mode",
    "champion",
    "match_id",
)

# Datadog reserves usr.* for user identity, which makes it searchable as
# @usr.email and surfaces in the UI. Map our names onto it.
USER_KEYS = {
    "user_id": "id",
    "user_email": "email",
    "user_name": "name",
}


def get_log_context() -> Dict[str, Any]:
    """Return a copy of the context bound to the current request."""
    return dict(_log_context.get() or {})


def bind_log_context(**fields: Any) -> None:
    """
    Merge fields into the current request's logging context.

    ``None`` values are skipped, so callers can pass optional fields
    unconditionally without blanking a value that is already bound.
    """
    context = dict(_log_context.get() or {})
    context.update({key: value for key, value in fields.items() if value is not None})
    _log_context.set(context)


def reset_log_context() -> None:
    """Drop everything bound to the current context."""
    _log_context.set({})


def elapsed_ms(started: float) -> float:
    """Milliseconds since a ``time.perf_counter()`` reading, rounded to 0.1ms."""
    return round((time.perf_counter() - started) * 1000, 1)


class LogContextFilter(logging.Filter):
    """
    Attach the bound context to every record passing through a handler.

    This must sit on the handler that *enqueues* records rather than on the one
    that ships them: the context lives in the request's task, so it has to be
    captured before a record crosses a thread boundary.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_log_context()
        record.log_context = context
        parts = [
            f"{key}={context[key]}"
            for key in CONSOLE_KEYS
            if context.get(key) is not None
        ]
        record.context_suffix = f" [{' '.join(parts)}]" if parts else ""
        return True


class ContextFormatter(logging.Formatter):
    """Formatter that appends the context suffix to the rendered line."""

    def format(self, record: logging.LogRecord) -> str:
        # getattr keeps records that never passed through LogContextFilter
        # (uvicorn installs handlers of its own) from breaking formatting.
        return f"{super().format(record)}{getattr(record, 'context_suffix', '')}"
