from __future__ import annotations

import logging
import asyncio

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update as sa_update, delete as sa_delete

from ..database import get_session
from ..models.asset import Asset, AssetTag, ClipSegment, TranscriptSegment
from ..models.tag import Tag
from ..schemas.asset import AssetRead, AssetUpdate, AssetSearchResult
from ..schemas.search import SearchQuery
from ..core.search_engine import search_assets, search_transcripts
from ..core.scanner import compute_file_hash
from ..core.indexer import extract_metadata, delete_asset_disk_files
from ..core.transcoder import generate_thumbnail
from ..config import settings
from ..models.ai_engine_job import AIEngineJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["Assets"])

from .assets import _asset_to_read, _enrich_ai_flags

@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   logger.debug("get_asset: asset_id=%s", asset_id)
   stmt = select(Asset).options(selectinload(Asset.tags).selectinload(AssetTag.tag)).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       logger.warning("get_asset not found: %s", asset_id)
       raise HTTPException(404, "Asset not found")
   logger.debug("get_asset: %s — %s (%dx%d, %.2fs)", asset_id, asset.file_name,
                asset.width or 0, asset.height or 0, asset.duration or 0)
   item = _asset_to_read(asset)
   _enrich_ai_flags([item])
   return item


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
   asset_id: uuid.UUID,
   update: AssetUpdate,
   session: AsyncSession = Depends(get_session),
):
   logger.info("update_asset: asset_id=%s", asset_id)
   stmt = select(Asset).options(selectinload(Asset.tags).selectinload(AssetTag.tag)).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       raise HTTPException(404, "Asset not found")
   update_data = update.model_dump(exclude_unset=True)
   logger.info("Updating asset %s fields: %s", asset_id, list(update_data.keys()))
   for key, val in update_data.items():
       setattr(asset, key, val)
   await session.flush()
   logger.info("Asset updated: %s — %s", asset_id, asset.file_name)
   return _asset_to_read(asset)


