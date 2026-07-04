from __future__ import annotations

import logging
import uuid
import re
from urllib.parse import quote
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models.asset import Asset, ClipSegment
from ..models.ai import Scene, get_ai_session

logger = logging.getLogger(__name__)

def _safe_filename(name: str) -> str:
    """Strip non-latin-1 characters for Content-Disposition header compatibility."""
    return re.sub(r'[^\x00-\x7F]', '_', name)


router = APIRouter(prefix="/preview", tags=["Preview"])


def _video_accel_response(path: Path, media_type: str) -> Response:
    """Map file path to nginx X-Accel-Redirect for zero-copy video serving.

    Path mapping rules (keep in sync with nginx.conf /accel/ locations):
      /nas-media/*           -> /accel/nas-media/*
      /media/*               -> /accel/media/*
      /data/reelmind/cache/* -> /accel/cache/*
      /data/reelmind/*       -> /accel/data/*
      fallback               -> FileResponse (direct read)
    """
    path_str = str(path)

    if path_str.startswith("/nas-media/"):
        accel_path = "/accel/nas-media/" + path_str[len("/nas-media/"):].lstrip("/")
    elif path_str.startswith("/media/"):
        accel_path = "/accel/media/" + path_str[len("/media/"):].lstrip("/")
    elif path_str.startswith(str(settings.CACHE_ROOT)):
        rel = Path(path_str).relative_to(settings.CACHE_ROOT)
        accel_path = f"/accel/cache/{rel}"
    elif path_str.startswith("/data/reelmind/"):
        accel_path = "/accel/data/" + path_str[len("/data/reelmind/"):].lstrip("/")
    else:
        logger.warning("X-Accel fallback to FileResponse: %s", path_str)
        return FileResponse(path_str, media_type=media_type, headers={
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
        })

    headers = {
        "X-Accel-Redirect": quote(accel_path, safe="/"),
        "Cache-Control": "public, max-age=86400",
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
    }
    return Response(content=None, headers=headers)


@router.get("/thumbnail/{asset_id}")
async def get_thumbnail(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("Preview thumbnail requested: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset or not asset.thumbnail_path:
        logger.warning("Thumbnail not available for asset %s", asset_id)
        raise HTTPException(404, "Thumbnail not available")
    thumb_path = Path(asset.thumbnail_path)
    if not thumb_path.exists():
        logger.warning("Thumbnail file missing for asset %s: %s", asset_id, asset.thumbnail_path)
        raise HTTPException(404, "Thumbnail file not found")
    logger.debug("Thumbnail served for %s", asset_id)
    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.get("/scene-thumbnail/{scene_id}")
async def get_scene_thumbnail(scene_id: str):
    """Serve AI scene thumbnail from Scene table."""
    logger.debug("Scene thumbnail requested: scene_id=%s", scene_id)
    session = get_ai_session()
    scene = session.query(Scene).filter(Scene.id == scene_id).first()
    session.close()
    if not scene or not scene.thumbnail_path:
        logger.warning("Scene thumbnail not available: scene_id=%s", scene_id)
        raise HTTPException(404, "Scene thumbnail not available")
    thumb_path = Path(scene.thumbnail_path)
    if not thumb_path.exists():
        logger.warning("Scene thumbnail file missing: %s", scene.thumbnail_path)
        raise HTTPException(404, "Thumbnail file not found")
    logger.debug("Scene thumbnail served for %s", scene_id)
    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.get("/webvtt/{asset_id}")
async def get_webvtt(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("WebVTT requested: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset or not asset.webvtt_path:
        logger.warning("WebVTT not available for asset %s", asset_id)
        raise HTTPException(404, "WebVTT not available")
    vtt_path = Path(asset.webvtt_path)
    if not vtt_path.exists():
        logger.warning("WebVTT file missing for asset %s: %s", asset_id, asset.webvtt_path)
        raise HTTPException(404, "WebVTT file not found")
    logger.debug("WebVTT served for %s", asset_id)
    return FileResponse(str(vtt_path), media_type="text/vtt")


@router.get("/proxy/{asset_id}")
async def get_proxy_video(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("Proxy video requested: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset or not asset.proxy_path:
        logger.warning("Proxy video not available for asset %s", asset_id)
        raise HTTPException(404, "Proxy video not available")
    proxy_path = Path(asset.proxy_path)
    if not proxy_path.exists():
        logger.warning("Proxy file missing for asset %s: %s", asset_id, asset.proxy_path)
        raise HTTPException(404, "Proxy file not found")
    return _video_accel_response(proxy_path, "video/mp4")


@router.get("/source/{asset_id}")
async def get_source_video(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info("Source video requested: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        logger.warning("Source video: asset not found: %s", asset_id)
        raise HTTPException(404, "Asset not found")
    src_path = Path(asset.original_path)
    if not src_path.exists():
        logger.warning("Source file missing for asset %s: %s", asset_id, asset.original_path)
        raise HTTPException(404, "Source file not found")
    return _video_accel_response(src_path, asset.mime_type or "video/mp4")


@router.get("/download/{asset_id}")
async def download_asset(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Download the original source file as an attachment."""
    logger.info("Download requested: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        logger.warning("Download: asset not found: %s", asset_id)
        raise HTTPException(404, "Asset not found")
    src_path = Path(asset.original_path)
    if not src_path.exists():
        logger.warning("Download: source file missing for asset %s: %s", asset_id, asset.original_path)
        raise HTTPException(404, "Source file not found")
    headers = {
        "Content-Disposition": f"attachment; filename=\"{_safe_filename(asset.file_name)}\"; filename*=UTF-8''{quote(asset.file_name)}"
    }
    return FileResponse(str(src_path), media_type="application/octet-stream", headers=headers)


@router.get("/segment-thumbnail/{segment_id}")
async def get_segment_thumbnail(segment_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("Segment thumbnail requested: segment_id=%s", segment_id)
    stmt = select(ClipSegment).where(ClipSegment.id == segment_id)
    result = await session.execute(stmt)
    seg = result.scalar_one_or_none()
    if not seg or not seg.thumbnail_path:
        logger.warning("Segment thumbnail not available: segment_id=%s", segment_id)
        raise HTTPException(404, "Segment thumbnail not available")
    thumb_path = Path(seg.thumbnail_path)
    if not thumb_path.exists():
        logger.warning("Segment thumbnail file missing: %s", seg.thumbnail_path)
        raise HTTPException(404, "Thumbnail file not found")
    logger.debug("Segment thumbnail served for %s", segment_id)
    return FileResponse(str(thumb_path), media_type="image/jpeg")
@router.get("/segment-thumbnail/{segment_id}")
async def get_segment_thumbnail(segment_id: str, session: AsyncSession = Depends(get_session)):
    """Serve ClipSegment thumbnail from the database path."""
    logger.debug("Segment thumbnail requested: segment_id=%s", segment_id)
    stmt = select(ClipSegment).where(ClipSegment.id == segment_id)
    result = await session.execute(stmt)
    seg = result.scalar_one_or_none()
    if not seg or not seg.thumbnail_path:
        logger.warning("Segment thumbnail not available: segment_id=%s", segment_id)
        raise HTTPException(404, "Segment thumbnail not available")
    thumb_path = Path(seg.thumbnail_path)
    if not thumb_path.exists():
        logger.warning("Segment thumbnail file missing: %s", seg.thumbnail_path)
        raise HTTPException(404, "Thumbnail file not found")
    logger.debug("Segment thumbnail served for %s", segment_id)
    return FileResponse(str(thumb_path), media_type="image/jpeg")

