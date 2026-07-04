import logging
from sqlalchemy import select, or_, and_, Text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ..models.asset import Asset, TranscriptSegment, AssetTag
from ..models.tag import Tag
from ..models.library import Library
from ..schemas.search import SearchQuery

logger = logging.getLogger(__name__)



async def search_assets(
    session: AsyncSession,
    query: SearchQuery,
) -> tuple[list[Asset], int]:
    logger.debug("Search assets: q=%s, library_id=%s, tags=%s, page=%d, page_size=%d",
                  query.q, query.library_id, query.tags, query.page, query.page_size)
    stmt = select(Asset)

    # exclude archived by default
    if not query.include_archived:
        stmt = stmt.where(Asset.is_archived == False)

    # text search
    if query.q:
        q = f"%{query.q}%"
        stmt = stmt.where(
            or_(
                Asset.file_name.ilike(q),
                Asset.notes.ilike(q),
            )
        )

    # library filter
    if query.library_id:
        stmt = stmt.where(Asset.library_id == query.library_id)

    # duration filters
    if query.min_duration is not None:
        stmt = stmt.where(Asset.duration >= query.min_duration)
    if query.max_duration is not None:
        stmt = stmt.where(Asset.duration <= query.max_duration)

    if query.min_file_size is not None:
        stmt = stmt.where(Asset.file_size >= query.min_file_size)
    if query.max_file_size is not None:
        stmt = stmt.where(Asset.file_size <= query.max_file_size)
    # orientation filter
    if query.orientation == "landscape":
        stmt = stmt.where(Asset.width > Asset.height)
    elif query.orientation == "portrait":
        stmt = stmt.where(Asset.width < Asset.height)


    # audio filter
    if query.has_audio is not None:
        stmt = stmt.where(Asset.has_audio == query.has_audio)

    # file type filter
    if query.file_types:
        type_filters = []
        for ft in query.file_types:
            type_filters.append(Asset.mime_type.ilike(f"%{ft}%"))
        stmt = stmt.where(or_(*type_filters))

    # tag filter
    if query.tags:
        tag_subq = (
            select(AssetTag.asset_id)
            .join(Tag)
            .where(Tag.name.in_(query.tags))
        )
        stmt = stmt.where(Asset.id.in_(tag_subq))


    # source engine filter (e.g. scene, yolo, ocr, clip, transcript, diarization)
    if query.source_engine:
        from ..models.ai_engine_job import AIEngineJob
        engine_subq = (
            select(AIEngineJob.media_id)
            .where(
                AIEngineJob.engine_name == query.source_engine,
                AIEngineJob.status == 'completed'
            )
        )
        stmt = stmt.where(Asset.id.in_(engine_subq))
    # sorting
    sort_cols = {
        "date": Asset.created_at,
        "duration": Asset.duration,
        "name": Asset.file_name,
    }
    sort_col = sort_cols.get(query.sort_by, Asset.created_at)
    if query.sort_order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # count: standalone query to avoid async subquery issues
    count_stmt = select(func.count(Asset.id))
    if stmt.whereclause is not None:
        count_stmt = count_stmt.where(stmt.whereclause)
    total = (await session.execute(count_stmt)).scalar() or 0

    # pagination
    offset = (query.page - 1) * query.page_size
    stmt = stmt.offset(offset).limit(query.page_size)
    # Add eager loading AFTER pagination so it does not pollute count subquery
    stmt = stmt.options(selectinload(Asset.tags).selectinload(AssetTag.tag))

    result = await session.execute(stmt)
    assets = list(result.scalars().all())
    logger.debug("Search returned %d assets (total=%d)", len(assets), total)
    return assets, total


async def search_transcripts(
    session: AsyncSession,
    q: str,
    limit: int = 50,
) -> list[tuple[Asset, str, float]]:
    logger.debug("Search transcripts: q=%s, limit=%d", q, limit)
    query = f"%{q}%"
    stmt = (
        select(Asset, TranscriptSegment.text, TranscriptSegment.start_time)
        .join(TranscriptSegment, TranscriptSegment.asset_id == Asset.id)
        .where(TranscriptSegment.text.ilike(query))
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()
    logger.debug("Transcript search returned %d results", len(rows))
    return [(row[0], row[1], row[2]) for row in rows]
