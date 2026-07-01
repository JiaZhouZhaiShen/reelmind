from __future__ import annotations

import logging

import shutil

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func

from ..database import get_session
from ..models.asset import Asset
from ..models.library import Library
from ..models.job import Job
from ..schemas.system import SystemInfo, SystemStats
from ..schemas.library import LibraryRead
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/info", response_model=SystemInfo)
async def get_info():
    logger.debug("System info requested")
    return SystemInfo()


@router.get("/stats", response_model=SystemStats)
async def get_stats(session: AsyncSession = Depends(get_session)):
    logger.debug("System stats requested")
    total_assets = (await session.execute(select(func.count(Asset.id)))).scalar() or 0
    total_size = (await session.execute(select(func.coalesce(func.sum(Asset.file_size), 0)))).scalar() or 0
    total_duration = (await session.execute(select(func.coalesce(func.sum(Asset.duration), 0.0)))).scalar() or 0.0
    lib_result = await session.execute(select(Library).options(selectinload(Library.paths)).order_by(Library.created_at.desc()))
    libs = lib_result.scalars().all()
    pending_jobs = (await session.execute(select(func.count(Job.id)).where(Job.status.in_(["queued", "running"])))).scalar() or 0

    libraries = []
    for lib in libs:
        path_list = [lp.path for lp in lib.paths] if lib.paths else []
        libraries.append(LibraryRead(id=lib.id, name=lib.name, description=lib.description,
            is_external=lib.is_external, import_mode=lib.import_mode, auto_scan=lib.auto_scan,
            total_assets=lib.total_assets, total_size_bytes=lib.total_size_bytes,
            total_duration_seconds=lib.total_duration_seconds or 0.0,
            created_at=lib.created_at, updated_at=lib.updated_at, paths=path_list))

    logger.info("Stats: assets=%d, libraries=%d, total_size=%.2f GB, total_duration=%.1f hrs, pending_jobs=%d",
                  total_assets, len(libraries), total_size / (1024**3), float(total_duration) / 3600, pending_jobs)
    return SystemStats(total_assets=total_assets, total_libraries=len(libraries),
        total_size_bytes=total_size, total_duration_seconds=float(total_duration),
        pending_jobs=pending_jobs, libraries=libraries)


@router.get("/health")
async def health_check():
    free_gb = shutil.disk_usage(settings.DATA_ROOT).free / (1024**3)
    if free_gb < settings.MIN_FREE_SPACE_GB:
        logger.warning("Low disk space: %.1f GB free (min: %d GB)", free_gb, settings.MIN_FREE_SPACE_GB)
    else:
        logger.debug("Health check: %.1f GB free", free_gb)
    return {"status": "healthy" if free_gb > settings.MIN_FREE_SPACE_GB else "low_space", "free_space_gb": round(free_gb, 1)}



