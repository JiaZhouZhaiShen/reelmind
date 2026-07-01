"""OrchestrationEvent — event bus from Orchestrator to Server (pure PG, no HTTP).

P3.1: Server polls this table for events, marks consumed, then processes.
"""
from __future__ import annotations
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..database import Base


class OrchestrationEvent(Base):
    __tablename__ = "orchestration_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type = Column(String(32), nullable=False, index=True)
    batch_id = Column(UUID(as_uuid=True), nullable=True)
    data = Column(JSONB, nullable=True)
    consumed = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
