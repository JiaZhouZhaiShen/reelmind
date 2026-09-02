"""ReelMind AI Service configuration — reads from environment variables."""
from __future__ import annotations
import os
from pathlib import Path


class AISettings:
    """Minimal config for the standalone AI container."""

    # PostgreSQL
    # 🔴 安全警告: 以下 DB_USER/DB_PASSWORD 为开发默认值，生产环境务必通过环境变量覆盖！
    DB_HOST: str = os.environ.get("DB_HOST", "postgres")
    DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
    DB_USER: str = os.environ.get("DB_USER", "reelmind")     # 🔴 默认值，生产环境务必覆盖
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "reelmind")  # 🔴 默认值，生产环境务必覆盖
    DB_NAME: str = os.environ.get("DB_NAME", "reelmind")

    # Redis
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))

    # Storage
    DATA_ROOT: str = os.environ.get("DATA_ROOT", "/data/reelmind/data")
    CACHE_ROOT: str = os.environ.get("CACHE_ROOT", "/data/reelmind/cache")
    MODEL_ROOT: str = os.environ.get("MODEL_ROOT", "/data/reelmind/models")

    # AI feature flags
    ENABLE_CLIP: bool = os.environ.get("ENABLE_CLIP", "false").lower() == "true"
    ENABLE_WHISPER: bool = os.environ.get("ENABLE_WHISPER", "false").lower() == "true"
    WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "tiny")

    # HuggingFace
    HUGGINGFACE_TOKEN: str = os.environ.get("HUGGINGFACE_TOKEN", "")

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = AISettings()
