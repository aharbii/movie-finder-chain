"""Tests for logger utilities."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

from chain.utils.logger import _JsonFormatter, configure_logging, get_logger


def test_get_logger() -> None:
    logger = get_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_json_formatter() -> None:
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Test message"
    assert "timestamp" in data
    assert "exception" not in data


def test_json_formatter_with_exception() -> None:
    formatter = _JsonFormatter()

    try:
        raise ValueError("Test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg="Error occurred",
        args=(),
        exc_info=exc_info,
    )

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "ERROR"
    assert data["message"] == "Error occurred"
    assert "exception" in data
    assert "Test error" in data["exception"]


@patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "LOG_FORMAT": "json"}, clear=True)
def test_configure_logging_json() -> None:
    # Clear existing handlers
    logging.getLogger("chain").handlers.clear()
    logging.getLogger("imdbapi").handlers.clear()

    configure_logging()

    logger = logging.getLogger("chain")
    assert logger.level == logging.DEBUG
    assert not logger.propagate
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, _JsonFormatter)

    # Test quiet libs
    assert logging.getLogger("httpx").level == logging.DEBUG

    # Test idempotency
    configure_logging()
    assert len(logger.handlers) == 1


@patch.dict(os.environ, {"LOG_LEVEL": "WARNING", "LOG_FORMAT": "text"}, clear=True)
def test_configure_logging_text() -> None:
    # Clear existing handlers
    logging.getLogger("chain").handlers.clear()
    logging.getLogger("imdbapi").handlers.clear()

    configure_logging()

    logger = logging.getLogger("chain")
    assert logger.level == logging.WARNING
    assert len(logger.handlers) == 1
    assert not isinstance(logger.handlers[0].formatter, _JsonFormatter)

    # Test quiet libs
    assert logging.getLogger("httpx").level == logging.WARNING
