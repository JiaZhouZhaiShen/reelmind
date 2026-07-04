"""ReelMind AI Task API -- trigger and query AI processing."""

from __future__ import annotations

import json
import logging
import queue as _queue
import threading
import time
from pydantic import BaseModel

from ...config import settings

logger = logging.getLogger(__name__)


class AITriggerRequest(BaseModel):
    video_id: str
    video_path: str


class AISearchRequest(BaseModel):
    query: str
    top_k: int = 50

# In-memory task tracking
_running_tasks: dict[str, dict] = {}
_progress_queues: dict[str, _queue.Queue] = {}
_pipeline_cancel_events: dict[str, threading.Event] = {}
_orchestration_lock = threading.Lock()


_scan_state: dict = {
    "status": "idle",
    "total": 0,
    "completed": 0,
    "failed": 0,
    "paused": False,
    "videos": [],
    "current_video": None,
    "current_stage": "",
    "current_progress": 0,
    "overall_progress": 0,
    "message": "",
}
_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None
_scan_stop_event = threading.Event()


def _publish_scan_event(data: dict):
    try:
        import redis as _r
        r = _r.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        r.publish("ai:scan-events", json.dumps(data))
        r.close()
    except Exception:
        pass

def _mark_checkpoint_cancelled(batch_id: str, reason: str = "") -> None:
    """Mark a checkpoint as cancelled (used when orchestration can't proceed)."""
    from app.database import sync_session_factory
    from app.models.batch_checkpoint import BatchCheckpoint
    import uuid
    session = sync_session_factory()
    try:
        uid = uuid.UUID(batch_id)
        cp = session.query(BatchCheckpoint).filter(BatchCheckpoint.id == uid).first()
        if cp:
            cp.status = "cancelled"
            session.commit()
            logger.info("_mark_checkpoint_cancelled: %s %s", batch_id, reason)
    except Exception:
        logger.exception("_mark_checkpoint_cancelled failed for %s", batch_id)
    finally:
        session.close()

