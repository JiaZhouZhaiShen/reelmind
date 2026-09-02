"""Job helpers for AIEngineJob table — shared by server and pipeline.

This is the single source of truth for status operations on the
ai_engine_jobs table.  After Phase 4 the old Asset column writes
will be deleted from callers.
"""
from __future__ import annotations
import uuid
import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

ENGINES = ("scene", "yolo", "ocr", "clip", "transcript", "diarization")

ENGINE_DEPENDS = {
    "scene": [],
    "yolo": ["scene"],
    "ocr": ["scene"],
    "clip": ["scene"],
    "transcript": [],
    "diarization": ["transcript"],
}

def insert_jobs_for_asset(session: Session, media_id: uuid.UUID | str):
    """Ensure 6 job rows exist for a given media asset."""
    mid = str(media_id)
    from app.models.ai_engine_job import AIEngineJob
    existing = {row.engine_name for row in session.query(AIEngineJob.engine_name).filter(AIEngineJob.media_id == mid).all()}
    for eng in ENGINES:
        if eng not in existing:
            session.add(AIEngineJob(media_id=mid, engine_name=eng, status="pending", depends_on=list(ENGINE_DEPENDS.get(eng, []))))
    session.commit()

def set_job_status(
    session: Session,
    media_id: uuid.UUID | str,
    engine_name: str,
    status: str,
    error_message: str | None = None,
):
    """Update a single job's status + timestamps."""
    import datetime
    from app.models.ai_engine_job import AIEngineJob
    mid = str(media_id)
    job = session.query(AIEngineJob).filter(
        AIEngineJob.media_id == mid,
        AIEngineJob.engine_name == engine_name,
    ).first()
    if not job:
        job = AIEngineJob(media_id=mid, engine_name=engine_name, status=status, depends_on=list(ENGINE_DEPENDS.get(engine_name, [])))
        session.add(job)
    job.status = status
    now = datetime.datetime.now(datetime.timezone.utc)
    if status == "running" and not job.started_at:
        job.started_at = now
    if status in ("completed", "error", "cancelled"):
        job.completed_at = now
        if error_message:
            job.error_message = error_message
        elif status == "completed":
            job.error_message = None
    if status == "error" and error_message:
        job.error_message = error_message
    if status == "cancelled" and error_message:
        job.error_message = error_message
    session.commit()

def set_job_success(session: Session, media_id: uuid.UUID | str, engine_name: str):
    """Convenience: mark a job as completed."""
    set_job_status(session, media_id, engine_name, "completed")

def set_job_error(session: Session, media_id: uuid.UUID | str, engine_name: str, error_message: str | None = None):
    """Convenience: mark a job as error."""
    set_job_status(session, media_id, engine_name, "error", error_message=error_message)

