from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field

class LibraryCreate(BaseModel):
    name: str
    description: str | None = None
    import_mode: str = "reference"
    auto_scan: bool = True
    paths: list[str] = []

class PathRead(BaseModel):
    """Library path with id for editing/deletion."""
    id: str
    path: str

class LibraryRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_external: bool = False
    import_mode: str = "reference"
    auto_scan: bool = True
    settings: dict | None = None
    total_assets: int = 0
    total_size_bytes: int = 0
    total_duration_seconds: float = 0.0
    created_at: datetime
    updated_at: datetime
    paths: list[str] = []
    path_details: list[PathRead] = []

    model_config = {"from_attributes": True}

class LibraryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    import_mode: str | None = None
    auto_scan: bool | None = None
    settings: dict | None = None

class LibraryPathAdd(BaseModel):
    path: str
    is_network: bool = False
