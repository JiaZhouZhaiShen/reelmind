from __future__ import annotations

import datetime
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models.library import Library, LibraryPath
from ..models.asset import Asset
from ..models.job import Job
from ..schemas.library import LibraryCreate, LibraryRead, LibraryUpdate, LibraryPathAdd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["Libraries"])


@router.post("", response_model=LibraryRead, status_code=201)
async def create_library(data: LibraryCreate, session: AsyncSession = Depends(get_session)):
    logger.info("Creating library: name=%s, paths=%s, import_mode=%s", data.name, data.paths, data.import_mode)
    lib = Library(name=data.name, description=data.description, import_mode=data.import_mode or "reference", auto_scan=data.auto_scan)
    session.add(lib)
    await session.flush()
    for path_str in data.paths:
        session.add(LibraryPath(library_id=lib.id, path=path_str))
    await session.commit()
    await session.refresh(lib)
    await session.refresh(lib, ["paths"])
    return _library_to_read(lib)


@router.get("", response_model=list[LibraryRead])
async def list_libraries(session: AsyncSession = Depends(get_session)):
    logger.debug("list_libraries")
    result = await session.execute(
        select(Library).options(selectinload(Library.paths)).order_by(Library.created_at.desc())
    )
    return [_library_to_read(l) for l in result.scalars().all()]


@router.get("/{library_id}", response_model=LibraryRead)
async def get_library(library_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("get_library: library_id=%s", library_id)
    stmt = select(Library).options(selectinload(Library.paths)).where(Library.id == library_id)
    result = await session.execute(stmt)
    lib = result.scalar_one_or_none()
    if not lib:
        raise HTTPException(404, "Library not found")
    return _library_to_read(lib)


@router.patch("/{library_id}", response_model=LibraryRead)
async def update_library(library_id: uuid.UUID, data: LibraryUpdate, session: AsyncSession = Depends(get_session)):
    logger.info("update_library: library_id=%s", library_id)
    stmt = select(Library).where(Library.id == library_id)
    result = await session.execute(stmt)
    lib = result.scalar_one_or_none()
    if not lib:
        raise HTTPException(404, "Library not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(lib, key, val)
    await session.commit()
    await session.refresh(lib)
    await session.refresh(lib, ["paths"])
    return _library_to_read(lib)


@router.delete("/{library_id}")
async def delete_library(library_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info("delete_library: library_id=%s", library_id)
    stmt = select(Library).options(selectinload(Library.paths)).where(Library.id == library_id)
    result = await session.execute(stmt)
    lib = result.scalar_one_or_none()
    if not lib:
        raise HTTPException(404, "Library not found")
    await session.delete(lib)
    await session.commit()
    return {"status": "deleted"}




@router.post("/{library_id}/paths")
async def add_library_path(library_id: uuid.UUID, data: LibraryPathAdd, session: AsyncSession = Depends(get_session)):
    logger.info("add_library_path: library_id=%s, path=%s", library_id, data.path)
    stmt = select(Library).where(Library.id == library_id)
    result = await session.execute(stmt)
    lib = result.scalar_one_or_none()
    if not lib:
        raise HTTPException(404, "Library not found")
    lp = LibraryPath(library_id=lib.id, path=data.path, is_network=data.is_network)
    session.add(lp)
    await session.commit()
    await session.refresh(lp)
    return {"status": "ok", "path_id": str(lp.id)}


@router.delete("/{library_id}/paths/{path_id}")
async def remove_library_path(library_id: uuid.UUID, path_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info("remove_library_path: library_id=%s, path_id=%s", library_id, path_id)
    stmt = select(LibraryPath).where(LibraryPath.id == path_id, LibraryPath.library_id == library_id)
    result = await session.execute(stmt)
    lp = result.scalar_one_or_none()
    if not lp:
        raise HTTPException(404, "Path not found")
    await session.delete(lp)
    await session.commit()
    return {"status": "deleted"}


@router.get("/{library_id}/scan-status")
async def get_scan_status(library_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Get the latest scan jobs and pending import count for a library."""
    jobs_stmt = (
        select(Job)
        .where(Job.library_id == str(library_id), Job.job_type == "scan")
        .order_by(Job.created_at.desc())
        .limit(10)
    )
    jobs_result = await session.execute(jobs_stmt)
    jobs = jobs_result.scalars().all()

    processing = await session.execute(
        select(func.count(Asset.id)).where(
            Asset.library_id == library_id,
            Asset.is_imported == False,
        )
    )
    pending_import = processing.scalar() or 0

    return {
        "library_id": str(library_id),
        "pending_import": pending_import,
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








def _library_to_read(lib: Library) -> LibraryRead:
    path_list = [lp.path for lp in lib.paths] if lib.paths else []
    path_details = [{"id": str(lp.id), "path": lp.path} for lp in lib.paths] if lib.paths else []
    return LibraryRead(
        id=lib.id,
        name=lib.name,
        description=lib.description,
        is_external=lib.is_external,
        import_mode=lib.import_mode,
        auto_scan=lib.auto_scan,
        total_assets=lib.total_assets,
        total_size_bytes=lib.total_size_bytes,
        total_duration_seconds=lib.total_duration_seconds or 0.0,
        created_at=lib.created_at,
        updated_at=lib.updated_at,
        settings=lib.settings,
        paths=path_list,
        path_details=path_details,
    )
