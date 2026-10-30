"""
Basic structured-ish logging configuration.

Kept intentionally simple for Milestone 1. Future milestones may replace this
with structured JSON logging if operational needs require it.
"""
import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Avoid duplicate handlers on reload
    if root_logger.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
