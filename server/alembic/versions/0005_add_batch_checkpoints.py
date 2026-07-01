"""Create batch_checkpoints table for partial-batch progress tracking.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-30 16:45:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_label", sa.String(64), nullable=False, index=True),
        sa.Column("engines", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("total_videos", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("batch_checkpoints")
