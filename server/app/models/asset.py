from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("libraries.id"), nullable=False, index=True)
    original_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(32))
    video_bitrate: Mapped[int | None] = mapped_column(Integer)
    audio_codec: Mapped[str | None] = mapped_column(String(32))
    audio_channels: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    media_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_ctime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_mtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    proxy_path: Mapped[str | None] = mapped_column(String(1024))
    webvtt_path: Mapped[str | None] = mapped_column(String(1024))
    is_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    clip_embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    exif: Mapped[dict | None] = mapped_column(JSONB)
    custom_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    library: Mapped["Library"] = relationship(back_populates="assets")
    tags: Mapped[list["AssetTag"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    segments: Mapped[list["ClipSegment"]] = relationship(back_populates="asset", cascade="all, delete-orphan", order_by="ClipSegment.start_time")

class ClipSegment(Base):
    __tablename__ = "clip_segments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    scene_label: Mapped[str | None] = mapped_column(String(128))
    clip_embedding: Mapped[list[float] | None] = mapped_column(Vector(512))
    source: Mapped[str] = mapped_column(String(16), default="auto")
    asset: Mapped["Asset"] = relationship(back_populates="segments")

class AssetTag(Base):
    __tablename__ = "asset_tags"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    asset: Mapped["Asset"] = relationship(back_populates="tags")
    tag: Mapped["Tag"] = relationship()

class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en")
    asset: Mapped["Asset"] = relationship()

