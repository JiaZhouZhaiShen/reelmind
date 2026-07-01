from __future__ import annotations

import logging

import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from ..database import get_session
from ..models.tag import Tag
from ..models.asset import Asset, AssetTag
from ..schemas.tag import (
    TagCreate, TagUpdate, TagRead,
    AssetTagAssign, AssetTagCreate, AutoTagRequest, AutoTagResult,
    TagsBatchDelete,
)
from ..core.auto_tagger import auto_generate_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["Tags"])


# ── Tag CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TagRead])
async def list_tags(
    category: str | None = Query(None),
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    logger.debug("list_tags: category=%s, search=%s", category, search)
    stmt = select(Tag)
    if category:
        stmt = stmt.where(Tag.category == category)
    if search:
        stmt = stmt.where(Tag.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Tag.usage_count.desc(), Tag.name)
    result = await session.execute(stmt)
    tags = list(result.scalars().all())
    logger.debug("list_tags returned %d tags", len(tags))
    return tags


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(data: TagCreate, session: AsyncSession = Depends(get_session)):
    logger.info("create_tag: name=%s, category=%s", data.name, data.category)
    existing = await session.execute(select(Tag).where(Tag.name == data.name))
    if existing.scalar_one_or_none():
        logger.warning("create_tag failed: tag '%s' already exists", data.name)
        raise HTTPException(409, f"Tag '{data.name}' already exists")
    tag = Tag(name=data.name, category=data.category or "general", color=data.color)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    logger.info("Tag created: id=%s, name=%s, category=%s", tag.id, tag.name, tag.category)
    return tag


@router.get("/categories")
async def list_tag_categories(session: AsyncSession = Depends(get_session)):
    logger.debug("list_tag_categories")
    stmt = select(Tag.category, func.count(Tag.id)).group_by(Tag.category).order_by(Tag.category)
    result = await session.execute(stmt)
    cats = [{"category": row[0], "count": row[1]} for row in result.all()]
    logger.debug("list_tag_categories returned %d categories", len(cats))
    return cats


@router.get("/auto-ids")
async def get_auto_tag_ids(
    session: AsyncSession = Depends(get_session),
):
    """Return IDs of tags that have been auto-generated (source='auto' in AssetTag)."""
    logger.debug("get_auto_tag_ids")
    stmt = select(AssetTag.tag_id).where(AssetTag.source == "auto").distinct()
    result = await session.execute(stmt)
    ids = [str(row[0]) for row in result.all()]
    logger.debug("get_auto_tag_ids: %d auto-generated tag IDs", len(ids))
    return {"auto_tag_ids": ids}


@router.post("/batch-delete")
async def batch_delete_tags(
    data: TagsBatchDelete,
    session: AsyncSession = Depends(get_session),
):
    """Delete multiple tags by ID and remove all their asset associations."""
    logger.info("batch_delete_tags: %d tags to delete", len(data.tag_ids))
    uuids: list[uuid.UUID] = []
    for tid in data.tag_ids:
        try:
            uuids.append(uuid.UUID(tid))
        except ValueError:
            logger.warning("batch_delete_tags: invalid uuid '%s', skipping", tid)
            continue

    # Delete AssetTag associations first
    at_stmt = select(AssetTag).where(AssetTag.tag_id.in_(uuids))
    at_result = await session.execute(at_stmt)
    at_rows = list(at_result.scalars().all())
    for at in at_rows:
        await session.delete(at)

    # Delete tags
    t_stmt = select(Tag).where(Tag.id.in_(uuids))
    t_result = await session.execute(t_stmt)
    tags = list(t_result.scalars().all())
    for tag in tags:
        await session.delete(tag)

    await session.commit()
    logger.info("batch_delete_tags: deleted %d tags and %d associations", len(tags), len(at_rows))
    return {"count": len(tags), "associations_removed": len(at_rows)}


@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(tag_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("get_tag: tag_id=%s", tag_id)
    stmt = select(Tag).where(Tag.id == tag_id)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if not tag:
        logger.warning("get_tag not found: %s", tag_id)
        raise HTTPException(404, "Tag not found")
    return tag


@router.put("/{tag_id}", response_model=TagRead)
async def update_tag(tag_id: uuid.UUID, data: TagUpdate, session: AsyncSession = Depends(get_session)):
    logger.info("update_tag: tag_id=%s", tag_id)
    stmt = select(Tag).where(Tag.id == tag_id)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if not tag:
        logger.warning("update_tag not found: %s", tag_id)
        raise HTTPException(404, "Tag not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(tag, key, val)
    await session.commit()
    await session.refresh(tag)
    logger.info("Tag updated: id=%s, name=%s", tag.id, tag.name)
    return tag


@router.delete("/{tag_id}")
async def delete_tag(tag_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info("delete_tag: tag_id=%s", tag_id)
    stmt = select(Tag).where(Tag.id == tag_id)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if not tag:
        logger.warning("delete_tag not found: %s", tag_id)
        raise HTTPException(404, "Tag not found")
    await session.delete(tag)
    logger.info("Tag deleted: id=%s, name=%s", tag_id, tag.name if tag else "?")
    return {"status": "deleted"}


# ── Asset-Tag assignment ──────────────────────────────────────────────────────

@router.get("/assets/{asset_id}")
async def get_asset_tags(asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug("get_asset_tags: asset_id=%s", asset_id)
    stmt = (
        select(AssetTag, Tag)
        .join(Tag, AssetTag.tag_id == Tag.id)
        .where(AssetTag.asset_id == asset_id)
    )
    result = await session.execute(stmt)
    items = []
    for at, tag in result.all():
        items.append({
            "id": str(at.id),
            "tag_id": str(tag.id),
            "tag_name": tag.name,
            "category": tag.category,
            "color": tag.color,
            "confidence": at.confidence,
            "source": at.source,
        })
    logger.debug("get_asset_tags returned %d tags for asset %s", len(items), asset_id)
    return items


@router.post("/assets/{asset_id}")
async def add_tags_to_asset(
    asset_id: uuid.UUID,
    data: AssetTagAssign | AssetTagCreate,
    session: AsyncSession = Depends(get_session),
):
    logger.info("add_tags_to_asset: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        logger.warning("add_tags_to_asset: asset not found: %s", asset_id)
        raise HTTPException(404, "Asset not found")

    added = 0
    tag_ids: list[uuid.UUID] = []

    if isinstance(data, AssetTagAssign):
        tag_ids = data.tag_ids
    else:
        # Look up or create tag by name
        t_stmt = select(Tag).where(Tag.name == data.tag_name)
        t_result = await session.execute(t_stmt)
        tag = t_result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=data.tag_name, category=data.category or "general", color=data.color)
            session.add(tag)
            await session.flush()
        tag_ids = [tag.id]

    for tid in tag_ids:
        # Check if already assigned
        existing = await session.execute(
            select(AssetTag).where(
                AssetTag.asset_id == asset_id,
                AssetTag.tag_id == tid,
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(AssetTag(
            asset_id=asset_id,
            tag_id=tid,
            confidence=getattr(data, "confidence", None),
            source=getattr(data, "source", "manual"),
        ))
        # Update usage count
        t = await session.get(Tag, tid)
        if t:
            t.usage_count = (t.usage_count or 0) + 1
        added += 1

    await session.commit()
    logger.info("Tags added to asset %s: %d tags", asset_id, added)
    return {"status": "ok", "tags_added": added}


@router.delete("/assets/{asset_id}/tags/{tag_id}")
async def remove_tag_from_asset(
    asset_id: uuid.UUID,
    tag_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.info("remove_tag_from_asset: asset_id=%s, tag_id=%s", asset_id, tag_id)
    stmt = select(AssetTag).where(
        AssetTag.asset_id == asset_id,
        AssetTag.tag_id == tag_id,
    )
    result = await session.execute(stmt)
    at = result.scalar_one_or_none()
    if not at:
        logger.warning("remove_tag_from_asset: assignment not found: asset=%s, tag=%s", asset_id, tag_id)
        raise HTTPException(404, "Tag assignment not found")
    await session.delete(at)
    # Decrement usage count
    t = await session.get(Tag, tag_id)
    if t and t.usage_count and t.usage_count > 0:
        t.usage_count -= 1
    await session.commit()
    return {"status": "deleted"}


# ── Batch operations ──────────────────────────────────────────────────────────
# ── Auto-tagging ──────────────────────────────────────────────────────────────

async def _run_auto_tagging(
    asset_id: str | None,
    library_id: str | None,
    *,
    _batch_size: int = 500,
):
    """Run auto-tagging in background with own session."""
    from ..database import async_session_factory

    async with async_session_factory() as session:
        logger.info("auto_tag background starting: asset_id=%s, library_id=%s", asset_id, library_id)

        if asset_id:
            from sqlalchemy import select as sel
            stmt = sel(Asset).where(Asset.id == asset_id)
            result = await session.execute(stmt)
            assets = [result.scalar_one_or_none()] if result.scalar_one_or_none() else []
        else:
            query = select(Asset).where(Asset.is_imported == True)
            if library_id:
                query = query.where(Asset.library_id == library_id)
            result = await session.execute(query)
            assets = list(result.scalars().all())

        total = len(assets)
        processed = 0

        for asset in assets:
            if not asset:
                continue
            meta = {
                "width": asset.width,
                "height": asset.height,
                "duration": asset.duration,
                "fps": asset.fps,
                "codec": asset.codec,
                "has_audio": asset.has_audio,
                "audio_channels": asset.audio_channels,
                "mime_type": asset.mime_type,
                "file_name": asset.file_name,
            }
            generated = auto_generate_tags(meta)

            for gt in generated:
                t_stmt = select(Tag).where(Tag.name == gt["name"])
                t_result = await session.execute(t_stmt)
                tag = t_result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=gt["name"], category=gt["category"], color=None)
                    session.add(tag)
                    await session.flush()

                existing_at = await session.execute(
                    select(AssetTag).where(
                        AssetTag.asset_id == asset.id,
                        AssetTag.tag_id == tag.id,
                        AssetTag.source == "auto",
                    )
                )
                if existing_at.scalar_one_or_none():
                    continue

                session.add(AssetTag(
                    asset_id=asset.id,
                    tag_id=tag.id,
                    confidence=gt["confidence"],
                    source="auto",
                ))
                tag.usage_count = (tag.usage_count or 0) + 1

            processed += 1

            if processed % _batch_size == 0:
                await session.commit()
                logger.info("auto_tag background progress: %d/%d assets", processed, total)

        await session.commit()
        logger.info("auto_tag background complete: %d/%d assets", processed, total)


@router.post("/auto-generate", status_code=202)
async def auto_tag_assets(
    req: AutoTagRequest,
    background_tasks: BackgroundTasks,
):
    """Auto-generate tags from metadata in background (returns immediately)."""
    logger.info("auto_tag_assets (background): asset_id=%s, library_id=%s", req.asset_id, req.library_id)
    background_tasks.add_task(_run_auto_tagging, req.asset_id, req.library_id)
    return {
        "status": "started",
        "message": "Auto-tagging started in background",
        "total_assets": None,
    }

@router.get("/assets/{asset_id}/suggest")
async def suggest_tags_for_asset(
    asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Preview tags that would be auto-generated for an asset without saving."""
    logger.debug("suggest_tags_for_asset: asset_id=%s", asset_id)
    stmt = select(Asset).where(Asset.id == asset_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        logger.warning("suggest_tags_for_asset: asset not found: %s", asset_id)
        raise HTTPException(404, "Asset not found")

    meta = {
        "width": asset.width,
        "height": asset.height,
        "duration": asset.duration,
        "fps": asset.fps,
        "codec": asset.codec,
        "has_audio": asset.has_audio,
        "audio_channels": asset.audio_channels,
        "mime_type": asset.mime_type,
        "file_name": asset.file_name,
    }
    suggested = auto_generate_tags(meta)
    logger.debug("suggest_tags_for_asset: %d tags suggested for %s", len(suggested), asset_id)
    return {"tags": suggested}



