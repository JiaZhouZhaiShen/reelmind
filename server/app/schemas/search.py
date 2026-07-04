from __future__ import annotations
from pydantic import BaseModel, Field

class SearchQuery(BaseModel):
    q: str = ""
    library_id: str | None = None
    include_archived: bool = False
    tags: list[str] = []
    min_duration: float | None = None
    max_duration: float | None = None
    min_file_size: int | None = None
    max_file_size: int | None = None
    has_audio: bool | None = None
    file_types: list[str] = []
    sort_by: str = "relevance"  # relevance | date | duration | name
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 50

class ClipSearchQuery(BaseModel):
    q: str = ""
    asset_id: str | None = None
    text_match: str = ""
