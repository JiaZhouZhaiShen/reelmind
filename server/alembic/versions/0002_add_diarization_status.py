"""Add diarization_status column to assets table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28 16:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # yolo_status and ocr_status were hot-added to the model
    # after the initial migration — add them if missing
    for col in ("yolo_status", "ocr_status", "diarization_status"):
        op.execute(
            f"ALTER TABLE assets ADD COLUMN IF NOT EXISTS {col} VARCHAR(16) NOT NULL DEFAULT 'pending'"
        )


def downgrade() -> None:
    op.drop_column("assets", "diarization_status")
    # Don't drop yolo_status/ocr_status — they may have been added by
    # the hot-patch; dropping them would be destructive.
