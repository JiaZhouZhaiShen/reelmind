from __future__ import annotations

import logging

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
from ..core.indexer import extract_metadata
from ..core.transcoder import generate_thumbnail
from ..config import settings
from ..core import settings_cache as _scache
from ..models.ai_engine_job import AIEngineJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["Assets"])

from .assets import _asset_to_read, _enrich_ai_flags

async def _generate_single_thumbnail(
    session: AsyncSession, asset_id: str, video_path: str
) -> dict:
    """Generate a single poster thumbnail for an asset.
    Delegates to transcoder.generate_asset_thumbnail (no Celery).
    """
    from ..core.transcoder import generate_asset_thumbnail
    from ..models.asset import Asset
    from sqlalchemy import select

    import asyncio
    loop = asyncio.get_running_loop()
    thumb_path = await loop.run_in_executor(
        None, lambda: generate_asset_thumbnail(video_path, asset_id)
    )

    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        return {"error": "asset not found"}

    asset.thumbnail_path = str(thumb_path)
    session.add(asset)
    await session.commit()
    logger.info("Thumbnail generated: %s", thumb_path)
    return {"status": "ok", "thumbnail_path": str(thumb_path)}


async def _repair_missing_thumbnails_inline(session: AsyncSession) -> dict:
    """Scan and regenerate missing thumbnails for Assets, Scenes, and ClipSegments.
    Parallelized with asyncio.gather + Semaphore.
    Note: Scene/Video are SQLite (AI engine), Asset/ClipSegment are PostgreSQL.
    """
    from pathlib import Path
    from ..models.asset import Asset, ClipSegment
    from ..models.ai import Scene, Video, get_ai_session
    from ..core.transcoder import generate_asset_thumbnail
    from sqlalchemy import select
    import asyncio

    sem = asyncio.Semaphore(_scache.get_int("thumbnail_concurrency", 6))
    stats = {
        "asset": {"found": 0, "repaired": 0, "source_missing": 0},
        "scene": {"found": 0, "repaired": 0, "source_missing": 0},
        "clip_segment": {"found": 0, "repaired": 0, "source_missing": 0},
    }

    tasks: list[tuple[str, str, str, Path, float | None]] = []

    # ===== Asset thumbnails (PostgreSQL) =====
    result = await session.execute(
        select(Asset).where(Asset.thumbnail_path.isnot(None), Asset.is_imported == True)
    )
    for a in result.scalars().all():
        if a.thumbnail_path and not Path(a.thumbnail_path).exists():
            vp = Path(a.original_path)
            if vp.exists():
                tasks.append(("asset", str(a.id), str(vp), settings.CACHE_ROOT / "thumbnails", None))
            else:
                stats["asset"]["source_missing"] += 1

    result2 = await session.execute(
        select(Asset).where(Asset.thumbnail_path.is_(None), Asset.is_imported == True)
    )
    for a in result2.scalars().all():
        vp = Path(a.original_path)
        if vp.exists():
            tasks.append(("asset", str(a.id), str(vp), settings.CACHE_ROOT / "thumbnails", None))
        else:
            stats["asset"]["source_missing"] += 1

    stats["asset"]["found"] = sum(1 for t in tasks if t[0] == "asset")

    # ===== Scene thumbnails (SQLite - AI engine) =====
    try:
        ai_session = get_ai_session()
        try:
            # Case: thumbnail_path NULL
            scenes_null = ai_session.query(Scene).filter(Scene.thumbnail_path.is_(None)).all()
            for sc in scenes_null:
                video = ai_session.query(Video).filter(Video.id == sc.video_id).first()
                if video:
                    vp = Path(video.file_path)
                    if vp.exists():
                        tasks.append(("scene", str(sc.id), str(vp), settings.CACHE_ROOT / "scene_thumbnails", sc.start_time))
                    else:
                        stats["scene"]["source_missing"] += 1
                else:
                    stats["scene"]["source_missing"] += 1

            # Case: thumbnail_path set but file missing
            scenes_path = ai_session.query(Scene).filter(Scene.thumbnail_path.isnot(None)).all()
            for sc in scenes_path:
                if sc.thumbnail_path and not Path(sc.thumbnail_path).exists():
                    video = ai_session.query(Video).filter(Video.id == sc.video_id).first()
                    if video:
                        vp = Path(video.file_path)
                        if vp.exists():
                            tasks.append(("scene", str(sc.id), str(vp), settings.CACHE_ROOT / "scene_thumbnails", sc.start_time))
                        else:
                            stats["scene"]["source_missing"] += 1
        finally:
            ai_session.close()
    except Exception as e:
        logger.warning("Failed to query AI scenes: %s", e)

    stats["scene"]["found"] = sum(1 for t in tasks if t[0] == "scene")

    # ===== ClipSegment thumbnails (PostgreSQL) =====
    for clip, asset_obj in (await session.execute(
        select(ClipSegment, Asset).join(Asset, ClipSegment.asset_id == Asset.id).where(ClipSegment.thumbnail_path.is_(None))
    )).all():
        vp = Path(asset_obj.original_path)
        if vp.exists():
            tasks.append(("clip", str(clip.id), str(vp), settings.CACHE_ROOT / "clip_thumbnails", clip.start_time))
        else:
            stats["clip_segment"]["source_missing"] += 1

    for clip, asset_obj in (await session.execute(
        select(ClipSegment, Asset).join(Asset, ClipSegment.asset_id == Asset.id).where(ClipSegment.thumbnail_path.isnot(None))
    )).all():
        if clip.thumbnail_path and not Path(clip.thumbnail_path).exists():
            vp = Path(asset_obj.original_path)
            if vp.exists():
                tasks.append(("clip", str(clip.id), str(vp), settings.CACHE_ROOT / "clip_thumbnails", clip.start_time))
            else:
                stats["clip_segment"]["source_missing"] += 1

    stats["clip_segment"]["found"] = sum(1 for t in tasks if t[0] == "clip")

    total_found = sum(s["found"] for s in stats.values())
    if not tasks:
        logger.info("repair_thumbnails: nothing to repair")
        return {"status": "ok", **stats}

    logger.info(
        "repair_thumbnails: %d total (asset=%d, scene=%d, clip=%d)",
        total_found, stats["asset"]["found"], stats["scene"]["found"], stats["clip_segment"]["found"]
    )

    # ===== Execute repairs in parallel =====
    async def _do_one(entity_type, entity_id, video_path, output_dir, time_sec):
        async with sem:
            try:
                loop = asyncio.get_running_loop()
                new_path = await loop.run_in_executor(
                    None,
                    lambda: generate_asset_thumbnail(video_path, entity_id, output_dir=output_dir, time_sec=time_sec)
                )

                if entity_type == "scene":
                    # Scene uses SQLite (AI engine)
                    def _write_scene():
                        s = get_ai_session()
                        try:
                            sc = s.query(Scene).filter(Scene.id == entity_id).first()
                            if sc:
                                sc.thumbnail_path = str(new_path)
                                s.commit()
                        finally:
                            s.close()
                    await loop.run_in_executor(None, _write_scene)
                else:
                    # Asset / ClipSegment use PostgreSQL
                    from ..database import async_session_factory
                    async with async_session_factory() as s:
                        if entity_type == "asset":
                            stmt = select(Asset).where(Asset.id == entity_id)
                            obj = (await s.execute(stmt)).scalar_one_or_none()
                            if obj:
                                obj.thumbnail_path = str(new_path)
                        elif entity_type == "clip":
                            stmt = select(ClipSegment).where(ClipSegment.id == entity_id)
                            obj = (await s.execute(stmt)).scalar_one_or_none()
                            if obj:
                                obj.thumbnail_path = str(new_path)
                        await s.commit()
                type_map = {"asset": "asset", "scene": "scene", "clip": "clip_segment"}
                stats[type_map[entity_type]]["repaired"] += 1
            except Exception as e:
                logger.warning("Thumbnail repair failed for %s %s: %s", entity_type, entity_id, e)

    await asyncio.gather(*[_do_one(*t) for t in tasks])

    return {"status": "ok", **stats}
