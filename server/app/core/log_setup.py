"""ReelMind centralized logging configuration.

Provides rotating file handlers + console output,
with separate channels for API access, errors, and worker logs.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Literal

# ── Log format ──────────────────────────────────────────────────────────

_FILE_FORMAT = (
    "[%(asctime)s] %(levelname)-7s | %(name)-36s | %(process)d | "
    "%(filename)s:%(lineno)d | %(message)s"
)
_CONSOLE_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)
_ACCESS_FORMAT = (
    "[%(asctime)s] %(levelname)-7s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _file_formatter() -> logging.Formatter:
    return logging.Formatter(_FILE_FORMAT, _DATE_FORMAT)


def _console_formatter() -> logging.Formatter:
    return logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT)


def _access_formatter() -> logging.Formatter:
    return logging.Formatter(_ACCESS_FORMAT, _DATE_FORMAT)


# ── Named loggers ───────────────────────────────────────────────────────

LOGGER_NAMES = {
    "reelmind": "ReelMind application logger",
    "reelmind.api": "API route handlers",
    "reelmind.worker": "Celery background tasks",
    "reelmind.core": "Core services (indexer, scanner, transcoder)",
    "reelmind.ml": "ML models (CLIP, Whisper, scene detection)",
    "reelmind.auth": "Authentication & authorization",
    "reelmind.access": "HTTP access log",
}


def setup_logging(
    *,
    log_dir: str | Path = "/data/reelmind/logs",
    level: str | int = logging.INFO,
    log_max_bytes: int = 50 * 1024 * 1024,    # 50 MB per file
    log_backup_count: int = 14,                # keep 14 files = ~700 MB max
    enable_console: bool = True,
    enable_access_log: bool = True,
) -> None:
    """Configure all loggers once at application startup.

    Creates:
      - reelmind.log       — everything at configured level
      - error.log          — ERROR+ from all reelmind.* loggers
      - access.log         — HTTP request/response entries
      - stdout             — console output (docker-friendly)
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # let handlers decide filtering

    # ── Clear existing handlers (safe for re-init) ──────────────────
    root_logger.handlers.clear()

    # ── Console handler ─────────────────────────────────────────────
    if enable_console:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(_resolve_level(level))
        console.setFormatter(_console_formatter())
        root_logger.addHandler(console)

    # ── Rotating file: reelmind.log ─────────────────────────────────
    main_handler = logging.handlers.RotatingFileHandler(
        log_path / "reelmind.log",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    main_handler.setLevel(_resolve_level(level))
    main_handler.setFormatter(_file_formatter())
    root_logger.addHandler(main_handler)

    # ── Rotating file: error.log (ERROR+) ──────────────────────────
    err_handler = logging.handlers.RotatingFileHandler(
        log_path / "error.log",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(_file_formatter())
    root_logger.addHandler(err_handler)

    # ── Access log ──────────────────────────────────────────────────
    if enable_access_log:
        access_logger = logging.getLogger("reelmind.access")
        access_logger.setLevel(logging.INFO)
        access_logger.handlers.clear()
        access_handler = logging.handlers.RotatingFileHandler(
            log_path / "access.log",
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
            encoding="utf-8",
        )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(_access_formatter())
        access_logger.addHandler(access_handler)
        # Also send access logs to console if DEBUG
        if _resolve_level(level) <= logging.DEBUG:
            access_logger.addHandler(console)
        access_logger.propagate = False

    # ── Suppress noisy third-party loggers ──────────────────────────
    _set_level("sqlalchemy.engine", logging.WARNING)
    _set_level("asyncio", logging.WARNING)
    _set_level("urllib3", logging.WARNING)
    _set_level("httpx", logging.WARNING)
    _set_level("watchfiles", logging.WARNING)
    _set_level("PIL", logging.WARNING)

    # Log startup banner
    logger = logging.getLogger("reelmind")
    logger.info("─" * 60)
    logger.info("Logging initialised —  level=%-7s  dir=%s", level, log_path)
    logger.info("─" * 60)


def setup_worker_logging(
    *,
    log_dir: str | Path = "/data/reelmind/logs",
    level: str | int = logging.INFO,
    log_max_bytes: int = 50 * 1024 * 1024,
    log_backup_count: int = 14,
) -> None:
    """Configure logging for the Celery worker process.

    Uses the same file handlers as the server but without access.log.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(_resolve_level(level))
    console.setFormatter(_console_formatter())
    logger.addHandler(console)

    # File (same reelmind.log as server)
    fh = logging.handlers.RotatingFileHandler(
        log_path / "reelmind.log",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    fh.setLevel(_resolve_level(level))
    fh.setFormatter(_file_formatter())
    logger.addHandler(fh)

    # Error
    eh = logging.handlers.RotatingFileHandler(
        log_path / "error.log",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(_file_formatter())
    logger.addHandler(eh)

    _set_level("sqlalchemy.engine", logging.WARNING)
    _set_level("asyncio", logging.WARNING)


def _resolve_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, level.upper(), logging.INFO)


def _set_level(name: str, level: int) -> None:
    lgr = logging.getLogger(name)
    lgr.setLevel(level)
    lgr.handlers.clear()


def get_logger(name: str) -> logging.Logger:
    """Shortcut: get a ``reelmind.*`` child logger."""
    return logging.getLogger(f"reelmind.{name}")


# ── FastAPI access-log middleware ───────────────────────────────────────

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration = time.perf_counter() - start
            access_logger = logging.getLogger("reelmind.access")
            access_logger.error(
                "%s %s → 500 (%.3fs) — %s: %s",
                request.method,
                request.url.path,
                duration,
                type(exc).__name__,
                exc,
            )
            raise

        duration = time.perf_counter() - start
        access_logger = logging.getLogger("reelmind.access")

        # Log based on status code
        status = response.status_code
        if 200 <= status < 400:
            access_logger.info(
                "%s %s → %d (%.3fs)",
                request.method,
                request.url.path,
                status,
                duration,
            )
        elif 400 <= status < 500:
            access_logger.warning(
                "%s %s → %d (%.3fs)",
                request.method,
                request.url.path,
                status,
                duration,
            )
        else:
            access_logger.error(
                "%s %s → %d (%.3fs)",
                request.method,
                request.url.path,
                status,
                duration,
            )

        return response
