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


def get_pending_count_by_engine(session: Session) -> dict[str, int]:
    """Return dict of engine_name -> count of pending jobs."""
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import func
    rows = session.query(
        AIEngineJob.engine_name,
        func.count(AIEngineJob.id),
    ).filter(
        AIEngineJob.status == "pending"
    ).group_by(AIEngineJob.engine_name).all()
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
def get_pending_media_ids(session, engines=None):
    """Return sorted list of media_ids that have at least one pending job.

    When `engines` is specified, only media_ids with pending jobs for those
    engine types are included.

    P2: used by _orchestrate_batch() to discover which videos need processing.
    """
    from app.models.ai_engine_job import AIEngineJob
    q = session.query(AIEngineJob.media_id).filter(AIEngineJob.status == "pending")
    if engines:
        q = q.filter(AIEngineJob.engine_name.in_(engines))
    rows = q.distinct(AIEngineJob.media_id).order_by(AIEngineJob.media_id).all()
    return [str(r[0]) for r in rows]