def _orchestrate_batch(task_label: str, config: dict, batch_id: str | None = None, media_ids: list[str] | None = None, event_id: int | None = None) -> str | None:
    """分批多次：取全部 pending → 分 chunk → 逐批调 AI 容器 → checkpoint。

    在后台线程中执行。Server 只负责编排，不做计算（铁律 ①）。
    文件过滤全部在 AI 容器的 process_batch() 入口做（铁律 ⑮）。
    如果传入了 batch_id，则使用已有 checkpoint（由调用方创建）。
    """
    if not _orchestration_lock.acquire(blocking=False):
        logger.info("_orchestrate_batch[%s]: orchestration in progress, deferring event_id=%s", task_label, event_id)
        return None

    # Mark event as consumed now that we hold the lock
    if event_id is not None:
        try:
            from app.database import sync_session_factory
            from app.models.orchestration_event import OrchestrationEvent
            s = sync_session_factory()
            try:
                evt = s.query(OrchestrationEvent).filter(OrchestrationEvent.id == event_id).first()
                if evt and not evt.consumed:
                    evt.consumed = True
                    s.commit()
            finally:
                s.close()
        except Exception:
            logger.exception("_orchestrate_batch[%s]: failed to consume event %s", task_label, event_id)
    from app.database import sync_session_factory
    from app.core.job_helpers import get_pending_media_ids
    from app.models.batch_checkpoint import BatchCheckpoint
    from app.services.pipeline_proxy import start_pipeline, wait_for_completion

    engines = config.get("engines")
    batch_size = config.get("batch_size", 100)
    filters = config.get("filters", {})

    session = sync_session_factory()
    try:
        if media_ids is not None:
            all_pending = media_ids
        else:
            _max_fs = filters.get("max_file_size_mb", 0)
            _max_dur = filters.get("max_duration_minutes", 0)
            all_pending = get_pending_media_ids(session, engines, _max_fs, _max_dur)
        if not all_pending:
            logger.info("_orchestrate_batch[%s]: no pending videos", task_label)
            if batch_id:
                checkpoint = session.query(BatchCheckpoint).filter(BatchCheckpoint.id == batch_id).first()
                if checkpoint:
                    checkpoint.status = "completed"
                    checkpoint.processed = 0
                    session.commit()
            return batch_id

        total = len(all_pending)
        # limit chunks so manual batch doesn't loop over all 22036 videos
        max_chunks = config.get("max_chunks")
        if max_chunks:
            total = min(total, max_chunks * batch_size)

        # Use existing checkpoint if batch_id provided, otherwise create one
        if batch_id:
            checkpoint = session.query(BatchCheckpoint).filter(BatchCheckpoint.id == batch_id).first()
            if not checkpoint:
                logger.error("_orchestrate_batch[%s]: checkpoint %s not found", task_label, batch_id)
                return None
        else:
            checkpoint = BatchCheckpoint(
                task_label=task_label,
                engines=engines or [],
                total_videos=total,
                batch_size=batch_size,
                processed=0,
                status="running",
            )
            session.add(checkpoint)
            session.commit()
            batch_id = str(checkpoint.id)

        logger.info("_orchestrate_batch[%s]: checkpoint=%s total=%d batch_size=%d",
                     task_label, batch_id, total, batch_size)

        for i in range(0, total, batch_size):
            chunk = all_pending[i:i + batch_size]
            processed = min(i + batch_size, total)
            chunk_num = i // batch_size + 1
            total_chunks = (total + batch_size - 1) // batch_size
            logger.info("_orchestrate_batch[%s]: chunk %d/%d (%d videos)",
                         task_label, chunk_num, total_chunks, len(chunk))
            # Store current chunk IDs for progress tracking
            session.query(BatchCheckpoint).filter(
                BatchCheckpoint.id == checkpoint.id
            ).update({"current_chunk_ids": chunk})
            session.commit()

            result = start_pipeline(
                limit=len(chunk),
                video_ids=chunk,
                engines=engines,
                task_label=task_label,
                filters=filters,
            )
            task_id = result.get("task_id")
            final_status = {"status": "unknown"}
            if task_id:
                final_status = wait_for_completion(task_id)
                if final_status.get("status") == "error":
                    logger.warning("_orchestrate_batch[%s]: chunk %d errored: %s",
                                  task_label, chunk_num, final_status)

            # ── Mark chunk's engine jobs as completed so orchestrator can track progress ──
            if final_status.get("status") == "completed":
                from app.models.ai_engine_job import AIEngineJob
                from sqlalchemy import func as sa_func
                updated = session.query(AIEngineJob).filter(
                    AIEngineJob.media_id.in_(chunk),
                    AIEngineJob.engine_name.in_(engines or []),
                    AIEngineJob.status == "running"
                ).update({
                    "status": "completed",
                    "completed_at": sa_func.now(),
                }, synchronize_session=False)
                session.commit()
                if updated:
                    logger.info(
                        "_orchestrate_batch[%s]: chunk %d done, marked %d engine jobs completed",
                        task_label, chunk_num, updated,
                    )

            session.query(BatchCheckpoint).filter(
                BatchCheckpoint.id == checkpoint.id
            ).update({"processed": processed})
            session.commit()
            # Store per-engine completion progress
            from app.models.ai_engine_job import AIEngineJob
            from sqlalchemy import func as sa_func
            engine_counts = session.query(
                AIEngineJob.engine_name,
                AIEngineJob.status,
                sa_func.count(AIEngineJob.id)
            ).filter(
                AIEngineJob.media_id.in_(chunk),
                AIEngineJob.engine_name.in_(engines or [])
            ).group_by(AIEngineJob.engine_name, AIEngineJob.status).all()
            progress = {}
            for eng_name, status, cnt in engine_counts:
                if eng_name not in progress:
                    progress[eng_name] = 0
                if status == "completed":
                    progress[eng_name] = cnt
            session.query(BatchCheckpoint).filter(
                BatchCheckpoint.id == checkpoint.id
            ).update({
                "engine_progress": progress
            })
            session.commit()
            # Check if cancelled between chunks
            _fresh = session.query(BatchCheckpoint.status).filter(
                BatchCheckpoint.id == checkpoint.id
            ).scalar()
            if _fresh == "cancelled":
                logger.warning("_orchestrate_batch[%s]: checkpoint cancelled, stopping early (%d/%d)",
                               task_label, processed, total)
                break
            logger.info("_orchestrate_batch[%s]: checkpoint updated %d/%d",
                         task_label, processed, total)

        session.query(BatchCheckpoint).filter(
            BatchCheckpoint.id == checkpoint.id
        ).update({"status": "completed", "processed": total})
        session.commit()
        logger.info("_orchestrate_batch[%s]: completed %d videos", task_label, total)
        return batch_id

    except Exception:
        logger.exception("_orchestrate_batch[%s] failed", task_label)
        if session:
            try:
                session.rollback()
            except Exception:
                pass
            try:
                cp = locals().get('checkpoint')
                if cp and cp.id:
                    session.query(BatchCheckpoint).filter(
                        BatchCheckpoint.id == cp.id
                    ).update({"status": "failed"})
                    session.commit()
            except Exception:
                pass
        return None
    finally:
        try:
            _orchestration_lock.release()
        except RuntimeError:
            pass
        if session:
            session.close()



def _cleanup_stale_checkpoints():
    """On startup, clean up checkpoints left 'running' from a previous crash/restart."""
    from app.database import sync_session_factory
    from app.models.batch_checkpoint import BatchCheckpoint
    from app.models.ai_engine_job import AIEngineJob
    session = sync_session_factory()
    try:
        stale = session.query(BatchCheckpoint).filter(
            BatchCheckpoint.status == "running"
        ).all()
        for cp in stale:
            # Check if there are actually still running jobs for this checkpoint
            ids = cp.current_chunk_ids or []
            has_running = False
            if ids:
                has_running = session.query(AIEngineJob).filter(
                    AIEngineJob.media_id.in_(ids),
                    AIEngineJob.status == "running"
                ).first() is not None
            if not has_running:
                cp.status = "failed"
                logger.warning("Startup cleanup: marked stale checkpoint %s as failed", cp.id)
        session.commit()
    except Exception:
        logger.exception("Startup checkpoint cleanup failed")
        session.rollback()
    finally:
        session.close()

