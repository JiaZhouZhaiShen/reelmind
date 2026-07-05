"""Single-video AI processing, results query, SSE progress, stats."""
from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ...config import settings
from .shared import _running_tasks, _progress_queues, _pipeline_cancel_events, AITriggerRequest

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/process")
async def trigger_ai_pipeline(req: AITriggerRequest):
    """Trigger the full AI pipeline for a video (async, runs in background thread)."""
    video_id = req.video_id
    video_path = req.video_path

    if not os.path.isfile(video_path):
        raise HTTPException(status_code=400, detail=f"Video not found: {video_path}")

    task_id = f"ai_{video_id}"
    if task_id in _running_tasks and _running_tasks[task_id].get("status") == "running":
        return {"status": "already_running", "task_id": task_id}

    _running_tasks[task_id] = {"status": "queued", "progress": 0, "message": ""}

    def _progress(msg: str, pct: float):
        data = {"status": "running", "progress": pct, "message": msg}
        _running_tasks[task_id] = data
        # Push to SSE queue (thread-safe)
        q = _progress_queues.get(task_id)
        if q:
            q.put(data)
        # Publish progress to Redis for WebSocket
        try:
            import redis as _r
            r = _r.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
            )
            channel = f"ai:progress:{video_id}"
            r.publish(channel, json.dumps({
                "task_id": task_id,
                "status": "running",
                "progress": pct,
                "message": msg,
            }))
            r.close()
        except Exception:
            pass

    def _run():
        try:
            cancel_evt = threading.Event()
            _pipeline_cancel_events[task_id] = cancel_evt

            # Wrap progress callback to support cancellation
            _orig_progress = _progress
            def _cancellable_progress(msg: str, pct: float):
                if cancel_evt.is_set():
                    cancel_evt.clear()  # Prevent re-trigger in error handler
                _orig_progress(msg, pct)
            pipeline_cb = _cancellable_progress

            from app.services.pipeline_proxy import start_pipeline, wait_for_completion
            proxy_resp = start_pipeline(video_ids=[video_id])
            if proxy_resp.get("task_id"):
                result = wait_for_completion(proxy_resp["task_id"])
            else:
                result = {"status": "error", "message": proxy_resp.get("error", "AI service unreachable")}
            done_data = {
                "status": "done" if result.get("status") == "completed" else "error",
                "progress": 100 if result.get("status") == "completed" else 0,
                "message": result.get("message", "Pipeline complete"),
                "result": result,
            }
            _running_tasks[task_id] = done_data
            _pipeline_cancel_events.pop(task_id, None)
            q = _progress_queues.get(task_id)
            if q:
                q.put(done_data)
        except Exception as e:
            error_data = {"status": "error", "progress": 0, "message": str(e)}
            _running_tasks[task_id] = error_data
            q = _progress_queues.get(task_id)
            if q:
                q.put(error_data)
            _pipeline_cancel_events.pop(task_id, None)
            logger.exception("AI pipeline thread failed for %s", video_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "queued", "task_id": task_id, "video_id": video_id}



@router.get("/status/{video_id}")
async def get_ai_status(video_id: str):
    """Get AI processing status for a video."""
    task_id = f"ai_{video_id}"
    status = _running_tasks.get(task_id, {"status": "not_found", "progress": 0, "message": ""})
    return {"video_id": video_id, "task_id": task_id, **status}



