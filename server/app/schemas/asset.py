from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field

class AssetBase(BaseModel):
    file_name: str
    file_size: int
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    fps: float | None = None
    codec: str | None = None
    has_audio: bool = False
    is_favorite: bool = False
    notes: str | None = None

class AssetRead(AssetBase):
    id: uuid.UUID
    library_id: uuid.UUID
    original_path: str
    file_hash: str | None = None
    thumbnail_path: str | None = None
    proxy_path: str | None = None
    transcript_status: str = "pending"
    clip_status: str = "pending"
    scene_status: str = "pending"
    yolo_status: str = "pending"
    ocr_status: str = "pending"
    diarization_status: str = "pending"
    is_imported: bool = False
    is_archived: bool = False
    exif: dict | None = None
    custom_metadata: dict | None = None
    media_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = []
    has_yolo_tags: bool = False
    has_ocr_text: bool = False

    model_config = {"from_attributes": True}

class AssetUpdate(BaseModel):
    is_favorite: bool | None = None
    is_archived: bool | None = None
    notes: str | None = None
    custom_metadata: dict | None = None

class AssetSearchResult(BaseModel):
    id: uuid.UUID
    file_name: str
    duration: float | None = None
    thumbnail_path: str | None = None
    score: float = 0.0
    match_type: str = "text"