def get_job_status(
    session: Session,
    media_id: uuid.UUID | str,
    engine_name: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Get status of one or all jobs for a media asset."""
    from app.models.ai_engine_job import AIEngineJob
    mid = str(media_id)
    q = session.query(AIEngineJob).filter(AIEngineJob.media_id == mid)
    if engine_name:
        job = q.filter(AIEngineJob.engine_name == engine_name).first()
        if not job:
            return {"engine_name": engine_name, "status": "pending"}
        return {"engine_name": job.engine_name, "status": job.status, "depends_on": job.depends_on}
    jobs = q.all()
    if not jobs:
        return {e: {"status": "pending"} for e in ENGINES}
    return {j.engine_name: {"status": j.status, "depends_on": list(j.depends_on) if j.depends_on else []} for j in jobs}

def reset_jobs_for_asset(session: Session, media_id: uuid.UUID | str):
    """Reset all 6 jobs to pending for a media asset."""
    from app.models.ai_engine_job import AIEngineJob
    mid = str(media_id)
    session.query(AIEngineJob).filter(AIEngineJob.media_id == mid).update(
        {
            "status": "pending",
            "retry_count": 0,
            "started_at": None,
            "completed_at": None,
            "error_message": None,
        }
    )
    session.commit()

def get_pending_count_by_engine(session: Session, max_file_size_mb: int = 0, max_duration_minutes: int = 0) -> dict[str, int]:
    """Return dict of engine_name -> count of pending jobs.

    When `max_file_size_mb > 0`, only count jobs for assets whose file_size
    is within the limit (JOIN assets table).  Assets with file_size = 0 or
    NULL are always excluded.
    When `max_duration_minutes > 0`, only count jobs for assets whose duration
    is within the limit. Assets with duration = 0 or NULL are always excluded.
    """
    from app.models.ai_engine_job import AIEngineJob
    from app.models.asset import Asset
    from sqlalchemy import func, and_
    q = session.query(
        AIEngineJob.engine_name,
        func.count(AIEngineJob.id),
    ).join(
        Asset, AIEngineJob.media_id == Asset.id
    ).filter(
        and_(Asset.file_size.isnot(None), Asset.file_size > 0),
        AIEngineJob.status == "pending",
    )
    if max_file_size_mb > 0:
        q = q.filter(Asset.file_size <= max_file_size_mb * 1024 * 1024)
    if max_duration_minutes > 0:
        q = q.filter(and_(Asset.duration.isnot(None), Asset.duration > 0, Asset.duration <= max_duration_minutes * 60))
    rows = q.group_by(AIEngineJob.engine_name).all()
    result = {}
    for eng in ENGINES:
        result[eng] = 0
    for eng, cnt in rows:
        result[eng] = cnt
    return result

def get_success_error_count_by_engine(session: Session) -> dict[str, dict[str, int]]:
    """Return dict of engine_name -> {success, error} counts."""
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import func
    rows = session.query(
        AIEngineJob.engine_name,
        AIEngineJob.status,
        func.count(AIEngineJob.id),
    ).filter(
        AIEngineJob.status.in_(["completed", "error"])
    ).group_by(AIEngineJob.engine_name, AIEngineJob.status).all()
    result = {}
    for eng in ENGINES:
        result[eng] = {"success": 0, "error": 0}
    for eng, st, cnt in rows:
        if st == "completed":
            result[eng]["success"] = cnt
        elif st == "error":
            result[eng]["error"] = cnt
    return result

def get_jobs_by_ids(session: Session, media_ids: list[str]) -> dict[str, dict[str, str]]:
    """Batch fetch all jobs for a list of media IDs.
    Returns {media_id: {engine_name: status, ...}, ...}
    """
    from app.models.ai_engine_job import AIEngineJob
    rows = session.query(AIEngineJob).filter(AIEngineJob.media_id.in_(media_ids)).all()
    result: dict = {}
    for row in rows:
        result.setdefault(row.media_id, {})[row.engine_name] = row.status
    return result

def insert_jobs_batch(session: Session, media_ids: list[str]):
    """Bulk-insert 6 job rows for each media_id that doesn't have them yet."""
    from app.models.ai_engine_job import AIEngineJob
    existing_mids = {row[0] for row in session.query(AIEngineJob.media_id).filter(AIEngineJob.media_id.in_(media_ids)).distinct().all()}
    to_add = []
    for mid in media_ids:
        if mid not in existing_mids:
            for eng in ENGINES:
                to_add.append(AIEngineJob(media_id=mid, engine_name=eng, status="pending", depends_on=list(ENGINE_DEPENDS.get(eng, []))))
    if to_add:
        session.bulk_save_objects(to_add)
        session.commit()

def get_pending_media_ids(session, engines=None, max_file_size_mb=0, max_duration_minutes=0):
    """Return sorted list of media_ids that have at least one pending job.

    When `engines` is specified, only media_ids with pending jobs for those
    engine types are included.
    When `max_file_size_mb > 0`, only assets whose file_size is within the
    limit are returned (JOIN assets table).  Assets with file_size = 0 or
    NULL are always excluded.
    When `max_duration_minutes > 0`, only assets whose duration is within
    the limit. Assets with duration = 0 or NULL are always excluded.

    P2: used by _orchestrate_batch() to discover which videos need processing.
    """
    from app.models.ai_engine_job import AIEngineJob
    from app.models.asset import Asset
    from sqlalchemy import and_
    q = session.query(AIEngineJob.media_id).join(
        Asset, AIEngineJob.media_id == Asset.id
    ).filter(
        and_(Asset.file_size.isnot(None), Asset.file_size > 0),
        AIEngineJob.status == "pending",
    )
    if engines:
        q = q.filter(AIEngineJob.engine_name.in_(engines))
    if max_file_size_mb > 0:
        q = q.filter(Asset.file_size <= max_file_size_mb * 1024 * 1024)
    if max_duration_minutes > 0:
        q = q.filter(and_(Asset.duration.isnot(None), Asset.duration > 0, Asset.duration <= max_duration_minutes * 60))
    rows = q.distinct(AIEngineJob.media_id).order_by(AIEngineJob.media_id).all()
    return [str(r[0]) for r in rows]


def reset_stale_jobs(
    session: Session,
    media_ids: list[str],
    target_status: str = "pending",
) -> int:
    """Batch-reset running jobs for stale checkpoints. Used at startup."""
    from app.models.ai_engine_job import AIEngineJob
    count = session.query(AIEngineJob).filter(
        AIEngineJob.media_id.in_(list(media_ids)),
        AIEngineJob.status == "running",
    ).update({"status": target_status})
    session.commit()
    return count


def claim_jobs_batch(
    session: Session,
    *,
    engines: list[str],
    max_file_size_bytes: int = 0,
    max_duration_seconds: int = 0,
    batch_size: int = 20,
) -> list[str]:
    """批量 claim：pending→running（SKIP LOCKED，原子）。唯一批量写入口。"""
    _CLAIM_SQL = text("""
        WITH eligible_media AS (
            SELECT DISTINCT j.media_id
            FROM ai_engine_jobs j
            JOIN assets a ON a.id = j.media_id
            WHERE j.status = 'pending'
              AND j.engine_name = ANY(:engines)
              AND NOT EXISTS (
                  SELECT 1 FROM ai_engine_jobs d
                  WHERE d.media_id = j.media_id
                    AND d.engine_name = ANY(j.depends_on)
                    AND d.status != 'completed'
              )
              AND a.file_size IS NOT NULL AND a.file_size > 0
              AND (:max_file_size_bytes <= 0 OR a.file_size <= :max_file_size_bytes)
              AND (:max_duration_seconds <= 0
                  OR (a.duration IS NOT NULL AND a.duration > 0 AND a.duration <= :max_duration_seconds))
            ORDER BY j.media_id
            LIMIT :batch_size
        ),
        eligible AS (
            SELECT j.media_id
            FROM ai_engine_jobs j
            WHERE j.media_id IN (SELECT media_id FROM eligible_media)
              AND j.status = 'pending'
              AND j.engine_name = ANY(:engines)
            FOR UPDATE OF j SKIP LOCKED
        )
        UPDATE ai_engine_jobs
        SET status = 'running',
            started_at = NOW(),
            retry_count = 0,
            error_message = NULL
        FROM eligible
        WHERE ai_engine_jobs.media_id = eligible.media_id
          AND ai_engine_jobs.status = 'pending'
          AND ai_engine_jobs.engine_name = ANY(:engines)
        RETURNING ai_engine_jobs.media_id
    """)
    rows = session.execute(
        _CLAIM_SQL,
        {
            "engines": engines,
            "batch_size": batch_size,
            "max_file_size_bytes": max_file_size_bytes,
            "max_duration_seconds": max_duration_seconds,
        },
    ).fetchall()
    return list(dict.fromkeys(str(r[0]) for r in rows))


def recover_timeout_jobs(
    session: Session,
    timeout_minutes: int = 180,
    max_retries: int = 3,
) -> dict[str, int]:
    """recover_stale + recover_exhausted 合并。返回 {"recovered": n, "exhausted": n}。"""
    params = {"timeout": str(timeout_minutes), "max_retries": max_retries}
    recovered = session.execute(text("""
        UPDATE ai_engine_jobs
        SET status = 'pending',
            retry_count = retry_count + 1,
            started_at = NULL,
            completed_at = NULL,
            error_message = CASE
                WHEN retry_count >= :max_retries THEN 'timeout after ' || :timeout || ' min'
                ELSE 'timeout, retrying'
            END
        WHERE status = 'running'
          AND started_at < NOW() - (:timeout || ' minutes')::interval
          AND retry_count < :max_retries
    """), params).rowcount
    exhausted = session.execute(text("""
        UPDATE ai_engine_jobs
        SET status = 'error',
            started_at = NULL,
            completed_at = NOW(),
            error_message = 'exhausted retries after timeout'
        WHERE status = 'running'
          AND started_at < NOW() - (:timeout || ' minutes')::interval
          AND retry_count >= :max_retries
    """), params).rowcount
    session.commit()
    return {"recovered": recovered, "exhausted": exhausted}


async def insert_jobs_batch_async(session, media_ids: list[str]) -> int:
    """async 批量创建 job 行，indexer 唯一入口（原 indexer 裸 INSERT 迁入）。"""
    if not media_ids:
        return 0
    rows = await session.execute(
        text("SELECT DISTINCT media_id::text FROM ai_engine_jobs WHERE media_id = ANY(:ids)"),
        {"ids": media_ids},
    )
    existing_mids = {r[0] for r in rows}
    new_jobs = []
    for mid in media_ids:
        if mid not in existing_mids:
            for eng in ENGINES:
                new_jobs.append({
                    "media_id": mid,
                    "engine_name": eng,
                    "status": "pending",
                    "depends_on": list(ENGINE_DEPENDS.get(eng, [])),
                })
    if new_jobs:
        await session.execute(
            text("""
                INSERT INTO ai_engine_jobs
                    (media_id, engine_name, status, depends_on)
                VALUES
                    (:media_id, :engine_name, :status, :depends_on)
            """),
            new_jobs,
        )
    return len(new_jobs)


def reclaim_timed_out_jobs(session: Session, media_ids, engines=None) -> int:
    """超时 chunk 回收：running→pending（唯一写入口）。"""
    from app.models.ai_engine_job import AIEngineJob
    if not media_ids:
        return 0
    q = session.query(AIEngineJob).filter(
        AIEngineJob.media_id.in_(media_ids),
        AIEngineJob.status == "running",
    )
    if engines:
        q = q.filter(AIEngineJob.engine_name.in_(engines))
    count = q.update({
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "error_message": "reclaimed from timed-out chunk",
    })
    session.commit()
    return count


def mark_chunk_jobs_completed(session: Session, media_ids, engines) -> int:
    """批处理 chunk 完成后批量标记 completed（唯一写入口）。"""
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import func as sa_func
    if not media_ids:
        return 0
    updated = session.query(AIEngineJob).filter(
        AIEngineJob.media_id.in_(media_ids),
        AIEngineJob.engine_name.in_(engines or []),
        AIEngineJob.status == "running",
    ).update({
        "status": "completed",
        "completed_at": sa_func.now(),
    }, synchronize_session=False)
    session.commit()
    return updated
