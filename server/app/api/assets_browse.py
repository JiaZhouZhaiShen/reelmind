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
from ..models.ai_engine_job import AIEngineJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["Assets"])

from .assets import _asset_to_read, _enrich_ai_flags

@router.get("/directory-tree")
async def directory_tree(
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Return a tree of directories containing assets."""
    stmt = select(Asset.original_path).where(Asset.is_archived == False)
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    stmt = stmt.distinct().order_by(Asset.original_path)
    result = await session.execute(stmt)
    paths = [r[0] for r in result.all()]

    # Build directory tree from paths
    tree: dict = {}
    for p in paths:
        parts = p.replace("\\", "/").split("/")
        node = tree
        # Skip the filename itself (last part)
        for i, part in enumerate(parts[:-1]):
            if not part:
                continue
            if part not in node:
                node[part] = {}
            node = node[part]

    # Convert tree to sorted list format
    def _node_to_list(name: str, children: dict, depth: int = 0) -> dict:
        subdirs = []
        for child_name, child_val in sorted(children.items()):
            subdirs.append(_node_to_list(child_name, child_val, depth + 1))
        return {"name": name, "depth": depth, "children": subdirs}

    entries = []
    for name in sorted(tree.keys()):
        entries.append(_node_to_list(name, tree[name]))
    return entries


@router.get("/browse-path")
async def browse_path(
    path: str = Query(...),
    library_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=10000),
    sort_by: str = Query("media_date"),
    sort_order: str = Query("asc"),
    session: AsyncSession = Depends(get_session),
):
    """List assets in a specific directory path with pagination."""
    logger.debug("browse_path: path=%s, library_id=%s, page=%d, page_size=%d, sort_by=%s, sort_order=%s",
                 path, library_id, page, page_size, sort_by, sort_order)
    stmt = (
        select(Asset)
        .options(selectinload(Asset.tags).selectinload(AssetTag.tag))
        .where(Asset.is_archived == False)
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    path_prefix = "/" + path.replace("\\", "/").strip("/") + "/"
    logger.debug("browse_path: path_prefix=%s", path_prefix)
    stmt = stmt.where(Asset.original_path.like(f"{path_prefix}%"))
    valid_sort_fields = {"media_date", "created_at", "file_name", "file_size", "duration"}
    if sort_by not in valid_sort_fields:
        sort_by = "media_date"
    sort_column = getattr(Asset, sort_by, Asset.media_date)
    if sort_order == "desc":
        stmt = stmt.order_by(sort_column.desc().nullslast())
    else:
        stmt = stmt.order_by(sort_column.asc().nullslast())
    # Count total before pagination
    count_stmt = select(func.count(Asset.id)).where(
        Asset.original_path.like(f"{path_prefix}%"),
        Asset.is_archived == False,
    )
    if library_id:
        count_stmt = count_stmt.where(Asset.library_id == library_id)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0
    logger.debug("browse_path: total=%d", total)
    # Pagination
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    assets = result.unique().scalars().all()
    # Batch-load AI engine jobs from the unified status table
    job_dict = {}
    if assets:
        asset_ids_list = [a.id for a in assets]
        job_q = select(AIEngineJob).where(AIEngineJob.media_id.in_(asset_ids_list))
        job_r = await session.execute(job_q)
        for j in job_r.scalars().all():
            job_dict.setdefault(str(j.media_id), {})[j.engine_name] = j.status
    items = [_asset_to_read(a, job_dict) for a in assets]
    logger.debug("browse_path: returned %d items", len(items))
    _enrich_ai_flags(items)
    return {"items": items, "total": total}


@router.get("/browse-path/directories")
async def browse_path_directories(
    path: str = Query(""),
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List subdirectories directly under a given path."""
    import os
    stmt = select(Asset.original_path).where(Asset.is_archived == False)
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    stmt = stmt.distinct()
    result = await session.execute(stmt)
    all_paths = [r[0].replace("\\", "/") for r in result.all()]

    prefix = "/" + path.replace("\\", "/").strip("/")
    if prefix:
        prefix += "/"

    subdirs: set = set()
    for p in all_paths:
        if prefix and not p.startswith(prefix):
            continue
        suffix = p[len(prefix):].lstrip("/")
        parts = suffix.split("/")
        if len(parts) > 1:
            subdirs.add(parts[0])

    return sorted(subdirs)


@router.post("/batch/update")
async def batch_update_assets(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    logger.info("batch_update_assets: %d assets, updates=%s", len(body.get("asset_ids", [])), list(body.get("updates", {}).keys()))
    asset_ids = body.get("asset_ids", [])
    updates = body.get("updates", {})
    if not asset_ids:
        raise HTTPException(400, "asset_ids required")

    for aid in asset_ids:
        stmt = select(Asset).where(Asset.id == aid)
        result = await session.execute(stmt)
        asset = result.scalar_one_or_none()
        if not asset:
            continue
        for key, val in updates.items():
            if hasattr(asset, key):
                setattr(asset, key, val)

    await session.commit()
    return {"status": "ok", "updated": len(asset_ids)}


@router.post("/batch/delete")
async def batch_delete_assets(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    logger.warning("batch_delete_assets: deleting %d assets", len(body.get("asset_ids", [])))
    asset_ids = body.get("asset_ids", [])
    if not asset_ids:
        raise HTTPException(400, "asset_ids required")

    for aid in asset_ids:
        stmt = select(Asset).where(Asset.id == aid)
        result = await session.execute(stmt)
        asset = result.scalar_one_or_none()
        if asset:
            await session.delete(asset)

    await session.commit()
    return {"status": "ok", "deleted": len(asset_ids)}


@router.post("/batch/tags")
async def batch_tags_assets(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    logger.info("batch_tags_assets: action=%s, %d assets, %d tags",
                body.get("action", "add"), len(body.get("asset_ids", [])), len(body.get("tag_ids", [])))
    asset_ids = body.get("asset_ids", [])
    tag_ids = body.get("tag_ids", [])
    action = body.get("action", "add")  # "add" or "remove"

    if not asset_ids or not tag_ids:
        raise HTTPException(400, "asset_ids and tag_ids required")

    total = 0
    for aid in asset_ids:
        for tid in tag_ids:
            if action == "add":
                existing = await session.execute(
                    select(AssetTag).where(
                        AssetTag.asset_id == aid,
                        AssetTag.tag_id == tid,
                    )
                )
                if not existing.scalar_one_or_none():
                    session.add(AssetTag(asset_id=aid, tag_id=tid, source="manual"))
                    total += 1
                    # increment tag usage count
                    t_stmt = select(Tag).where(Tag.id == tid)
                    t_result = await session.execute(t_stmt)
                    tag = t_result.scalar_one_or_none()
                    if tag:
                        tag.usage_count = (tag.usage_count or 0) + 1
            elif action == "remove":
                del_stmt = sa_delete(AssetTag).where(
                    AssetTag.asset_id == aid,
                    AssetTag.tag_id == tid,
                )
                await session.execute(del_stmt)
                total += 1

    await session.commit()
    return {"status": "ok", "affected": total}

