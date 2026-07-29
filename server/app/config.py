"""ReelMind configuration - loaded from environment / .env file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "ReelMind"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # --- Database (PostgreSQL with pgvector) ---
    DB_DRIVER: str = "postgresql+asyncpg"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = "reelmind"
    DB_POOL_SIZE: int = 10
    DB_POOL_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"{self.DB_DRIVER}://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # --- Redis ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # --- Storage ---
    DATA_ROOT: Path = Path.home() / ".reelmind"
    MEDIA_ROOT: Path = Path.home() / ".reelmind" / "media"
    CACHE_ROOT: Path = Path.home() / ".reelmind" / "cache"
    MODEL_ROOT: Path = Path.home() / ".reelmind" / "models"

    MIN_FREE_SPACE_GB: int = 10

    # --- Video Processing ---
    THUMBNAIL_SIZE: tuple[int, int] = (480, 270)
    THUMBNAIL_QUALITY: int = 85
    PROXY_VIDEO_BITRATE: str = "2M"
    PROXY_VIDEO_MAX_WIDTH: int = 1280

    # --- AI / ML ---
    WHISPER_MODEL: str = "base"
    CLIP_MODEL: str = "ViT-B/32"
    ENABLE_WHISPER: bool = False
    ENABLE_CLIP: bool = False
    ENABLE_FACE_DETECT: bool = False

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 2588

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "/data/reelmind/logs"
    LOG_MAX_BYTES: int = 52428800
    LOG_BACKUP_COUNT: int = 14
    ENABLE_ACCESS_LOG: bool = True

    # --- External paths ---
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"
    ENABLE_HW_ACCEL: bool = False
    HW_ACCEL_DEVICE: str = "/dev/dri/renderD128"

    # --- API ---
    CORS_ORIGINS: list[str] = ["*"]
    API_PREFIX: str = "/api"

    # --- External Library scanning ---
    SCAN_INTERVAL_SECONDS: int = 300
    SCAN_BATCH_SIZE: int = 100
    SUPPORTED_VIDEO_EXTENSIONS: set[str] = {
        ".mp4", ".mov", ".avi", ".mkv", ".webm",
        ".m4v", ".wmv", ".flv", ".ts", ".mts",
        ".m2ts", ".3gp", ".ogv", ".mxf",
    }
    SUPPORTED_IMAGE_EXTENSIONS: set[str] = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    }

    # --- Chunking for uploads ---
    MAX_UPLOAD_SIZE_GB: int = 50
    CHUNK_SIZE_MB: int = 100


    # --- Scanning Pipeline (performance optimization) ---
    FFPROBE_CONCURRENCY: int = 2          # Max parallel ffprobe processes
    FFPROBE_ANALYZE_DURATION: str = "50M"  # ffprobe -analyzeduration safety limit
    FFPROBE_PROBE_SIZE: str = "50M"        # ffprobe -probesize safety limit
    METADATA_BATCH_SIZE: int = 50          # Batch DB writes for metadata results
    FFPROBE_TIMEOUT: int = 60             # Seconds per ffprobe call
    ENABLE_SSE_PROGRESS: bool = True       # Enable real-time scan progress via SSE
    ENABLE_ASYNC_INDEXER: bool = True      # Use async metadata indexing (non-Celery)
    ENABLE_PURGE_ON_SCAN: bool = True      # Auto-purge deleted files from DB on scan

    # --- Frontend ---
    FRONTEND_DIST: str = "../web/dist"
    # --- Authentication ---
    JWT_SECRET: str = ""  # MUST be set via environment variable; no default for security


settings = Settings()


def ensure_dirs():
    """Create all required directories on startup."""
    for p in (settings.DATA_ROOT, settings.MEDIA_ROOT, settings.CACHE_ROOT, settings.MODEL_ROOT):
        p.mkdir(parents=True, exist_ok=True)
    for sub in ("thumbnails", "proxy", "frames", "clip_embeddings"):
        (settings.CACHE_ROOT / sub).mkdir(parents=True, exist_ok=True)

    
    
