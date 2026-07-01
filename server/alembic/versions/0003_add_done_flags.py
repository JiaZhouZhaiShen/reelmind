"""Add _done boolean columns for each AI engine status.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28 17:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    done_cols = [
        "scene_done",
        "yolo_done",
        "ocr_done",
        "clip_done",
        "transcript_done",
        "diarization_done",
    ]
    for col in done_cols:
        op.execute(
            f"ALTER TABLE assets ADD COLUMN IF NOT EXISTS {col} BOOLEAN NOT NULL DEFAULT false"
        )


def downgrade() -> None:
    for col in ("scene_done", "yolo_done", "ocr_done", "clip_done", "transcript_done", "diarization_done"):
        op.drop_column("assets", col)
