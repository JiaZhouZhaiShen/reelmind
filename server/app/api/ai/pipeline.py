"""Pipeline configuration, engine jobs, batch management, single-video pipeline."""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...config import settings
from .shared import (_orchestration_lock, _orchestrate_batch,
    _mark_checkpoint_cancelled)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/pipeline/manual/config")
async def get_manual_pipeline_config():
    """Get manual batch pipeline configuration."""
    from ...services.pipeline_config import get_manual_config
    return {"config": get_manual_config()}

@router.post("/pipeline/manual/config")
async def set_manual_pipeline_config(data: dict):
    """Save manual batch pipeline configuration."""
    from ...services.pipeline_config import save_manual_config
    save_manual_config(data.get("config", data))
    logger.info("Manual pipeline config saved: %s", data)
    return {"status": "saved"}

@router.get("/pipeline/auto/pending-summary")
async def get_auto_pending_summary():
    """Orchestrator 专用：返回 backlog/running 汇总。"""
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import text
    session = sync_session_factory()
    try:
        backlog = session.execute(text("""
            SELECT COUNT(*) FROM ai_engine_jobs
            WHERE status = 'pending'
              AND NOT EXISTS (
                  SELECT 1 FROM ai_engine_jobs d
                  WHERE d.media_id = ai_engine_jobs.media_id
                    AND d.engine_name = ANY(ai_engine_jobs.depends_on)
                    AND d.status != 'completed'
              )
        """)).scalar() or 0
        running = session.query(AIEngineJob).filter(
            AIEngineJob.status == "running"
        ).count()
        total_pending = session.query(AIEngineJob).filter(
            AIEngineJob.status == "pending"
        ).count()
        from sqlalchemy import func
        rows = session.query(
            AIEngineJob.engine_name,
            func.count(AIEngineJob.id)
        ).filter(
            AIEngineJob.status == "pending"
        ).group_by(AIEngineJob.engine_name).all()
        pending_per_engine = {r[0]: r[1] for r in rows}
        return {
            "backlog": backlog,
            "running": running,
            "total_pending": total_pending,
            "pending_per_engine": pending_per_engine,
        }
    finally:
        session.close()
