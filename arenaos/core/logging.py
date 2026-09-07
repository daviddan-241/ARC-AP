"""Logging setup with a global secret-redaction filter on every record."""
from __future__ import annotations

import logging
import sys
from typing import Optional

from arenaos.core.security import redact


class RedactingFilter(logging.Filter):
    """Applies secret redaction to every log message and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage():
            record.msg = redact(str(record.msg))
            record.args = ()
        if record.exc_info:
            etype, value, tb = record.exc_info
            if isinstance(value, Exception) and str(value):
                record.exc_info = (etype, type(value)(redact(str(value))), tb)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging: single stderr handler, JSON-free, fully redacted."""
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """Return a configured logger (redaction inherited from root handlers)."""
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
