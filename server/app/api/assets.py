from __future__ import annotations

import logging

import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.asset import Asset, AssetTag, ClipSegment, TranscriptSegment
from ..models.tag import Tag
from sqlalchemy import select, func, update as sa_update, delete as sa_delete
from ..schemas.asset import AssetRead, AssetUpdate, AssetSearchResult
from ..schemas.search import SearchQuery
from ..core.search_engine import search_assets, search_transcripts
from ..core.scanner import compute_file_hash
from ..core.indexer import extract_metadata
from ..core.transcoder import generate_thumbnail
from ..config import settings
from ..models.ai_engine_job import AIEngineJob
from sqlalchemy import select as sa_select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("", response_model=dict)
async def list_assets(
   library_id: str | None = Query(None),
   include_archived: bool = Query(False),
   is_favorite: bool | None = Query(None),
   page: int = Query(1, ge=1),
    page_size: int = Query(10000, ge=1, le=10000),
    sort_by: str = Query("media_date"),
    sort_order: str = Query("asc"),
    ai_filter: str | None = Query(None),
    orientation_filter: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    logger.debug("list_assets: library_id=%s, include_archived=%s, page=%d, page_size=%d, sort_by=%s, sort_order=%s",
                    library_id, include_archived, page, page_size, sort_by, sort_order)
    stmt = (
        select(Asset)
        .options(selectinload(Asset.tags).selectinload(AssetTag.tag))
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    if not include_archived:
        stmt = stmt.where(Asset.is_archived == False)
    if is_favorite is not None:
        stmt = stmt.where(Asset.is_favorite == is_favorite)

    # AI filter — queried from server side, not client-side filtering
    if ai_filter == 'scene':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'scene',
            AIEngineJob.status == 'completed'
        )
        stmt = stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'transcript':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'transcript',
            AIEngineJob.status == 'completed'
        )
        stmt = stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'yolo':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'yolo',
            AIEngineJob.status == 'completed'
        )
        stmt = stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'ocr':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'ocr',
            AIEngineJob.status == 'completed'
        )
        stmt = stmt.where(Asset.id.in_(subq))

    if orientation_filter == 'landscape':
        stmt = stmt.where(Asset.width > Asset.height)
    elif orientation_filter == 'portrait':
        stmt = stmt.where(Asset.height > Asset.width)
    elif orientation_filter == 'square':
        stmt = stmt.where(Asset.width == Asset.height)

    # Sorting
    valid_sort_fields = {"media_date", "created_at", "file_name", "file_size", "duration"}
    if sort_by not in valid_sort_fields:
        sort_by = "media_date"
    sort_column = getattr(Asset, sort_by, Asset.media_date)
    if sort_order == "desc":
        stmt = stmt.order_by(sort_column.desc().nullslast())
    else:
        stmt = stmt.order_by(sort_column.asc().nullslast())

    # Pagination
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    assets = result.unique().scalars().all()
    # Batch-load AI engine jobs from the unified status table
    job_dict = {}
    if assets:
        asset_ids_list = [a.id for a in assets]
        job_q = sa_select(AIEngineJob).where(AIEngineJob.media_id.in_(asset_ids_list))
        job_r = await session.execute(job_q)
        for j in job_r.scalars().all():
            job_dict.setdefault(str(j.media_id), {})[j.engine_name] = j.status
    items = [_asset_to_read(a, job_dict) for a in assets]

    # Build count query
    count_stmt = select(func.count(Asset.id))
    if library_id:
        count_stmt = count_stmt.where(Asset.library_id == library_id)
    if not include_archived:
        count_stmt = count_stmt.where(Asset.is_archived == False)
    if ai_filter == 'scene':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'scene',
            AIEngineJob.status == 'completed'
        )
        count_stmt = count_stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'transcript':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'transcript',
            AIEngineJob.status == 'completed'
        )
        count_stmt = count_stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'yolo':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'yolo',
            AIEngineJob.status == 'completed'
        )
        count_stmt = count_stmt.where(Asset.id.in_(subq))
    elif ai_filter == 'ocr':
        subq = sa_select(AIEngineJob.media_id).where(
            AIEngineJob.engine_name == 'ocr',
            AIEngineJob.status == 'completed'
        )
        count_stmt = count_stmt.where(Asset.id.in_(subq))
    if orientation_filter == 'landscape':
        count_stmt = count_stmt.where(Asset.width > Asset.height)
    elif orientation_filter == 'portrait':
        count_stmt = count_stmt.where(Asset.height > Asset.width)
    elif orientation_filter == 'square':
        count_stmt = count_stmt.where(Asset.width == Asset.height)


    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0
    logger.debug("list_assets total=%d, returned %d assets", total, len(items))
    _enrich_ai_flags(items)
    return {"items": items, "total": total}


