"""
Logging setup for the Telegram Auto-Forwarding Bot.
Provides a consistent logging configuration across all modules.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "bot.log"


def setup_logging(level: int = logging.WARNING) -> logging.Logger:
    """
    Configure and return the root logger with both console and file handlers.

    Args:
        level: Logging level (default: INFO)

    Returns:
        Configured root logger instance
    """
    logger = logging.getLogger("telegram_bot")
    logger.setLevel(level)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    # --- Formatters ---
    console_fmt = logging.Formatter(
        "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    file_fmt = logging.Formatter(
        "%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(filename)s:%(lineno)d │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # --- File Handler (rotating: 5 MB max, keep 3 backups) ---
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.WARNING)  # Keep warnings in log file for debugging
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger


# Convenience function to get a module-specific logger
def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific module."""
    return logging.getLogger(f"telegram_bot.{name}")
