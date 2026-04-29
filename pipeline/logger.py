"""Shared logger for all pipeline modules. Writes to stdout + logs/pipeline.log."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config.settings import LOG_LEVEL, LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(LOG_LEVEL)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    file = RotatingFileHandler(
        LOGS_DIR / "pipeline.log", maxBytes=2_000_000, backupCount=3
    )
    file.setFormatter(fmt)
    logger.addHandler(file)
    return logger
