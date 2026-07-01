"""Initial migration: create all tables.

Revision ID: 0001
Revises: None
Create Date: 2026-06-23 20:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # --- libraries -----------------------------------------------------------
    op.create_table(
        "libraries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(256), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(128), nullable=False, server_default="admin"),
        sa.Column("external_url", sa.String(1024), nullable=True),
        sa.Column("access_key", sa.String(256), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("import_mode", sa.String(16), nullable=False, server_default="copy"),
        sa.Column("auto_scan", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("total_assets", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_duration_seconds", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("settings", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- library_paths -------------------------------------------------------
    op.create_table(
        "library_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("path", sa.String(2048), nullable=False),
        sa.Column("is_network", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- tags ----------------------------------------------------------------
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("category", sa.String(64), nullable=True, server_default="general"),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tag_metadata", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- assets (core table) -------------------------------------------------
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("libraries.id"), nullable=False, index=True),
        sa.Column("original_path", sa.String(2048), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False, index=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True, index=True),
        sa.Column("mime_type", sa.String(64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("codec", sa.String(32), nullable=True),
        sa.Column("video_bitrate", sa.Integer(), nullable=True),
        sa.Column("audio_codec", sa.String(32), nullable=True),
        sa.Column("audio_channels", sa.Integer(), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("media_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_ctime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_mtime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thumbnail_path", sa.String(1024), nullable=True),
        sa.Column("proxy_path", sa.String(1024), nullable=True),
        sa.Column("webvtt_path", sa.String(1024), nullable=True),
        sa.Column("is_imported", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("transcript_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("clip_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("scene_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("clip_embedding", Vector(512), nullable=True),
        sa.Column("exif", postgresql.JSONB(), nullable=True),
        sa.Column("custom_metadata", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- clip_segments -------------------------------------------------------
    op.create_table(
        "clip_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("thumbnail_path", sa.String(1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scene_label", sa.String(128), nullable=True),
        sa.Column("clip_embedding", Vector(512), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="auto"),
    )

    # --- asset_tags ----------------------------------------------------------
    op.create_table(
        "asset_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
    )

    # --- transcript_segments -------------------------------------------------
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
    )

    # --- jobs ----------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_type", sa.String(32), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued", index=True),
        sa.Column("progress", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.String(64), nullable=True, index=True),
        sa.Column("library_id", sa.String(64), nullable=True, index=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.drop_table("transcript_segments")
    op.drop_table("asset_tags")
    op.drop_table("clip_segments")
    op.drop_table("jobs")
    op.drop_table("assets")
    op.drop_table("library_paths")
    op.drop_table("tags")
    op.drop_table("libraries")
