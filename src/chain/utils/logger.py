"""Logging configuration for the chain library."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def _setup_logging() -> None:
    """Configure the root logger for the chain package.

    Uses a standardized format and sets the level from ChainConfig (via environment).
    """
    from chain.config import get_config

    cfg = get_config()
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger("chain")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False  # Avoid double-logging if root is also configured


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance for the given name.

    Args:
        name: The name of the logger (usually __name__).

    Returns:
        A configured logging.Logger instance.
    """
    _setup_logging()
    if not name.startswith("chain.") and name != "chain":
        # Ensure it's part of the chain hierarchy
        return logging.getLogger(f"chain.{name}")
    return logging.getLogger(name)
