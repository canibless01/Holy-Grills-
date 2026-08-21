"""
app/utils/logger.py — Structured logging for Holy Grills backend.

All modules should import the logger from here instead of using print().

Usage:
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Order created", extra={"order_id": order_id, "user_id": user_id})
    logger.error("Payment failed", extra={"reference": ref, "error": str(e)})

Log format:
    [LEVEL] YYYY-MM-DD HH:MM:SS | module.name | message | key=value ...
"""

import logging
import sys
from typing import Any


LOG_FORMAT = "[%(levelname)s] %(asctime)s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ExtraFormatter(logging.Formatter):
    """Custom formatter that renders extra={...} attributes if present."""
    RESERVED_ATTRS = {
        'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
        'funcName', 'levelname', 'levelno', 'lineno', 'module', 'msecs',
        'message', 'msg', 'name', 'pathname', 'process', 'processName',
        'relativeCreated', 'stack_info', 'thread', 'threadName'
    }

    def format(self, record: logging.LogRecord) -> str:
        standard_msg = super().format(record)
        extra_items = {k: v for k, v in record.__dict__.items() if k not in self.RESERVED_ATTRS}
        if extra_items:
            extra_str = " | " + " ".join(f"{k}={v!r}" for k, v in extra_items.items())
            return standard_msg + extra_str
        return standard_msg


def _configure_root_logger(level: int = logging.INFO) -> None:
    """Configure the root logger once at app startup."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ExtraFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger. Call at module level:
        logger = get_logger(__name__)
    """
    _configure_root_logger()
    return logging.getLogger(name)


def format_extra(extra: dict[str, Any]) -> str:
    """Render extra context as key=value pairs suitable for appending to a log line."""
    return " | " + " ".join(f"{k}={v!r}" for k, v in extra.items()) if extra else ""
