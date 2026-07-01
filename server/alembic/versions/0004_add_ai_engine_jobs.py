"""Create ai_engine_jobs table and migrate existing status data.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-29 12:00:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table(
        "ai_engine_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("engine_name", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("depends_on", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("media_id", "engine_name", name="uq_media_engine"),
        sa.PrimaryKeyConstraint("id"),
    )
    # migrate existing data from assets columns into ai_engine_jobs
    engines = ["scene", "yolo", "ocr", "clip", "transcript", "diarization"]
    for eng in engines:
        op.execute(f"""INSERT INTO ai_engine_jobs (media_id, engine_name, status, depends_on)
        SELECT
            id,
            '{eng}',
            CASE
                WHEN {eng}_done = true THEN 'completed'
                WHEN {eng}_status = 'error' THEN 'error'
                ELSE 'pending'
            END,
            CASE
                WHEN '{eng}' = 'clip' THEN ARRAY['scene']
                WHEN '{eng}' = 'diarization' THEN ARRAY['transcript']
                WHEN '{eng}' = 'yolo' THEN ARRAY['scene']
                WHEN '{eng}' = 'ocr' THEN ARRAY['scene']
                ELSE ARRAY[]::varchar[]
            END
        FROM assets
        ON CONFLICT (media_id, engine_name) DO NOTHING""")
def downgrade() -> None:
    op.drop_table("ai_engine_jobs")
