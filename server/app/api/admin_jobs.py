"""Admin jobs API."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.job import Job
from .admin import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Job Management ────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_admin_jobs(
    status_filter: str | None = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """List jobs with optional status filter."""
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status_filter:
        if status_filter == "queued":
            stmt = stmt.where(Job.status.in_(["queued"]))
        elif status_filter == "running":
            stmt = stmt.where(Job.status.in_(["running"]))
        elif status_filter == "completed":
            stmt = stmt.where(Job.status.in_(["completed"]))
        elif status_filter == "failed":
            stmt = stmt.where(Job.status.in_(["failed"]))
        elif status_filter == "cancelled":
            stmt = stmt.where(Job.status.in_(["cancelled"]))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(j.id),
            "job_type": j.job_type,
            "status": j.status,
            "progress": j.progress,
            "message": j.message,
            "error": j.error,
            "asset_id": j.asset_id,
            "library_id": j.library_id,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in rows
    ]


@router.post("/jobs/{job_id}/retry")
async def retry_admin_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Retry a failed or cancelled job."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"Cannot retry job with status '{job.status}'")
    job.status = "queued"
    job.progress = 0.0
    job.message = None
    job.error = None
    job.started_at = None
    job.finished_at = None
    if job.payload and job.job_type:
        if job.job_type == "scan_library":
            from ..api.scan import start_scan
            await start_scan(library_id=job.payload.get("library_id"))
        else:
            logger.warning("Retry for job type %r is not supported (Celery tasks migrated to pipeline)", job.job_type)
    session.add(job)
    await session.commit()
    logger.info("Retried job %s (type=%s)", job_id, job.job_type)
    return {"status": "ok"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_admin_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Cancel a queued or running job."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, f"Cannot cancel job with status '{job.status}'")
    if job.status == "running" and job.id:
        logger.info("Marking job %s as cancelled (Celery revoke not available)", job.id)
    job.status = "cancelled"
    job.finished_at = func.now()
    session.add(job)
    await session.commit()
    logger.info("Cancelled job %s (type=%s)", job_id, job.job_type)
    return {"status": "ok"}


# ── User Management ───────────────────────────────────────────────────────
@router.post("/jobs/cleanup")
async def cleanup_admin_jobs(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Delete old finished jobs and mark stale running jobs as failed."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_2h = now - timedelta(hours=2)

    # Delete completed/cancelled/superseded jobs older than 30 days
    delete_result = await session.execute(
        delete(Job).where(
            Job.status.in_(["completed", "cancelled", "superseded"]),
            Job.created_at < cutoff_30d,
        )
    )
    deleted_old = delete_result.rowcount

    # Mark running jobs stuck > 2 hours as failed
    stale_result = await session.execute(
        select(Job).where(
            Job.status == "running",
            Job.started_at < cutoff_2h,
        )
    )
    stale_jobs = stale_result.scalars().all()
    for job in stale_jobs:
        job.status = "failed"
        job.error = "自动标记为失败：任务运行超过 2 小时"
        job.finished_at = now
        session.add(job)

    await session.commit()
    logger.info("Cleanup: deleted %d old jobs, marked %d stale as failed", deleted_old, len(stale_jobs))
    return {"deleted_old": deleted_old, "marked_stale": len(stale_jobs)}