@router.get("/subtitles/{video_id}")
async def get_subtitles(video_id: str):
    """Get subtitles (with speaker info) for a video."""
    try:
        from app.models.ai import Subtitle, get_ai_session
        session = get_ai_session()
        subs = session.query(Subtitle).filter(
            Subtitle.video_id == video_id
        ).order_by(Subtitle.start).all()
        session.close()
        return {
            "results": [{
                "id": s.id,
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "language": s.language,
                "speaker": s.speaker,
            } for s in subs],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/scenes/{video_id}")
async def get_scenes(video_id: str):
    """Get scene list with thumbnails and detected objects."""
    try:
        from app.models.ai import Scene, SceneTag, SceneOCR, get_ai_session
        session = get_ai_session()
        scenes = session.query(Scene).filter(
            Scene.video_id == video_id
        ).order_by(Scene.scene_index).all()

        result = []
        for sc in scenes:
            tags = session.query(SceneTag).filter(SceneTag.scene_id == sc.id).all()
            ocrs = session.query(SceneOCR).filter(SceneOCR.scene_id == sc.id).all()
            result.append({
                "id": sc.id,
                "scene_index": sc.scene_index,
                "start_time": sc.start_time,
                "end_time": sc.end_time,
                "thumbnail_path": sc.thumbnail_path or "",
                "tags": [{"label": t.label, "confidence": t.confidence, "count": t.count} for t in tags],
                "ocr_texts": [{"text": o.text, "confidence": o.confidence, "bbox": {
                    "x": o.bbox_x, "y": o.bbox_y, "w": o.bbox_w, "h": o.bbox_h,
                }} for o in ocrs],
            })
        session.close()
        return {"results": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/frames/{video_id}")
async def get_frames(video_id: str):
    """Get encoded frames for a video."""
    try:
        from app.models.ai import Frame, get_ai_session
        session = get_ai_session()
        frames = session.query(Frame).filter(
            Frame.video_id == video_id
        ).order_by(Frame.time_sec).all()
        session.close()
        return {
            "results": [{
                "id": f.id,
                "scene_id": f.scene_id,
                "time_sec": f.time_sec,
                "frame_path": f.frame_path or "",
            } for f in frames],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/speakers/{video_id}")
async def get_speakers(video_id: str):
    """Get unique speakers for a video."""
    try:
        from app.models.ai import Subtitle, get_ai_session
        session = get_ai_session()
        subs = session.query(Subtitle).filter(
            Subtitle.video_id == video_id,
            Subtitle.speaker.isnot(None),
        ).all()
        speakers = set()
        for s in subs:
            if s.speaker:
                speakers.add(s.speaker)
        session.close()
        return {"speakers": sorted(speakers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/{video_id}")
async def get_scene_tags(video_id: str):
    """Get all scene-level tags for a video (tag cloud)."""
    try:
        from app.models.ai import Scene, SceneTag, get_ai_session
        session = get_ai_session()
        scenes = session.query(Scene).filter(Scene.video_id == video_id).all()
        tag_counts = {}
        for sc in scenes:
            tags = session.query(SceneTag).filter(SceneTag.scene_id == sc.id).all()
            for t in tags:
                tag_counts[t.label] = tag_counts.get(t.label, 0) + t.count
        session.close()
        cloud = [{"label": k, "total_count": v} for k, v in sorted(tag_counts.items(), key=lambda x: -x[1])]
        return {"tags": cloud}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/tags/yolo/browse")
async def yolo_tags_browse(search: str = "", sort: str = "count"):
    """Aggregate scene_tags across all videos for YOLO tag browsing."""
    try:
        from app.models.ai import SceneTag, Scene, get_ai_session
        from sqlalchemy import func
        session = get_ai_session()
        query = session.query(
            SceneTag.label,
            func.count(SceneTag.id).label("total_count"),
            func.count(func.distinct(SceneTag.scene_id)).label("scene_count"),
            func.count(func.distinct(Scene.video_id)).label("video_count"),
            func.avg(SceneTag.confidence).label("avg_confidence"),
        ).join(Scene, Scene.id == SceneTag.scene_id)
        if search:
            query = query.filter(SceneTag.label.contains(search))
        query = query.group_by(SceneTag.label)
        if sort == "alpha":
            query = query.order_by(SceneTag.label)
        else:
            query = query.order_by(func.count(SceneTag.id).desc())
        rows = query.all()
        session.close()
        labels = [
            {"label": r.label, "total_count": r.total_count,
             "scene_count": r.scene_count, "video_count": r.video_count,
             "avg_confidence": round(float(r.avg_confidence), 4)}
            for r in rows
        ]
        return {"labels": labels, "total": len(labels)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/yolo/browse/{label}/videos")
async def yolo_tag_videos(label: str, page: int = 1, page_size: int = 200):
    """Get videos containing a specific YOLO label."""
    try:
        import uuid
        from app.models.ai import SceneTag, Scene, get_ai_session
        from app.models.asset import Asset
        from app.database import sync_session_factory
        from sqlalchemy import func
        ai_session = get_ai_session()
        # First, get total count
        total = ai_session.query(
            func.count(func.distinct(Scene.video_id))
        ).select_from(SceneTag
        ).join(Scene, Scene.id == SceneTag.scene_id
        ).filter(SceneTag.label == label
        ).scalar() or 0

        rows = ai_session.query(
            Scene.video_id,
            func.count(SceneTag.id).label("tag_count"),
            func.count(func.distinct(SceneTag.scene_id)).label("scene_count"),
        ).join(Scene, Scene.id == SceneTag.scene_id
        ).filter(SceneTag.label == label
        ).group_by(Scene.video_id
        ).order_by(func.count(SceneTag.id).desc()
        ).limit(page_size).offset((page - 1) * page_size).all()
        ai_session.close()
        video_ids = [uuid.UUID(r.video_id) for r in rows]
        pg_session = sync_session_factory()
        assets = pg_session.query(Asset).filter(Asset.id.in_(video_ids)).all()
        asset_map = {str(a.id): a for a in assets}
        pg_session.close()
        results = []
        for r in rows:
            a = asset_map.get(r.video_id)
            results.append({
                "id": r.video_id,
                "file_name": a.file_name if a else "",
                "duration": a.duration if a else 0,
                "thumbnail_path": a.thumbnail_path if a else "",
                "tag_count": r.tag_count,
                "scene_count": r.scene_count,
            })
        return {"assets": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/progress/{video_id}")
async def ai_progress_sse(video_id: str):
    """SSE endpoint: real-time pipeline progress for a video."""
    task_id = f"ai_{video_id}"

    """Return per-step counts from ai_engine_jobs."""
    try:
        from app.database import sync_session_factory
        from app.models.asset import Asset
        from app.models.ai_engine_job import AIEngineJob
        from sqlalchemy import func

        s = sync_session_factory()
        total_assets = s.query(Asset.id).filter(
            Asset.mime_type.like("video/%"),
            Asset.file_name.notlike("Rendered - %"),
        ).count()

        rows = s.query(
            AIEngineJob.engine_name,
            AIEngineJob.status,
            func.count(AIEngineJob.id),
        ).group_by(AIEngineJob.engine_name, AIEngineJob.status).all()

        counts: dict = {}
        for eng_name, st, cnt in rows:
            counts.setdefault(eng_name, {})[st] = cnt

        ENGINES = ("scene", "yolo", "ocr", "clip", "transcript", "diarization")
        result = {}
        for eng in ENGINES:
            ec = counts.get(eng, {})
            success = ec.get("completed", 0)
            error = ec.get("error", 0)
            pending = ec.get("pending", 0)
            result[f"{eng}_success"] = int(success)
            result[f"{eng}_error"] = int(error)
            result[f"{eng}_pending"] = int(pending)
            result[f"{eng}_done_count"] = int(success + error)

        subq = s.query(AIEngineJob.media_id).group_by(
            AIEngineJob.media_id,
        ).having(
            func.bool_and(AIEngineJob.status == "pending") == True
        ).subquery()
        raw = s.query(func.count()).select_from(subq).scalar() or 0
        result["total_pending"] = int(raw)
        result["total_assets"] = int(total_assets)

        s.close()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/stats")
async def get_ai_stats():
     """Get aggregated AI processing statistics from the AI database."""
     try:
         from app.models.ai import Video, Scene, Subtitle, SceneTag, SceneOCR, Frame, get_ai_session
         from sqlalchemy import func
         session = get_ai_session()
         videos_count = session.query(func.count(func.distinct(Video.id))).join(Scene, Scene.video_id == Video.id).scalar() or 0
         scenes_count = session.query(func.count(Scene.id)).scalar() or 0
         subs_count = session.query(func.count(Subtitle.id)).scalar() or 0
         tags_count = session.query(func.count(SceneTag.id)).scalar() or 0
         ocr_count = session.query(func.count(SceneOCR.id)).scalar() or 0
         frames_count = session.query(func.count(Frame.id)).scalar() or 0
         speakers_count = session.query(func.count(func.distinct(Subtitle.speaker))).filter(Subtitle.speaker.isnot(None)).scalar() or 0
         session.close()
         return {
             "videos_processed": videos_count,
             "total_scenes": scenes_count,
             "total_subtitles": subs_count,
             "total_tags": tags_count,
             "total_ocr_texts": ocr_count,
             "total_frames": frames_count,
             "speakers_found": speakers_count,
         }
     except Exception as e:
         logger.warning("Failed to get AI stats: %s", e)
         return {
             "videos_processed": 0,
             "total_scenes": 0,
             "total_subtitles": 0,
             "total_tags": 0,
             "total_ocr_texts": 0,
             "total_frames": 0,
             "speakers_found": 0,
         }



@router.get("/processed-assets")
async def get_processed_assets(page: int = Query(1, ge=1), page_size: int = Query(10000, ge=1, le=10000)):
    """Get assets that have been processed by AI, paginated."""
    from sqlalchemy import select as sa_select, func as sa_func
    from sqlalchemy.orm import selectinload
    from app.models.asset import Asset, AssetTag
    from app.models.ai import Video as AIVideo, Scene as AIScene, get_ai_session
    from app.database import async_session_factory
    from app.schemas.asset import AssetRead
    from fastapi import Query

    # Get video_ids that have at least one scene (truly processed videos)
    try:
        ai_session = get_ai_session()
        video_ids = [str(r[0]) for r in ai_session.query(AIVideo.id).join(AIScene, AIScene.video_id == AIVideo.id).distinct().all()]
        # Filter to only valid UUIDs (postgres UUID column rejects non-UUID values)
        import uuid
        video_ids = [v for v in video_ids if _is_valid_uuid(v)]
        ai_session.close()
    except Exception as e:
        logger.warning("Failed to query AI database: %s", e)
        video_ids = []

    if not video_ids:
        return {"items": [], "total": 0}

    # Fetch matching assets from main database
    async with async_session_factory() as session:
        # Count
        count_stmt = sa_select(sa_func.count(Asset.id)).where(Asset.id.in_(video_ids)).where(Asset.is_archived == False)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Fetch page
        stmt = (
            sa_select(Asset)
            .options(selectinload(Asset.tags).selectinload(AssetTag.tag))
            .where(Asset.id.in_(video_ids))
            .where(Asset.is_archived == False)
            .order_by(Asset.media_date.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        assets = result.unique().scalars().all()

    # Convert to response format
    items = []
    for a in assets:
        tag_list = []
        for at in a.tags:
            if at.tag and at.tag.name:
                tag_list.append(at.tag.name)
        items.append({
            "id": str(a.id),
            "library_id": str(a.library_id),
            "original_path": a.original_path,
            "file_name": a.file_name,
            "file_size": a.file_size,
            "file_hash": a.file_hash,
            "mime_type": a.mime_type,
            "width": a.width,
            "height": a.height,
            "duration": a.duration,
            "fps": a.fps,
            "codec": a.codec,
            "audio_codec": a.audio_codec,
            "has_audio": a.has_audio,
            "thumbnail_path": a.thumbnail_path,
            "proxy_path": a.proxy_path,
            "is_imported": a.is_imported,
            "is_archived": a.is_archived,
            "is_favorite": a.is_favorite,
            "notes": a.notes,
            "media_date": a.media_date.isoformat() if a.media_date else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "tags": tag_list,
            "exif": a.exif,
            "custom_metadata": a.custom_metadata,
        })

    return {"items": items, "total": total}


