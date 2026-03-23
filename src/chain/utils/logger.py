"""Centralized logging for the Movie Finder chain.

Three sinks per logger — all under ``logs/<timestamp>/``:

* **Console** — INFO+ by default, DEBUG when ``LOG_LEVEL=DEBUG`` is set.
* **Per-module file** — always DEBUG, path mirrors the dotted module name
  (e.g. ``chain.nodes.qa_agent`` → ``logs/<ts>/chain/nodes/qa_agent.log``).
* **Full combined log** — always DEBUG, one file for the entire run.

Usage
-----
Module-level (most nodes)::

    from chain.utils.logger import get_logger
    logger = get_logger(__name__)

Class-based (services with a ``debug`` constructor flag)::

    from chain.utils.logger import get_logger

    class MyService:
        def __init__(self, debug: bool = False):
            self.logger = get_logger(self.__class__.__name__, debug=debug)

Environment control
-------------------
Set ``LOG_LEVEL=DEBUG`` in ``chain/.env`` (or the shell) to get full
DEBUG-level output on the console without changing code.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

# One timestamp per process — all loggers in a single run share the same dir.
_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOGS_DIR = os.path.join(os.getcwd(), "logs", _TIMESTAMP)

_ENV_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_DEFAULT_LEVEL = logging.DEBUG if _ENV_LEVEL == "DEBUG" else logging.INFO

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


def get_logger(name: str, debug: bool = False) -> logging.Logger:
    """Return a logger with console + per-module file + full.log sinks.

    Parameters
    ----------
    name:
        Logger name.  Use ``__name__`` for module loggers or
        ``self.__class__.__name__`` for class-level loggers.
    debug:
        When ``True`` forces DEBUG level on the console handler regardless
        of the ``LOG_LEVEL`` env var.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    console_level = logging.DEBUG if debug else _DEFAULT_LEVEL

    # 1. Console — level controlled by env or debug flag
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(_FORMATTER)
    logger.addHandler(console)

    # 2. Per-module file — always DEBUG so nothing is ever lost
    log_path = os.path.join(LOGS_DIR, f"{name.replace('.', os.sep)}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(_FORMATTER)
    logger.addHandler(file_h)

    # 3. Full combined log — always DEBUG
    full_path = os.path.join(LOGS_DIR, "full.log")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    full_h = logging.FileHandler(full_path, encoding="utf-8")
    full_h.setLevel(logging.DEBUG)
    full_h.setFormatter(_FORMATTER)
    logger.addHandler(full_h)

    # Set the logger itself to DEBUG so file handlers always capture everything;
    # each handler's own level acts as the per-sink filter.
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # prevent double-logging through the root logger
    return logger
