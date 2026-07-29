"""Structured operational logging without product audit persistence."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    """Emit compact JSON records suitable for container log collection."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Configure the application logger once without altering root handlers."""

    logger = logging.getLogger("january")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
