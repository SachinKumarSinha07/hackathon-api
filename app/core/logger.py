"""
Logging Configuration Module

Provides a simple logging setup for the application.
"""

import logging
import sys
from typing import Optional


def setup_logging(log_level: str = "INFO") -> None:
    """Configure application logging."""
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str, log_level: Optional[str] = None) -> logging.Logger:
    """Get a logger instance."""
    logger = logging.getLogger(name)
    if log_level:
        logger.setLevel(getattr(logging, log_level.upper()))
    return logger
