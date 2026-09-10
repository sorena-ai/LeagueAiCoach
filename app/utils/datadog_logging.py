"""Datadog logging utilities."""

from __future__ import annotations

import json
import logging
import queue
import socket
from logging.handlers import QueueHandler, QueueListener
from typing import Any, Dict, Optional

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.logs_api import LogsApi
from datadog_api_client.v2.model.http_log import HTTPLog
from datadog_api_client.v2.model.http_log_item import HTTPLogItem

from app.config import Settings
from app.utils.log_context import USER_KEYS

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Set by _build_message; never overwritten by request context.
_RESERVED_ATTRIBUTES = {"message", "logger", "usr", "error"}


class DatadogLogHandler(logging.Handler):
    """
    Custom logging handler that ships records to Datadog Logs.

    Records are sent as a JSON message, which Datadog parses into structured
    attributes - so the request context bound via
    :mod:`app.utils.log_context` becomes searchable (``@usr.email``,
    ``@champion``, ``@duration_ms``) instead of being buried in a text line.

    ``submit_log`` is a blocking HTTP call, so this handler is meant to run
    behind a queue on a background thread; see :func:`build_datadog_handler`.
    """

    def __init__(self, settings: Settings):
        level = getattr(logging, settings.datadog_log_level.upper(), logging.INFO)
        super().__init__(level=level)

        if not settings.datadog_api_key or not settings.datadog_app_key:
            raise ValueError("Datadog API and APP keys are required when logs are enabled.")

        configuration = Configuration()
        configuration.server_variables["site"] = settings.datadog_site
        configuration.api_key = {
            "apiKeyAuth": settings.datadog_api_key,
            "appKeyAuth": settings.datadog_app_key,
        }

        self._client = ApiClient(configuration)
        self._api = LogsApi(self._client)
        self._service = settings.datadog_service
        self._env = settings.datadog_env
        self._version = settings.datadog_version
        self._hostname = self._resolve_hostname()
        self._ddtags = f"service:{self._service},env:{self._env},version:{self._version}"

    @staticmethod
    def _resolve_hostname() -> str:
        hostname = socket.gethostname()
        return hostname or "sensei"

    def _build_message(self, record: logging.LogRecord) -> str:
        """Render the record as JSON so Datadog indexes it as attributes."""
        context: Dict[str, Any] = dict(getattr(record, "log_context", None) or {})

        body: Dict[str, Any] = {
            "message": self.format(record),
            "logger": {"name": record.name},
        }

        user = {}
        for source, target in USER_KEYS.items():
            value = context.pop(source, None)
            if value is not None:
                user[target] = value
        if user:
            body["usr"] = user

        stack = getattr(record, "error_stack", None)
        if stack:
            body["error"] = {"stack": stack, "kind": getattr(record, "error_kind", None)}

        for key, value in context.items():
            if key not in _RESERVED_ATTRIBUTES:
                body[key] = value

        try:
            return json.dumps(body, default=str)
        except (TypeError, ValueError):
            # Never lose a line because one attribute would not serialize.
            return self.format(record)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = HTTPLog(
                [
                    HTTPLogItem(
                        ddsource="python",
                        ddtags=f"{self._ddtags},logger:{record.name}",
                        hostname=self._hostname,
                        message=self._build_message(record),
                        service=self._service,
                        status=record.levelname.lower(),
                    )
                ]
            )
            self._api.submit_log(body=payload)
        except Exception:  # pragma: no cover - never raise log handler errors
            self.handleError(record)

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            super().close()


class ContextQueueHandler(QueueHandler):
    """
    Queue handler that preserves what the Datadog handler needs.

    ``QueueHandler.prepare`` clears ``exc_info`` once it has folded the
    traceback into the message text, so the stack is captured here first and
    carried across as an attribute for Datadog error tracking.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        exc_info = record.exc_info
        stack = kind = None
        if exc_info and exc_info[0] is not None:
            stack = logging.Formatter().formatException(exc_info)
            kind = exc_info[0].__name__

        prepared = super().prepare(record)

        if stack:
            prepared.error_stack = stack
            prepared.error_kind = kind
        return prepared


def build_datadog_handler(settings: Settings) -> Optional[logging.Handler]:
    """
    Factory helper that only creates the handler when inputs are valid.

    Returns a queue handler fronting the real one. Shipping a log record is a
    blocking HTTPS round trip, and doing that inline meant every log call
    stalled the event loop mid-request; the listener drains the queue on its
    own thread instead.
    """

    if not settings.datadog_logs_enabled:
        return None

    if not settings.datadog_api_key or not settings.datadog_app_key:
        raise ValueError("Datadog logging enabled but API or APP key is missing.")

    target = DatadogLogHandler(settings)
    target.setFormatter(logging.Formatter(LOG_FORMAT))

    listener = QueueListener(queue.SimpleQueue(), target, respect_handler_level=True)
    listener.start()  # runs on a daemon thread

    handler = ContextQueueHandler(listener.queue)
    handler.setLevel(target.level)
    # Exposed so the application can flush and stop the thread on shutdown.
    handler.listener = listener
    return handler


def shutdown_datadog_handler(handler: Optional[logging.Handler]) -> None:
    """Flush queued records and stop the background listener."""
    listener = getattr(handler, "listener", None)
    if listener is None:
        return
    try:
        listener.stop()
    except Exception:  # pragma: no cover - shutdown must not raise
        logging.getLogger(__name__).debug("Datadog log listener failed to stop cleanly")
