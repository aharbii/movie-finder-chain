"""Logging utilities for the chain package.

Library code calls ``logging.getLogger(__name__)`` directly — it never
configures the logging system.  Configuration is the responsibility of the
entry point (FastAPI app via ``app.logging_config.configure_logging``,
standalone examples, or test suites).

``get_logger`` is a thin backward-compatible shim.  New code should call
``logging.getLogger(__name__)`` directly.

``configure_logging`` is provided for standalone chain usage (examples,
one-off scripts) where the FastAPI app bootstrap is not present.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger for the given name.

    Thin wrapper around ``logging.getLogger`` kept for backward compatibility.
    New callers may use ``logging.getLogger(__name__)`` directly.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A ``logging.Logger`` instance.
    """
    return logging.getLogger(name)


class _JsonFormatter(logging.Formatter):
    """JSON formatter for structured log output."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a single-line JSON string.

        Args:
            record: The log record to format.

        Returns:
            A JSON-encoded log entry string.
        """
        data: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def configure_logging() -> None:
    """Bootstrap logging for standalone chain usage (examples, scripts).

    Reads ``LOG_LEVEL`` (default ``INFO``) and ``LOG_FORMAT`` (default ``text``)
    from the environment.  Idempotent — safe to call multiple times.

    The FastAPI app calls ``app.logging_config.configure_logging`` instead;
    this function is for standalone chain scripts and examples only.
    """
    if logging.getLogger("chain").handlers:
        return  # already configured

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_format = os.environ.get("LOG_FORMAT", "text").lower()
    level: int = getattr(logging, level_name, logging.INFO)

    if log_format == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    for namespace in ("chain", "imdbapi"):
        ns_logger = logging.getLogger(namespace)
        ns_logger.setLevel(level)
        ns_logger.addHandler(handler)
        ns_logger.propagate = False

    _quiet_libs = ("httpx", "httpcore", "openai", "anthropic")
    quiet_level = logging.DEBUG if level == logging.DEBUG else logging.WARNING
    for lib in _quiet_libs:
        logging.getLogger(lib).setLevel(quiet_level)
