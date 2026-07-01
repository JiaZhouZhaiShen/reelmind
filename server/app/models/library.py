from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class Library(Base):
    __tablename__ = "libraries"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="admin")
    external_url: Mapped[str | None] = mapped_column(String(1024))
    access_key: Mapped[str | None] = mapped_column(String(256))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)
    import_mode: Mapped[str] = mapped_column(String(16), default="copy")
    auto_scan: Mapped[bool] = mapped_column(Boolean, default=True)
    total_assets: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, default=0.0)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    assets: Mapped[list["Asset"]] = relationship(back_populates="library")
    paths: Mapped[list["LibraryPath"]] = relationship(back_populates="library", cascade="all, delete-orphan")

class LibraryPath(Base):
    __tablename__ = "library_paths"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("libraries.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_network: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    library: Mapped["Library"] = relationship(back_populates="paths")
