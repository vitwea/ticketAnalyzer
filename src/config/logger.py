"""
Provides a professional logging setup for the entire project.

Features:
- Console output (human‑readable) and file output (persistent).
- Log rotation to prevent oversized log files.
- Log level configurable via the LOG_LEVEL environment variable.

Usage:
    from config.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Processing ticket %s", ticket_id)
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.config.settings import settings

_CONFIGURED = False


def _configure_root_logger() -> None:
    """
    Configure the root logger once per application run.
    Creates both console and rotating file handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Ensure log directory exists
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / "app.log"

    # Log message format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger instance configured for the given module name.
    Ensures the root logger is initialized before use.
    """
    _configure_root_logger()
    return logging.getLogger(name)
