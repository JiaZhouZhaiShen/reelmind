"""AI Engine Job - unified status tracking for per-asset per-engine processing.

Replaces the 6 _done/_status column pairs on assets table.

Engine dependency graph:
  scene -> yolo -> clip
  scene -> ocr
  transcript -> diarization
"""
from __future__ import annotations
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import func
from ..database import Base
ENGINE_NAMES = frozenset({'scene','yolo','ocr','clip','transcript','diarization'})
ENGINE_DEPENDS_ON = {'scene':(),'yolo':('scene',),'ocr':('scene',),'clip':('scene',),'transcript':(),'diarization':('transcript',)}
class AIEngineJob(Base):
    __tablename__ = 'ai_engine_jobs'
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    media_id = Column(UUID(as_uuid=True), ForeignKey('assets.id', ondelete='CASCADE'), nullable=False, index=True)
    engine_name = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, server_default='pending', index=True)
    depends_on = Column(ARRAY(String), default=list, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint('media_id','engine_name', name='uq_media_engine'),)
