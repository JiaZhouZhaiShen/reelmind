"""In-memory cache of SystemSetting DB table.

Populated on server startup, reloaded after admin writes.
Consumers (transcoder, indexer, scanner, etc.) read synchronously
from this cache -- no DB call at read time.
"""

from __future__ import annotations

import logging

from ..config import settings

logger = logging.getLogger(__name__)


_DEFAULT_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".m4v", ".wmv", ".flv", ".ts", ".mts",
    ".m2ts", ".3gp", ".ogv", ".mxf",
}

_cache: dict[str, str] = {}


async def load_all(session=None) -> None:
    """Load all SystemSetting rows into the in-memory cache."""
    global _cache
    from ..models.system_settings import SystemSetting
    from sqlalchemy import select
    if session is None:
        from ..database import async_session_factory
        async with async_session_factory() as s:
            rows = (await s.execute(select(SystemSetting))).scalars().all()
    else:
        rows = (await session.execute(select(SystemSetting))).scalars().all()
    _cache = {r.key: r.value for r in rows if r.value is not None}
    logger.info("Loaded %d system settings into cache", len(_cache))


async def reload_all(session) -> None:
    """Reload cache after admin writes (uses same session for consistency)."""
    await load_all(session)


def get_str(key: str, default: str = "") -> str:
    """Get a string setting from cache."""
    return _cache.get(key, default)


def get_int(key: str, default: int) -> int:
    """Get an integer setting from cache."""
    raw = _cache.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def get_float(key: str, default: float) -> float:
    """Get a float setting from cache."""
    raw = _cache.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def get_csv(key: str, default: list[str] | None = None) -> list[str]:
    """Parse a comma-separated setting. Returns [] if not set."""
    raw = _cache.get(key)
    if not raw:
        return default or []
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_video_extensions() -> set[str]:
    """Get supported video extensions from cache, falling back to config."""
    raw = _cache.get("supported_video_extensions", "")
    if raw:
        return {x.strip() for x in raw.split(",") if x.strip()}
    return getattr(settings, "SUPPORTED_VIDEO_EXTENSIONS", _DEFAULT_VIDEO_EXTENSIONS)