@router.post("/repair-thumbnails")
async def repair_thumbnails(session: AsyncSession = Depends(get_session)):
    """Scan and regenerate missing asset thumbnails (inline ffmpeg, no Celery)."""
    logger.info("repair_thumbnails: starting inline repair")
    result = await _repair_missing_thumbnails_inline(session)
    return result
@router.post("/batch/process-ai")
async def batch_process_ai(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """Find assets missing AI processing and queue Pipeline tasks based on enabled settings."""
    logger.info("batch_process_ai: %s", body)
    from ..services.pipeline_proxy import start_pipeline

    tasks_to_run = body.get("tasks", [])
    library_id = body.get("library_id")
    asset_ids = body.get("asset_ids")

    if not tasks_to_run:
        if settings.ENABLE_WHISPER:
            tasks_to_run.append("transcribe")
        if settings.ENABLE_CLIP:
            tasks_to_run.append("clip")
        tasks_to_run.append("scenes")

    stmt = select(Asset)
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    if asset_ids:
        stmt = stmt.where(Asset.id.in_(asset_ids))
    result = await session.execute(stmt)
    assets = result.scalars().all()
    if not assets:
        return {"status": "ok", "queued": {"transcribe": 0, "clip": 0, "scenes": 0}}

    asset_id_list = [str(a.id) for a in assets if a.original_path]
    engines = []
    if "transcribe" in tasks_to_run and settings.ENABLE_WHISPER:
        engines.append("transcript")
    if "clip" in tasks_to_run and settings.ENABLE_CLIP:
        engines.append("clip")
    if "scenes" in tasks_to_run:
        engines.append("scene")

    if not engines or not asset_id_list:
        return {"status": "ok", "queued": {"transcribe": 0, "clip": 0, "scenes": 0}}

    result = start_pipeline(
        limit=len(asset_id_list), video_ids=asset_id_list,
        engines=engines, task_label="batch",
    )
    logger.info("batch_process_ai: started pipeline task_id=%s", result.get("task_id"))
    return {"status": "ok", "task_id": result.get("task_id"),
            "asset_count": len(asset_id_list), "engines": engines}




