"""Datadog logging utilities."""

from __future__ import annotations

import logging
import socket
from typing import Optional

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.logs_api import LogsApi
from datadog_api_client.v2.model.http_log import HTTPLog
from datadog_api_client.v2.model.http_log_item import HTTPLogItem

from app.config import Settings


class DatadogLogHandler(logging.Handler):
    """Custom logging handler that ships records to Datadog Logs."""

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

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            payload = HTTPLog(
                [
                    HTTPLogItem(
                        ddsource="python",
                        ddtags=f"{self._ddtags},logger:{record.name}",
                        hostname=self._hostname,
                        message=message,
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


def build_datadog_handler(settings: Settings) -> Optional[logging.Handler]:
    """Factory helper that only creates the handler when inputs are valid."""

    if not settings.datadog_logs_enabled:
        return None

    if not settings.datadog_api_key or not settings.datadog_app_key:
        raise ValueError("Datadog logging enabled but API or APP key is missing.")

    return DatadogLogHandler(settings)
