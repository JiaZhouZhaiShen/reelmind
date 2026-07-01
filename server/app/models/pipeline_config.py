"""PipelineConfig — auto pipeline configuration stored in PG for Orchestrator.

P3: Orchestrator reads auto config from this table instead of JSON file.
Server writes to both JSON (pipeline_config.get_auto_config()) and PG.
"""
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from ..database import Base


class PipelineConfig(Base):
    __tablename__ = "pipeline_configs"

    name = Column(String(64), primary_key=True)
    config = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
