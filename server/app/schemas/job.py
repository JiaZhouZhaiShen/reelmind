from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel

class JobRead(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    progress: float = 0.0
    message: str | None = None
    error: str | None = None
    asset_id: str | None = None
    library_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
