"""Scan API — inline asyncio-based scanning (Celery-free) with SSE progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session, async_session_factory
from ..models.library import Library
from ..models.job import Job
from ..models.asset import Asset
from ..models.system_settings import SystemSetting
from ..config import settings
from ..auth import get_current_user
from ..core.indexer import IndexingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["Scan"])

# ── In-memory scan registry ──────────────────────────────────────────
# Maps library_id -> BackgroundScanState
class BackgroundScanState:
    def __init__(self, job_id: str, task: asyncio.Task):
        self.job_id = job_id
        self.task = task
        self.last_progress: dict = {}

_running_scans: dict[str, BackgroundScanState] = {}


# ── Auth helper ──────────────────────────────────────────────────────
async def require_auth(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user


# ── Helper: build IndexingService with settings ──────────────────────
async def _build_indexing_service(library_id: str) -> IndexingService:
    """Load scanning settings from DB / defaults and build an IndexingService."""
    async with async_session_factory() as session:
        # Load library settings
        stmt = select(Library).options(selectinload(Library.paths)).where(Library.id == library_id)
        result = await session.execute(stmt)
        lib = result.scalar_one_or_none()
        if not lib:
            raise HTTPException(404, "Library not found")

        # Load system settings for scanning
        s = (await session.execute(select(SystemSetting))).scalars().all()
        s_map = {r.key: r.value for r in s}

    ffprobe_concurrency = int(s_map.get("ffprobe_concurrency", settings.FFPROBE_CONCURRENCY))
    metadata_batch_size = int(s_map.get("metadata_batch_size", settings.METADATA_BATCH_SIZE))
    max_workers = max(1, min(ffprobe_concurrency * 2, 8))

    # SSE progress publisher
    def _publish_to_redis(data: dict):
        data["library_id"] = str(library_id)
        try:
            import redis as sync_redis
            r = sync_redis.Redis(
                host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                db=settings.REDIS_DB, decode_responses=True)
            r.publish(f"scan:progress:{library_id}", json.dumps(data, default=str))
            r.close()
        except Exception:
            pass

    # IndexingService handles its own concurrency & progress publishing internally
    return IndexingService()


# --- Reusable scan orchestrator (API + background loop) -----------------------
async def trigger_library_scan(lib_id: str) -> dict:
    """Start a scan for a library. Returns result dict. Used by both API and periodic background scan."""
    async with async_session_factory() as session:
        # Check for existing running scan
        existing = _running_scans.get(lib_id)
        if existing and not existing.task.done():
            return {"status": "skipped", "reason": "already_running"}

        # Load library
        stmt = select(Library).options(selectinload(Library.paths)).where(Library.id == uuid.UUID(lib_id))
        result = await session.execute(stmt)
        lib = result.scalar_one_or_none()
        if not lib:
            return {"status": "error", "reason": "library_not_found"}

        # Supersede old jobs
        old_jobs = (await session.execute(
            select(Job).where(
                Job.library_id == lib_id,
                Job.job_type == "scan",
                Job.status.in_(["queued", "running", "paused"]),
            )
        )).scalars().all()
        for j in old_jobs:
            j.status = "superseded"
            j.message = "Superseded by new scan"

        # Create scan job
        scan_job = Job(
            job_type="scan",
            status="queued",
            library_id=lib_id,
            progress=0.0,
            message="Queued...",
        )
        session.add(scan_job)
        await session.commit()
        await session.refresh(scan_job)

        # Load lib settings
        lib_settings = lib.settings or {}
        custom_video_extensions = lib_settings.get("custom_video_extensions", [])
        excluded_extensions = lib_settings.get("excluded_extensions", [])
        metadata_fields = None
        try:
            mf = lib_settings.get("metadata_fields", "")
            if mf and isinstance(mf, str) and mf.strip():
                metadata_fields = [x.strip() for x in mf.split(",") if x.strip()]
        except Exception:
            pass
        paths = [lp.path for lp in lib.paths]

        # Build IndexingService
        service = await _build_indexing_service(lib_id)

        # Launch scan as background asyncio task
        async def _scan_task():
            try:
                _running_scans[lib_id] = BackgroundScanState(
                    job_id=str(scan_job.id), task=asyncio.current_task()
                )
                # Mark job as running
                async with async_session_factory() as s:
                    j = (await s.execute(select(Job).where(Job.id == scan_job.id))).scalar_one_or_none()
                    if j:
                        j.status = "running"
                        j.message = "Scanning..."
                        await s.commit()

                for path_str in paths:
                    if not Path(path_str).exists():
                        logger.warning("Scan path does not exist: %s", path_str)
                        continue
                    await service.start_scan(
                        root_path=path_str,
                        library_id=lib_id,
                        job_id=str(scan_job.id),
                        included_fields=metadata_fields,
                        custom_extensions=custom_video_extensions,
                        excluded_extensions=excluded_extensions,
                    )

                # Update library totals and mark job completed
                async with async_session_factory() as s:
                    total_assets = (await s.execute(
                        select(func.count(Asset.id)).where(Asset.library_id == uuid.UUID(lib_id))
                    )).scalar() or 0
                    lib_row = (await s.execute(select(Library).where(Library.id == uuid.UUID(lib_id)))).scalar_one_or_none()
                    if lib_row:
                        lib_row.total_assets = total_assets
                        await s.commit()
                    job = (await s.execute(select(Job).where(Job.id == scan_job.id))).scalar_one_or_none()
                    if job:
                        job.status = "completed"
                        job.progress = 100.0
                        job.message = "Scan completed"
                        job.finished_at = func.now()
                        await s.commit()
            except asyncio.CancelledError:
                logger.info("Scan task cancelled for library %s", lib_id)
            except Exception as e:
                logger.exception("Scan task failed for library %s: %s", lib_id, e)
                try:
                    async with async_session_factory() as s:
                        j = (await s.execute(select(Job).where(Job.id == scan_job.id))).scalar_one_or_none()
                        if j:
                            j.status = "failed"
                            j.error = str(e)[:500]
                            j.message = "Scan failed: %s" % str(e)[:200]
                            j.finished_at = func.now()
                            await s.commit()
                except Exception:
                    pass
            finally:
                if lib_id in _running_scans:
                    del _running_scans[lib_id]

        task = asyncio.create_task(_scan_task())
        return {"status": "queued", "library_id": lib_id, "scan_job_id": str(scan_job.id)}


# --- POST /api/scan/{library_id}  Start scan ------------------------------
@router.post("/{library_id}", status_code=202)
async def start_scan(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_auth),
):
    """Start an inline asyncio scan for a library (Celery-free)."""
    lib_id = str(library_id)
    result = await trigger_library_scan(lib_id)
    if result.get("status") == "error":
        status_code_map = {"library_not_found": 404, "already_running": 409}
        raise HTTPException(
            status_code=status_code_map.get(result["reason"], 400),
            detail=result["reason"],
        )
    return result


# ── GET /api/scan/{library_id}/status  Get scan status ────────────────
@router.get("/{library_id}/status")
async def get_scan_status(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_auth),
):
    """Get current scan status — latest job info + pending count."""
    lib_id = str(library_id)

    # Check in-memory running state
    running = _running_scans.get(lib_id)
    in_memory_status = "running" if (running and not running.task.done()) else None

    # Latest jobs from DB
    jobs = (await session.execute(
        select(Job)
        .where(Job.library_id == lib_id, Job.job_type == "scan")
        .order_by(Job.created_at.desc())
        .limit(10)
    )).scalars().all()

    pending = (await session.execute(
        select(func.count(Asset.id)).where(
            Asset.library_id == library_id,
            Asset.is_imported == False,
        )
    )).scalar() or 0

    return {
        "library_id": lib_id,
        "in_memory_status": in_memory_status,
        "pending_import": pending,
        "recent_jobs": [
            {
                "id": str(j.id),
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ],
    }


# ── POST /api/scan/{library_id}/pause  Pause scan ────────────────────
@router.post("/{library_id}/pause")
async def pause_scan(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_auth),
):
    """Cancel the running scan task and mark jobs as paused."""
    lib_id = str(library_id)
    running = _running_scans.get(lib_id)

    if running and not running.task.done():
        running.task.cancel()
        try:
            await running.task
        except asyncio.CancelledError:
            pass

    # Mark jobs as paused
    jobs = (await session.execute(
        select(Job).where(
            Job.library_id == lib_id,
            Job.job_type == "scan",
            Job.status.in_(["queued", "running"]),
        )
    )).scalars().all()

    for j in jobs:
        j.status = "paused"
        j.message = "Scan paused by user"

    await session.commit()

    del _running_scans[lib_id]

    return {"status": "paused", "library_id": lib_id}


# ── POST /api/scan/{library_id}/resume  Resume scan ──────────────────
@router.post("/{library_id}/resume")
async def resume_scan(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_auth),
):
    """Resume a paused scan (delegates to POST /scan/{library_id})."""
    # Simply delegate to start_scan
    return await start_scan(library_id, session, _)


# ── GET /api/scan/{library_id}/events  SSE progress stream ────────────
@router.get("/{library_id}/events")
async def scan_events(
    library_id: uuid.UUID,
    request: Request,
    _: dict = Depends(require_auth),
):
    """SSE endpoint that streams scan progress for a library via Redis pub/sub."""
    lib_id = str(library_id)

    async def event_stream():
        try:
            import redis.asyncio as redis_async
            r = redis_async.Redis(
                host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                db=settings.REDIS_DB, decode_responses=True)
            pubsub = r.pubsub()
            channel = f"scan:progress:{lib_id}"
            await pubsub.subscribe(channel)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    msg = await pubsub.get_message(timeout=3.0)
                    if msg and msg["type"] == "message":
                        yield f"data: {msg['data']}\n\n"
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await r.close()
        except Exception as e:
            yield f"data: {{\"error\": \"{e}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