@router.get("/search", response_model=dict)
async def search(
    q: str = Query(""),
    library_id: str | None = Query(None),
    include_archived: bool = Query(False),
    tags: str = Query(""),
    min_duration: float | None = Query(None),
    max_duration: float | None = Query(None),
    has_audio: bool | None = Query(None),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    logger.debug("search: q=%s, library_id=%s, tags=%s, page=%d", q, library_id, tags, page)
    search_query = SearchQuery(
        q=q,
        library_id=library_id,
        include_archived=include_archived,
        tags=tags.split(",") if tags else [],
        min_duration=min_duration,
        max_duration=max_duration,
        has_audio=has_audio,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    assets, total = await search_assets(session, search_query)

    if q and not assets:
        logger.debug("Transcript fallback search for q=%s", q)
        transcript_results = await search_transcripts(session, q, limit=page_size)
        transcript_assets = list(set(r[0] for r in transcript_results))
        results = [AssetSearchResult(
            id=a.id, file_name=a.file_name,
            duration=a.duration, thumbnail_path=a.thumbnail_path,
            score=0.9, match_type="transcript",
        ) for a in transcript_assets]
        return {"results": results, "total": len(results)}

    items = []
    # Batch-load AI engine jobs from the unified status table
    job_dict = {}
    if assets:
        asset_ids_list = [a.id for a in assets]
        job_q = sa_select(AIEngineJob).where(AIEngineJob.media_id.in_(asset_ids_list))
        job_r = await session.execute(job_q)
        for j in job_r.scalars().all():
            job_dict.setdefault(str(j.media_id), {})[j.engine_name] = j.status
    items = [_asset_to_read(a, job_dict) for a in assets]
    logger.info("Search finished: q=%s → %d results (total=%d)", q or "(all)", len(items), total)
    _enrich_ai_flags(items)
    return {"results": items, "total": total}

@router.get("/timeline/years")
async def timeline_years(
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List years that have assets with media_date, with asset counts."""
    from sqlalchemy import func as sa_func
    stmt = (
        select(
            sa_func.extract("year", Asset.media_date).label("year"),
            sa_func.count(Asset.id).label("count"),
        )
        .where(Asset.media_date.isnot(None), Asset.is_archived == False)
        .group_by(sa_func.extract("year", Asset.media_date))
        .order_by(sa_func.extract("year", Asset.media_date).desc())
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    result = await session.execute(stmt)
    rows = result.all()
    return [{"year": int(r.year), "count": r.count} for r in rows]


@router.get("/timeline/months")
async def timeline_months(
    year: int = Query(...),
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List months in a given year that have assets, with counts."""
    from sqlalchemy import func as sa_func
    stmt = (
        select(
            sa_func.extract("month", Asset.media_date).label("month"),
            sa_func.count(Asset.id).label("count"),
        )
        .where(
            Asset.media_date.isnot(None),
            Asset.is_archived == False,
            sa_func.extract("year", Asset.media_date) == year,
        )
        .group_by(sa_func.extract("month", Asset.media_date))
        .order_by(sa_func.extract("month", Asset.media_date).desc())
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    result = await session.execute(stmt)
    rows = result.all()
    return [{"month": int(r.month), "count": r.count} for r in rows]


@router.get("/timeline/days")
async def timeline_days(
    year: int = Query(...),
    month: int = Query(...),
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List days in a given year/month that have assets, with counts."""
    from sqlalchemy import func as sa_func
    stmt = (
        select(
            sa_func.extract("day", Asset.media_date).label("day"),
            sa_func.count(Asset.id).label("count"),
        )
        .where(
            Asset.media_date.isnot(None),
            Asset.is_archived == False,
            sa_func.extract("year", Asset.media_date) == year,
            sa_func.extract("month", Asset.media_date) == month,
        )
        .group_by(sa_func.extract("day", Asset.media_date))
        .order_by(sa_func.extract("day", Asset.media_date).desc())
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    result = await session.execute(stmt)
    rows = result.all()
    return [{"day": int(r.day), "count": r.count} for r in rows]


@router.get("/timeline/assets")
async def timeline_assets(
    year: int = Query(...),
    month: int = Query(...),
    day: int = Query(...),
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List assets for a specific date (year/month/day)."""
    from sqlalchemy import func as sa_func
    stmt = (
        select(Asset)
        .options(selectinload(Asset.tags).selectinload(AssetTag.tag))
        .where(
            Asset.media_date.isnot(None),
            Asset.is_archived == False,
            sa_func.extract("year", Asset.media_date) == year,
            sa_func.extract("month", Asset.media_date) == month,
            sa_func.extract("day", Asset.media_date) == day,
        )
        .order_by(Asset.media_date.desc())
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    result = await session.execute(stmt)
    assets = result.unique().scalars().all()
    enriched = [_asset_to_read(a) for a in assets]
    _enrich_ai_flags(enriched)
    return enriched


@router.get("/timeline/days-by-year")
async def timeline_days_by_year(
    year: int = Query(...),
    library_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List all days in a given year that have assets, with counts, flattened."""
    from sqlalchemy import func as sa_func
    stmt = (
        select(
            sa_func.extract("month", Asset.media_date).label("month"),
            sa_func.extract("day", Asset.media_date).label("day"),
            sa_func.count(Asset.id).label("count"),
        )
        .where(
            Asset.media_date.isnot(None),
            Asset.is_archived == False,
            sa_func.extract("year", Asset.media_date) == year,
        )
        .group_by(
            sa_func.extract("month", Asset.media_date),
            sa_func.extract("day", Asset.media_date),
        )
.order_by(
            sa_func.extract("month", Asset.media_date).desc(),
            sa_func.extract("day", Asset.media_date).desc(),
        )
    )
    if library_id:
        stmt = stmt.where(Asset.library_id == library_id)
    result = await session.execute(stmt)
    rows = result.all()
    return [{"month": int(r.month), "day": int(r.day), "count": r.count} for r in rows]



def _enrich_ai_flags(items: list[AssetRead]) -> None:
    """Batch-query AI SQLite DB to populate has_yolo_tags and has_ocr_text."""
    if not items:
        return
    try:
        from app.models.ai import get_ai_session
        from sqlalchemy import text as _sa_text
        ids = [str(item.id) for item in items]
        _ai = get_ai_session()
        try:
            yolo_rows = _ai.execute(_sa_text(
                "SELECT DISTINCT s.video_id FROM scenes s JOIN scene_tags st ON st.scene_id = s.id "
                "WHERE s.video_id IN ({0})".format(",".join('"' + x + '"' for x in ids))
            )).fetchall()
            yolo_ids = set(r[0] for r in yolo_rows if r[0])
            ocr_rows = _ai.execute(_sa_text(
                "SELECT DISTINCT s.video_id FROM scenes s JOIN scene_ocr so ON so.scene_id = s.id "
                "WHERE s.video_id IN ({0})".format(",".join('"' + x + '"' for x in ids))
            )).fetchall()
            ocr_ids = set(r[0] for r in ocr_rows if r[0])
            for item in items:
                sid = str(item.id)
                item.has_yolo_tags = sid in yolo_ids
                item.has_ocr_text = sid in ocr_ids
        finally:
            _ai.close()
    except Exception as exc:
        logger.warning("Failed to enrich AI flags: %s", exc)

def _asset_to_read(a: Asset, job_dict = None) -> AssetRead:
    """Convert Asset ORM to AssetRead schema."""
    tag_names = []
    if a.tags:
        for at in a.tags:
            tag_names.append(at.tag.name if at.tag else "")
    aid = str(a.id)
    ajobs = (job_dict or {}).get(aid, {})
    return AssetRead(
        id=a.id, library_id=a.library_id,
        original_path=a.original_path,
        file_name=a.file_name, file_size=a.file_size,
        mime_type=a.mime_type, width=a.width, height=a.height,
        duration=a.duration, fps=a.fps,
        codec=a.codec, has_audio=a.has_audio,
        file_hash=a.file_hash,
        thumbnail_path=a.thumbnail_path,
        proxy_path=a.proxy_path,
        transcript_status=ajobs.get("transcript", "pending"),
        clip_status=ajobs.get("clip", "pending"),
        scene_status=ajobs.get("scene", "pending"),
        is_imported=a.is_imported,
        is_archived=a.is_archived,
        is_favorite=a.is_favorite,
        exif=a.exif,
        custom_metadata=a.custom_metadata,
        notes=a.notes,
        media_date=a.media_date,
        created_at=a.created_at,
        updated_at=a.updated_at,
        tags=tag_names,
        yolo_status=ajobs.get("yolo", "pending"),
        ocr_status=ajobs.get("ocr", "pending"),
        diarization_status=ajobs.get("diarization", "pending"),
    )


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
        job_q = sa_select(AIEngineJob).where(AIEngineJob.media_id.in_(asset_ids_list))
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
    await session.delete(asset)
    logger.info("Asset deleted: %s — %s", asset_id, asset.file_name)
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

    sem = asyncio.Semaphore(6)
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


@router.post("/{asset_id}/cancel-ai")
async def cancel_ai_task(
    asset_id: uuid.UUID,
    body: dict,
):
    """Cancel a running AI task for an asset (Pipeline does not support cancellation)."""
    logger.info("cancel_ai_task: asset_id=%s", asset_id)
    raise HTTPException(400, "Pipeline tasks cannot be cancelled via this endpoint. "
                             "Use Orchestrator timeout or checkpoint cancel.")
