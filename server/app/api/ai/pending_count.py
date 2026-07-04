"""Pending asset count route."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from ...config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/pending-count")
async def get_pending_asset_count(
    engines: str = Query(None, description="Comma-separated engine names to scope pending count, e.g. scene,yolo"),
    max_file_size_mb: int = Query(0, description="Max file size in MB to include (0 = no limit)"),
    max_duration_minutes: int = Query(0, description="Max duration in minutes to include (0 = no limit)"),
):
    """Return per-engine pending/success/error counts for AIPendingOverview.
    Optional ?engines=scene,yolo returns selected_pending (union-distinct).
    When max_file_size_mb > 0, assets with file_size = 0, NULL, or exceeding the limit are excluded.
    When max_duration_minutes > 0, assets with duration = 0, NULL, or exceeding the limit are excluded.
    """
    from app.database import sync_session_factory
    from app.core.job_helpers import get_pending_count_by_engine, get_success_error_count_by_engine, ENGINES
    from app.models.ai_engine_job import AIEngineJob
    from app.models.asset import Asset
    from sqlalchemy import text, and_

    session = sync_session_factory()
    try:
        max_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb > 0 else 0
        max_duration_seconds = max_duration_minutes * 60 if max_duration_minutes > 0 else 0

        # total_assets with file size + duration + rendered filters
        q = session.query(AIEngineJob.media_id).join(
            Asset, AIEngineJob.media_id == Asset.id
        ).filter(
            and_(Asset.file_size.isnot(None), Asset.file_size > 0),
        )
        if max_file_size_mb > 0:
            q = q.filter(Asset.file_size <= max_bytes)
        if max_duration_minutes > 0:
            q = q.filter(and_(Asset.duration.isnot(None), Asset.duration > 0, Asset.duration <= max_duration_seconds))
        total_assets = q.distinct().count()

        # total_pending with file size + duration + rendered filters
        sql = text("""
            SELECT COUNT(*) FROM (
                SELECT aje.media_id FROM ai_engine_jobs aje
                JOIN assets a ON a.id = aje.media_id
                WHERE a.file_size > 0
                  AND (:max_bytes = 0 OR a.file_size <= :max_bytes)
                  AND (:max_duration = 0 OR (a.duration > 0 AND a.duration <= :max_duration))
                GROUP BY aje.media_id
                HAVING COUNT(CASE WHEN status != 'pending' THEN 1 END) = 0
            ) sub
        """)
        total_pending = session.execute(sql, {
            "max_bytes": max_bytes,
            "max_duration": max_duration_seconds,
        }).scalar() or 0

        pending_by_engine = get_pending_count_by_engine(session, max_file_size_mb, max_duration_minutes)
        success_error = get_success_error_count_by_engine(session)

        result = {"total_assets": total_assets, "total_pending": total_pending}
        for eng in ENGINES:
            s = success_error.get(eng, {})
            cnt = s.get("success", 0)
            err = s.get("error", 0)
            result[eng + "_pending"] = pending_by_engine.get(eng, 0)
            result[eng + "_success"] = cnt
            result[eng + "_error"] = err
            result[eng + "_done_count"] = cnt + err

        # If engines param provided, calculate union-distinct pending count
        if engines:
            engine_list = [e.strip() for e in engines.split(",")]
            engine_list = [e for e in engine_list if e in ENGINES]
            if engine_list:
                from sqlalchemy import text as _sql_text
                sql_selected = _sql_text("""
                    SELECT COUNT(DISTINCT aje.media_id) FROM ai_engine_jobs aje
                    JOIN assets a ON a.id = aje.media_id
                    WHERE aje.engine_name = ANY(:engines)
                      AND aje.status = 'pending'
                      AND a.file_size > 0
                      AND (:max_bytes = 0 OR a.file_size <= :max_bytes)
                      AND (:max_duration = 0 OR (a.duration > 0 AND a.duration <= :max_duration))
                """)
                selected_pending = session.execute(
                    sql_selected, {
                        "engines": engine_list,
                        "max_bytes": max_bytes,
                        "max_duration": max_duration_seconds,
                    }
                ).scalar() or 0
                result["selected_pending"] = selected_pending

        return result
    finally:
        session.close()


