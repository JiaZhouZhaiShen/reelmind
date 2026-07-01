"""Create pipeline_configs + orchestration_events tables for P3 Orchestrator.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-30 17:00:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pipeline_configs — auto config for Orchestrator (pure PG read)
    op.create_table(
        "pipeline_configs",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # orchestration_events — event bus from Orchestrator → Server
    op.create_table(
        "orchestration_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default="false", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("orchestration_events")
    op.drop_table("pipeline_configs")
