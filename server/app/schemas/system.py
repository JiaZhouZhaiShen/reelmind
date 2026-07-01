from __future__ import annotations
from pydantic import BaseModel
from .library import LibraryRead
from ..config import settings

class SystemInfo(BaseModel):
    app_name: str = settings.APP_NAME
    app_version: str = settings.APP_VERSION
    debug: bool = settings.DEBUG

class SystemStats(BaseModel):
    total_assets: int = 0
    total_libraries: int = 0
    total_size_bytes: int = 0
    total_duration_seconds: float = 0.0
    pending_jobs: int = 0
    libraries: list[LibraryRead] = []
