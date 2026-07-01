"""ReelMind AI Service — rotating log file setup (standalone, no server dependency).

Writes to /data/reelmind/logs/reelmind-ai.log + error.log
with the same format as the server, so log_service can find them.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

LOG_DIR = "/data/reelmind/logs"
LOG_MAX_BYTES = 50 * 1024 * 1024   # 50 MB
LOG_BACKUP_COUNT = 14               # ~700 MB max
LOG_LEVEL = os.environ.get("AI_LOG_LEVEL", "INFO").upper()

_FILE_FORMAT = (
    "[%(asctime)s] %(levelname)-7s | %(name)-36s | %(process)d | "
    "%(filename)s:%(lineno)d | %(message)s"
)
_CONSOLE_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(service: str = "ai") -> None:
    """Configure rotating file + console logging for an AI-side service.

    Args:
        service: Short name used in filenames (e.g. "ai", "orchestrator").
    """
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    level = getattr(logging, LOG_LEVEL, logging.INFO)

    # Console (always — Docker expects stdout)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    root.addHandler(console)

    # Main rotating file
    main_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"reelmind-{service}.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    main_handler.setLevel(level)
    main_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))
    root.addHandler(main_handler)

    # Error-only rotating file
    err_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"reelmind-{service}-error.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))
    root.addHandler(err_handler)

    # Suppress noisy libs
    for noisy in ("asyncio", "urllib3", "httpx", "PIL", "watchfiles"):
        l = logging.getLogger(noisy)
        l.setLevel(logging.WARNING)
        l.handlers.clear()

    logger = logging.getLogger(f"reelmind.{service}")
    logger.info("─" * 60)
    logger.info("Logging initialised — service=%-10s level=%-7s dir=%s", service, LOG_LEVEL, log_dir)
    logger.info("─" * 60)
