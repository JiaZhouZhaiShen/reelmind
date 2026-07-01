from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    category: str = "general"
    color: str | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    color: str | None = None


class TagRead(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None = "general"
    color: str | None = None
    usage_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetTagAssign(BaseModel):
    tag_ids: list[uuid.UUID]


class AssetTagCreate(BaseModel):
    tag_name: str
    category: str = "general"
    color: str | None = None
    confidence: float | None = None
    source: str = "manual"


class AutoTagRequest(BaseModel):
    asset_id: str | None = None  # None = all unprocessed assets
    library_id: str | None = None


class AutoTagResult(BaseModel):
    asset_id: str
    tags_added: int
    tags: list[str]


class TagsBatchDelete(BaseModel):
    tag_ids: list[str]

