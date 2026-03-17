"""Logging configuration for the application."""

import logging
import sys

from luca.utils.config import get_settings


def setup_logging() -> logging.Logger:
    """Configure and return the application logger."""
    settings = get_settings()

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger = logging.getLogger("luca")
    logger.setLevel(settings.log_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(f"luca.{name}")
