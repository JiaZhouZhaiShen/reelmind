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