@router.post("/pipeline/auto/claim")
async def claim_auto_chunk(data: dict):
    """Orchestrator 调用：原子 claim 一个 chunk（FOR UPDATE SKIP LOCKED）。"""
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob, ENGINE_NAMES
    from app.models.orchestration_event import OrchestrationEvent
    from sqlalchemy import text as _text
    import uuid
    engines = data.get("engines", list(ENGINE_NAMES))
    batch_size = data.get("batch_size", 50)
    filters = data.get("filters", {})
    max_file_size_mb = filters.get("max_file_size_mb", 0)
    max_duration_minutes = filters.get("max_duration_minutes", 0)
    max_file_size_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb > 0 else 0
    max_duration_seconds = max_duration_minutes * 60 if max_duration_minutes > 0 else 0
    batch_id = str(uuid.uuid4())
    session = sync_session_factory()
    try:
        _CLAIM_SQL = _text("""
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
            }
        ).fetchall()
        claimed = list(dict.fromkeys(str(r[0]) for r in rows))
        if not claimed:
            session.close()
            return {"claimed": False, "batch_id": batch_id, "media_ids": []}
        event = OrchestrationEvent(
            event_type="chunk_ready",
            batch_id=uuid.UUID(batch_id),
            data={"batch_id": batch_id, "media_ids": claimed},
        )
        session.add(event)
        session.commit()
        logger.info("claim_auto_chunk: batch=%s media_ids=%d", batch_id, len(claimed))
        return {"claimed": True, "batch_id": batch_id, "media_ids": claimed}
    except Exception:
        logger.exception("claim_auto_chunk failed")
        session.rollback()
        return {"claimed": False, "batch_id": batch_id, "media_ids": []}
    finally:
        session.close()
@router.get("/pipeline/auto/chunk-done")
async def check_chunk_done(batch_id: str = Query(...), engines: str = Query(None)):
    """Orchestrator 轮询：检查一个 chunk 是否处理完成。"""
    from app.database import sync_session_factory
    from app.models.orchestration_event import OrchestrationEvent
    from app.models.ai_engine_job import AIEngineJob
    import uuid
    try:
        uid = uuid.UUID(batch_id)
    except ValueError:
        return {"error": "invalid batch_id"}
    session = sync_session_factory()
    try:
        event = session.query(OrchestrationEvent).filter(
            OrchestrationEvent.batch_id == uid,
            OrchestrationEvent.event_type == "chunk_ready",
        ).first()
        if not event:
            return {"error": "batch_id not found", "done": True}
        media_ids = (event.data or {}).get("media_ids", [])
        if not media_ids:
            return {"done": True, "remaining": 0}
        engine_list = engines.split(",") if engines else []
        remaining = session.query(AIEngineJob).filter(
            AIEngineJob.media_id.in_(media_ids),
            AIEngineJob.status.notin_(["completed", "error", "cancelled"]),
        )
        if engine_list:
            remaining = remaining.filter(AIEngineJob.engine_name.in_(engine_list))
        remaining_count = remaining.count()
        return {"done": remaining_count == 0, "remaining": remaining_count}
    finally:
        session.close()
@router.post("/pipeline/auto/reclaim")
async def reclaim_timed_out_chunk(data: dict):
    """Orchestrator 调用：超时后把 chunk 的 jobs 重置回 pending。"""
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob
    media_ids = data.get("media_ids", [])
    engines = data.get("engines", [])
    if not media_ids:
        return {"reclaimed": 0}
    session = sync_session_factory()
    try:
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
        logger.info("reclaim_timed_out_chunk: reclaimed %d jobs", count)
        return {"reclaimed": count}
    except Exception:
        logger.exception("reclaim_timed_out_chunk failed")
        session.rollback()
        return {"reclaimed": 0}
    finally:
        session.close()
@router.post("/pipeline/auto/recover-stale")
async def recover_stale_jobs():
    """恢复超时/耗尽重试次数的 jobs（组合 recover_stale + recover_exhausted）。"""
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import text as _text
    timeout_minutes = 180
    max_retries = 3
    session = sync_session_factory()
    try:
        recovered = session.execute(_text("""
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
        """), {"timeout": str(timeout_minutes), "max_retries": max_retries}).rowcount
        exhausted = session.execute(_text("""
            UPDATE ai_engine_jobs
            SET status = 'error',
                started_at = NULL,
                completed_at = NOW(),
                error_message = 'exhausted retries after timeout'
            WHERE status = 'running'
              AND started_at < NOW() - (:timeout || ' minutes')::interval
              AND retry_count >= :max_retries
        """), {"timeout": str(timeout_minutes), "max_retries": max_retries}).rowcount
        session.commit()
        if recovered:
            logger.info("recover_stale: recovered %d stale jobs for retry", recovered)
        if exhausted:
            logger.warning("recover_stale: exhausted %d jobs (max retries=%d)", exhausted, max_retries)
        return {"recovered": recovered, "exhausted": exhausted}
    except Exception:
        logger.exception("recover_stale_jobs failed")
        session.rollback()
        return {"recovered": 0, "exhausted": 0}
    finally:
        session.close()
@router.post("/pipeline/manual/start")
async def start_manual_batch():
    """Start a manual batch pipeline run — creates checkpoint + background thread."""
    from ...services.pipeline_config import get_manual_config
    from app.database import sync_session_factory
    from app.core.job_helpers import get_pending_media_ids
    from app.models.batch_checkpoint import BatchCheckpoint
    from app.models.ai_engine_job import AIEngineJob
    import threading

    config = get_manual_config()
    engines = config.get("engines")
    batch_size = config.get("batch_size", 100)

    # ── Check if another orchestration is still running (auto batch in background) ──
    if not _orchestration_lock.acquire(blocking=False):
        logger.warning("start_manual_batch: orchestration lock held, manual batch rejected")
        return {"status": "error", "message": "已有批处理任务正在运行，请等待完成后再试"}
    _orchestration_lock.release()

    session = sync_session_factory()
    try:
        # ── Cancel any existing running batches to prevent parallel orchestration ──
        running_batches = session.query(BatchCheckpoint).filter(
            BatchCheckpoint.status == "running"
        ).all()
        for old_batch in running_batches:
            old_batch.status = "cancelled"
            logger.info("start_manual_batch: cancelled stale batch %s", old_batch.id)
        if running_batches:
            session.commit()

        # ── Skip completed: only include jobs already in "pending" status.
        # Already-completed engine jobs are not re-processed;
        # error/running jobs are left untouched so batch only picks up pending work.
        _fs = config.get("filters", {}).get("max_file_size_mb", 0)
        _dur = config.get("filters", {}).get("max_duration_minutes", 0)
        all_pending = get_pending_media_ids(session, engines, _fs, _dur)
        total = len(all_pending) if all_pending else 0
        # manual batch: only process 1 chunk per click
        config["max_chunks"] = 1

        checkpoint = BatchCheckpoint(
            task_label="manual",
            engines=engines or [],
            total_videos=total,
            batch_size=batch_size,
            processed=0,
            status="running",
        )
        session.add(checkpoint)
        session.commit()
        batch_id = str(checkpoint.id)
        # If no pending videos, mark as completed immediately so frontend doesn't get stuck
        if total == 0:
            checkpoint.status = "completed"
            checkpoint.processed = 0
            session.commit()
    finally:
        session.close()

    if total > 0:
        threading.Thread(
            target=_orchestrate_batch,
            args=("manual", config, batch_id),
            daemon=True,
        ).start()
        logger.info("start_manual_batch: spawned bg thread, batch=%s total=%d", batch_id, total)
    else:
        logger.info("start_manual_batch: no pending videos, checkpoint=%s", batch_id)

    return {"status": "started", "batch_id": batch_id}

@router.get("/pipeline/auto/config")
async def get_auto_pipeline_config_endpoint():
    """Get auto batch pipeline configuration."""
    from ...services.pipeline_config import get_auto_config
    return {"config": get_auto_config()}

@router.post("/pipeline/auto/config")
async def set_auto_pipeline_config(data: dict):
    """Save auto batch pipeline configuration (JSON + PG double-write).

    P3: Orchestrator reads from PG, so config must be written to both locations.
    """
    from ...services.pipeline_config import save_auto_config
    from app.database import sync_session_factory
    from app.models.pipeline_config import PipelineConfig
    import json

    cfg = data.get("config", data)
    save_auto_config(cfg)

    # Double-write to PG for Orchestrator
    session = sync_session_factory()
    try:
        pg_config = session.query(PipelineConfig).filter(PipelineConfig.name == "auto").first()
        if pg_config:
            pg_config.config = cfg
        else:
            session.add(PipelineConfig(name="auto", config=cfg))
        session.commit()
        logger.info("Auto pipeline config double-written to PG")
    except Exception as e:
        logger.error("Failed to write auto config to PG: %s", e)
        session.rollback()
    finally:
        session.close()

    logger.info("Auto pipeline config saved: %s", data)
    return {"status": "saved"}

@router.get("/pipeline/single/config")
async def get_single_pipeline_config():
    """Get single video pipeline configuration."""
    from ...services.pipeline_config import get_single_config
    return {"config": get_single_config()}

@router.post("/pipeline/single/config")
async def set_single_pipeline_config(data: dict):
    """Save single video pipeline configuration."""
    from ...services.pipeline_config import save_single_config
    save_single_config(data.get("config", data))
    logger.info("Single pipeline config saved: %s", data)
    return {"status": "saved"}

@router.get("/pipeline/batch/status/{batch_id}")
async def get_batch_checkpoint_status(batch_id: str):
    """Get progress of a specific batch checkpoint."""
    from app.database import sync_session_factory
    from app.models.batch_checkpoint import BatchCheckpoint
    session = sync_session_factory()
    try:
        cp = session.query(BatchCheckpoint).filter(BatchCheckpoint.id == batch_id).first()
        if not cp:
            return {"status": "not_found"}
        return {
            "id": str(cp.id),
           "task_label": cp.task_label,
           "total_videos": cp.total_videos,
            "batch_size": cp.batch_size,
           "processed": cp.processed,
           "status": cp.status,
            "created_at": cp.created_at.isoformat() if cp.created_at else None,
           "updated_at": cp.updated_at.isoformat() if cp.updated_at else None,
        }
    finally:
        session.close()

@router.get("/pipeline/batch/list")
async def list_batch_checkpoints(limit: int = 20, active_only: bool = True):
    """List batch checkpoints ordered by creation time DESC.
    When active_only=True (default), only show 'running' checkpoints.
    """
    from app.database import sync_session_factory
    from app.models.batch_checkpoint import BatchCheckpoint
    session = sync_session_factory()
    try:
        q = session.query(BatchCheckpoint).order_by(
            BatchCheckpoint.created_at.desc()
        )
        if active_only:
            q = q.filter(BatchCheckpoint.status != 'cancelled')
        cps = q.limit(limit).all()
        return {
            "checkpoints": [
               {
                   "id": str(cp.id),
                   "task_label": cp.task_label,
                   "total_videos": cp.total_videos,
                   "engines": cp.engines if cp.engines else [],
                   "batch_size": cp.batch_size,
                   "processed": cp.processed,
                   "status": cp.status,
                   "created_at": cp.created_at.isoformat() if cp.created_at else None,
                   "engine_progress": cp.engine_progress if hasattr(cp, "engine_progress") else None,
               }
                for cp in cps
            ]
        }
    finally:
        session.close()

@router.get("/pipeline/batch/engine-progress/{batch_id}")
async def get_batch_engine_progress(batch_id: str):
    """Return per-engine progress for a batch checkpoint.
    Uses current_chunk_ids to query ai_engine_jobs for real-time engine-level progress.
    """
    from app.database import sync_session_factory
    from app.models.batch_checkpoint import BatchCheckpoint
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import func as sa_func
    import uuid
    session = sync_session_factory()
    try:
        try:
            uid = uuid.UUID(batch_id)
        except ValueError:
            return {"status": "error", "message": "Invalid batch_id"}
        cp = session.query(BatchCheckpoint).filter(BatchCheckpoint.id == uid).first()
        if not cp:
            return {"status": "not_found"}

        current_ids = cp.current_chunk_ids or []
        progress = {}
        if current_ids:
            rows = session.query(
                AIEngineJob.engine_name,
                AIEngineJob.status,
                sa_func.count(AIEngineJob.id)
            ).filter(
                AIEngineJob.media_id.in_(current_ids),
                AIEngineJob.engine_name.in_(cp.engines or [])
            ).group_by(AIEngineJob.engine_name, AIEngineJob.status).all()

            for eng_name, status, cnt in rows:
                if eng_name not in progress:
                    progress[eng_name] = {"completed": 0, "running": 0, "pending": 0, "error": 0}
                if status in progress[eng_name]:
                    progress[eng_name][status] = cnt

        return {
            "status": "ok",
            "batch_id": batch_id,
            "chunk_size": len(current_ids) if current_ids else 0,
            "engines": cp.engines or [],
            "engine_progress": progress,
            "stored_progress": cp.engine_progress if hasattr(cp, "engine_progress") else {},
        }
    finally:
        session.close()

@router.post("/pipeline/jobs/reset-errors")
async def reset_error_jobs():
    """Reset all AI engine jobs with status='error' back to 'pending'.

    This allows previously failed/oversized/skipped files to be re-processed.
    """
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import update

    session = sync_session_factory()
    try:
        error_count = session.query(AIEngineJob).filter(AIEngineJob.status == "error").count()
        if error_count == 0:
            return {"count": 0}
        stmt = (
            update(AIEngineJob)
            .where(AIEngineJob.status == "error")
            .values(
                status="pending",
                retry_count=0,
                started_at=None,
                completed_at=None,
                error_message=None,
            )
        )
        session.execute(stmt)
        session.commit()
        logger.info("reset_error_jobs: reset %d error jobs to pending", error_count)
        return {"count": error_count}
    finally:
        session.close()

@router.get("/engine-jobs/{video_id}")
async def get_engine_jobs(video_id: str):
    """Return per-engine job status for a single video from ai_engine_jobs."""
    import uuid
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob, ENGINE_NAMES

    try:
        uid = uuid.UUID(video_id)
    except ValueError:
        return {"error": "invalid video_id"}
    from app.database import sync_session_factory

    session = sync_session_factory()
    try:
        from ...services.pipeline_config import get_single_config as _get_cfg
        _cfg = _get_cfg() or {}
        _configured = _cfg.get("engines") or []
        jobs = {eng: "pending" for eng in _configured}
        rows = session.query(AIEngineJob).filter(
            AIEngineJob.media_id == uid
       ).all()
        for row in rows:
           if row.engine_name in jobs:
               jobs[row.engine_name] = row.status
        return {"video_id": video_id, "jobs": jobs}
    except Exception as e:
        logger.error("get_engine_jobs failed for %s: %s", video_id, e)
        return {"video_id": video_id, "jobs": {}, "error": str(e)}
    finally:
        session.close()
@router.get("/results-ready/{video_id}")
async def get_results_ready(video_id: str):
    """Return results_ready flags based on actual SQLite data (Rule ㉑)."""
    try:
        uid = uuid.UUID(video_id)
    except ValueError:
        return {"error": "invalid video_id"}
    from app.database import sync_session_factory

    session = sync_session_factory()
    try:
        from ...services.pipeline_config import get_single_config as _get_cfg
        _cfg = _get_cfg() or {}
        _configured = _cfg.get("engines") or []
        from app.models.ai_engine_job import AIEngineJob
        jobs = {eng: "pending" for eng in _configured}
        rows = session.query(AIEngineJob).filter(
            AIEngineJob.media_id == uid
        ).all()
        for row in rows:
            if row.engine_name in jobs:
                jobs[row.engine_name] = row.status

        state = "completed"
        for eng, status in jobs.items():
            if status == "running": state = "running"
            elif status == "error": state = "error"
            elif status == "pending" and state == "completed": state = "pending"
    except Exception as e:
        logger.error("get_results_ready PG failed for %s: %s", video_id, e)
        session.close()
        return {"video_id": video_id, "state": "error", "results_ready": {}, "error": str(e)}
    finally:
        session.close()

    from app.models.ai import Scene, Subtitle, SceneTag, SceneOCR, get_ai_session
    ai_session = get_ai_session()
    try:
        str_id = str(uid)
        has_scenes = ai_session.query(Scene).filter(Scene.video_id == str_id).count() > 0
        has_subtitles = ai_session.query(Subtitle).filter(Subtitle.video_id == str_id).count() > 0
        has_tags = ai_session.query(SceneTag).join(Scene).filter(Scene.video_id == str_id).count() > 0
        has_ocr = ai_session.query(SceneOCR).join(Scene).filter(Scene.video_id == str_id).count() > 0
    except Exception as e:
        logger.error("get_results_ready SQLite failed for %s: %s", video_id, e)
        ai_session.close()
        return {"video_id": video_id, "state": "error", "results_ready": {}, "error": str(e)}
    finally:
        ai_session.close()

    # Only check results_ready for engines that were configured
    engine_to_result = {
        "scenes": ("scenes", has_scenes),
        "ocr": ("ocr", has_ocr),
        "subtitle": ("subtitle", has_subtitles),
        "tags": ("tags", has_tags),
    }
    # Map configured engines to their result keys
    result_map = {
        "scene": "scenes",
        "yolo": "tags",
        "ocr": "ocr",
        "transcript": "subtitle",
    }
    results_ready = {}
    for eng in _configured:
        key = result_map.get(eng)
        if key and key in engine_to_result:
            results_ready[key] = engine_to_result[key][1]

    return {
        "video_id": video_id,
        "state": state,
        "jobs": jobs,
        "results_ready": results_ready,
    }


@router.post("/pipeline/single/start")
async def start_single_pipeline(data: dict):
    """Start AI pipeline for a single video.  No bg thread, no SSE — just dispatch."""
    video_id = data.get("video_id")
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id required")

    from ...services.pipeline_proxy import start_pipeline
    config = {}
    try:
        from ...services.pipeline_config import get_single_config
        config = get_single_config() or {}
    except Exception:
        pass

    engines = config.get("engines")

    try:
        result = start_pipeline(
            video_ids=[video_id],
            engines=engines,
            task_label="single",
        )
        task_id = result.get("task_id")
        if task_id:
            logger.info("start_single_pipeline: video=%s task=%s", video_id, task_id)
            return {"status": "started", "task_id": task_id}
        error_msg = result.get("error", "AI service unreachable")
        logger.error("start_single_pipeline failed for %s: %s", video_id, error_msg)
        return {"status": "error", "message": error_msg}
    except Exception as e:
        logger.exception("start_single_pipeline exception for %s", video_id)
        return {"status": "error", "message": str(e)}

@router.post("/pipeline/single/reset/{video_id}")
async def reset_single_asset(video_id: str):
    """Reset all AI engine jobs & SQLite results for a single asset."""
    import uuid
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob

    try:
        uid = uuid.UUID(video_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid video_id")

    session = sync_session_factory()
    try:
        count = session.query(AIEngineJob).filter(
            AIEngineJob.media_id == uid
        ).delete()
        session.commit()
        logger.info("reset_single_asset: deleted %d engine jobs for %s", count, video_id)
    except Exception as e:
        session.rollback()
        logger.error("reset_single_asset PG failed for %s: %s", video_id, e)
        session.close()
        return {"status": "error", "message": str(e)}
    session.close()

    # Clean up SQLite AI results + disk cache via AI service
    import httpx
    ai_url = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{ai_url}/pipeline/reset-asset/{video_id}")
            if resp.status_code == 200:
                logger.info("reset_single_asset: AI service cleaned data for %s", video_id)
            else:
                logger.warning("reset_single_asset: AI service returned %s for %s", resp.status_code, video_id)
    except Exception as e:
        logger.error("reset_single_asset: failed to call AI service for %s: %s", video_id, e)

    return {"status": "ok", "deleted_engine_jobs": count}