@router.delete("/{asset_id}")
async def delete_asset(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   logger.info("delete_asset: asset_id=%s", asset_id)
   stmt = select(Asset).options(selectinload(Asset.tags).selectinload(AssetTag.tag)).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
      logger.warning("delete_asset not found: %s", asset_id)
      raise HTTPException(404, "Asset not found")
   # Delete disk files first (before DB record is removed)
   disk_result = await asyncio.to_thread(delete_asset_disk_files, asset, logger)
   if disk_result["deleted"]:
       logger.info("Deleted %d disk files for %s", len(disk_result["deleted"]), asset.file_name)
   if disk_result["errors"]:
       logger.error("Errors deleting disk files for %s: %s", asset.file_name, disk_result["errors"])
   await session.delete(asset)
   await session.commit()
   logger.info("Asset deleted (DB + disk): %s — %s", asset_id, asset.file_name)
   return {"status": "deleted"}


@router.get("/{asset_id}/transcript")
async def get_transcript(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   logger.debug("get_transcript: asset_id=%s", asset_id)
   stmt = select(TranscriptSegment).where(
       TranscriptSegment.asset_id == asset_id
   ).order_by(TranscriptSegment.start_time)
   result = await session.execute(stmt)
   segments = result.scalars().all()
   logger.debug("get_transcript returned %d segments for %s", len(segments), asset_id)
   return [
       {"start": s.start_time, "end": s.end_time, "text": s.text, "language": s.language}
       for s in segments
   ]


@router.get("/{asset_id}/segments")
async def get_segments(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   logger.debug("get_segments: asset_id=%s", asset_id)
   stmt = select(ClipSegment).where(
       ClipSegment.asset_id == asset_id
   ).order_by(ClipSegment.start_time)
   result = await session.execute(stmt)
   segments = result.scalars().all()
   logger.debug("get_segments returned %d segments for %s", len(segments), asset_id)
   return [
       {"id": str(s.id), "start_time": s.start_time, "end_time": s.end_time,
      "thumbnail_path": s.thumbnail_path, "description": s.description,
      "scene_label": s.scene_label, "source": s.source}
       for s in segments
   ]


@router.post("/{asset_id}/reimport")
async def reimport_asset(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   logger.info("reimport_asset: asset_id=%s", asset_id)
   stmt = select(Asset).options(selectinload(Asset.tags).selectinload(AssetTag.tag)).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       raise HTTPException(404, "Asset not found")

   video_path = Path(asset.original_path)
   if not video_path.exists():
       raise HTTPException(400, "Original file not found")

   try:
       asset.file_hash = compute_file_hash(video_path)
       meta = extract_metadata(video_path)
       for key, val in meta.items():
           setattr(asset, key, val)

       thumb_dir = settings.CACHE_ROOT / "thumbnails"
       thumb_dir.mkdir(parents=True, exist_ok=True)
       thumb_path = thumb_dir / f"{asset.id}.jpg"
       if not thumb_path.exists():
           generate_thumbnail(str(video_path), thumb_path, time_sec=5.0)
       asset.thumbnail_path = str(thumb_path.resolve())


       asset.is_imported = True
   except Exception as e:
       raise HTTPException(500, f"Reimport failed: {e}")

   return {"status": "ok", "message": "Asset reimported"}


@router.post("/{asset_id}/transcribe")
async def trigger_transcribe(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   """Trigger Whisper transcription for an asset via Pipeline (on-demand)."""
   logger.info("trigger_transcribe: asset_id=%s", asset_id)
   from ..services.pipeline_proxy import start_pipeline
   stmt = select(Asset).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       raise HTTPException(404, "Asset not found")
   if not settings.ENABLE_WHISPER:
       raise HTTPException(400, "Whisper transcription is disabled (enable in AI settings first)")
   if not asset.original_path:
       raise HTTPException(400, "Asset has no source path")
   result = start_pipeline(
       limit=1, video_ids=[str(asset.id)],
       engines=["transcript"], task_label="single",
   )
   return {"status": "ok", "message": "Transcription pipeline started",
           "asset_id": str(asset.id), "task_id": result.get("task_id")}
@router.post("/{asset_id}/generate-clip")
async def trigger_generate_clip(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   """Trigger CLIP embedding generation for an asset via Pipeline (on-demand)."""
   logger.info("trigger_generate_clip: asset_id=%s", asset_id)
   from ..services.pipeline_proxy import start_pipeline
   stmt = select(Asset).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       raise HTTPException(404, "Asset not found")
   if not settings.ENABLE_CLIP:
       raise HTTPException(400, "CLIP embedding is disabled (enable in AI settings first)")
   if not asset.original_path:
       raise HTTPException(400, "Asset has no source path")
   result = start_pipeline(
       limit=1, video_ids=[str(asset.id)],
       engines=["clip"], task_label="single",
   )
   return {"status": "ok", "message": "CLIP pipeline started",
           "asset_id": str(asset.id), "task_id": result.get("task_id")}


@router.post("/{asset_id}/generate-scenes")
async def trigger_generate_scenes(
   asset_id: uuid.UUID,
   session: AsyncSession = Depends(get_session),
):
   """Trigger scene detection for an asset via Pipeline (on-demand)."""
   logger.info("trigger_generate_scenes: asset_id=%s", asset_id)
   from ..services.pipeline_proxy import start_pipeline
   stmt = select(Asset).where(Asset.id == asset_id)
   result = await session.execute(stmt)
   asset = result.scalar_one_or_none()
   if not asset:
       raise HTTPException(404, "Asset not found")
   if not asset.original_path:
       raise HTTPException(400, "Asset has no source path")
   result = start_pipeline(
       limit=1, video_ids=[str(asset.id)],
       engines=["scene"], task_label="single",
   )
   return {"status": "ok", "message": "Scene pipeline started",
           "asset_id": str(asset.id), "task_id": result.get("task_id")}


@router.post("/{asset_id}/cancel-ai")
async def cancel_ai_task(
   asset_id: uuid.UUID,
   body: dict,
):
   """Cancel a running AI task for an asset (Pipeline does not support cancellation)."""
   logger.info("cancel_ai_task: asset_id=%s", asset_id)
   raise HTTPException(400, "Pipeline tasks cannot be cancelled via this endpoint. "
                            "Use Orchestrator timeout or checkpoint cancel.")

