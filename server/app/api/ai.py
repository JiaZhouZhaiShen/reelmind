"""ReelMind AI Task API -- trigger and query AI processing."""

from __future__ import annotations

import asyncio
import gc
import time
import importlib
import json
import logging
import os
import queue as _queue
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Processing"])


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

            from ..services.pipeline_proxy import start_pipeline, wait_for_completion
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
        from ..models.ai import Subtitle, get_ai_session
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
        from ..models.ai import Scene, SceneTag, SceneOCR, get_ai_session
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
        from ..models.ai import Frame, get_ai_session
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
        from ..models.ai import Subtitle, get_ai_session
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
        from ..models.ai import Scene, SceneTag, get_ai_session
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

@router.get("/models/status")
async def get_ai_model_status():
    """Get real runtime status of all AI models + GPU memory info (proxied to AI service)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://reelmind-ai:2589/health")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Failed to get AI service health: %s", e)
        return {"models": {}, "gpu": {"used": 0, "total": 0, "percent": 0}}

    models = data.get("models", {})
    total_gb = data.get("total_gb", 0)
    total_used_gb = data.get("total_used_gb", 0)
    gpu_percent = int((total_used_gb / total_gb * 100)) if total_gb > 0 else 0

    return {
        "models": models,
        "gpu": {
            "used": round(total_used_gb, 2),
            "total": round(total_gb, 1),
            "percent": min(gpu_percent, 100),
        },
    }



@router.post("/models/load/{model_name}")
async def load_ai_model(model_name: str):
    """Load a specific AI model for persistent use (proxied to AI service)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"http://reelmind-ai:2589/pipeline/load/{model_name}")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/unload/{model_name}")
async def unload_ai_model(model_name: str):
    """Unload a specific AI model, freeing GPU memory (proxied to AI service)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"http://reelmind-ai:2589/pipeline/unload/{model_name}")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/config")
async def get_pipeline_config_legacy():
    """Deprecated: use GET /pipeline/manual/config instead"""
    from ..services.pipeline_config import get_manual_config
    cfg = get_manual_config()
    engines = cfg.get("engines", [])
    return {"config": {
        "scene": {"enabled": "scene" in engines},
        "yolo": {"enabled": "yolo" in engines},
        "ocr": {"enabled": "ocr" in engines},
        "clip": {"enabled": "clip" in engines},
        "whisper": {"enabled": "whisper" in engines},
        "diarization": {"enabled": "diarization" in engines},
        "pipeline": {"batch_size": cfg.get("batch_size", 100)},
    }}



@router.post("/pipeline/config")
async def set_pipeline_config(data: dict):
    """Set which pipeline steps to run (proxied to AI service)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post("http://reelmind-ai:2589/config", json=data)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Failed to set pipeline config on AI service: %s", e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

    except Exception as e:
        logger.warning("Failed to get pipeline templates from AI service: %s", e)
        return JSONResponse(content={"templates": {}, "active": "full"}, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/models/token")
async def get_hf_token_status():
    """Check if HUGGINGFACE_TOKEN is set (env or persisted file)."""
    from pathlib import Path
    token = os.environ.get("HUGGINGFACE_TOKEN", "")
    if not token:
        root = os.environ.get("DATA_ROOT", str(Path.home() / ".reelmind"))
        token_file = Path(root) / "hf_token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                os.environ["HUGGINGFACE_TOKEN"] = token
    return {"set": bool(token)}


@router.post("/models/token")
async def set_hf_token(data: dict):
    """Set HUGGINGFACE_TOKEN in process env + persist to disk."""
    from pathlib import Path
    token = data.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    os.environ["HUGGINGFACE_TOKEN"] = token
    root = os.environ.get("DATA_ROOT", str(Path.home() / ".reelmind"))
    token_file = Path(root) / "hf_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    logger.info("HUGGINGFACE_TOKEN set from UI and persisted to %s", token_file)
    return {"status": "saved", "set": True}




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
         from ..models.ai import Video, Scene, Subtitle, SceneTag, SceneOCR, Frame, get_ai_session
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
    from ..models.asset import Asset, AssetTag
    from ..models.ai import Video as AIVideo, Scene as AIScene, get_ai_session
    from ..database import async_session_factory
    from ..schemas.asset import AssetRead
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


@router.get("/auto-run/status")
async def get_auto_run_status_compat():
    """Backward-compat stub — returns auto pipeline config as status."""
    from ..services.pipeline_config import get_auto_config
    cfg = get_auto_config()
    return {
        "enabled": cfg.get("enabled", False),
        "status": "running" if cfg.get("enabled", False) else "idle",
        "last_run": None,
        "idle_checks": 0,
        "config": cfg,
    }




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


@router.post("/scan-library")
async def scan_library():
    global _scan_thread
    with _scan_lock:
        if _scan_state["status"] in ("running",):
            return {"status": "already_running", "message": "A scan is already in progress"}
        _scan_state["status"] = "running"
        _scan_state["paused"] = False
        _scan_state["completed"] = 0
        _scan_state["failed"] = 0
        _scan_state["message"] = ""
        _scan_state["current_video"] = None
        _scan_state["current_stage"] = ""
        _scan_state["current_progress"] = 0
        _scan_state["overall_progress"] = 0
        _scan_stop_event.clear()

    def _run_scan():
        try:
            from pathlib import Path

            library_path = Path(settings.DATA_ROOT) / "uploaded"
            if not library_path.exists():
                with _scan_lock:
                    _scan_state["status"] = "error"
                    _scan_state["message"] = f"Library path not found: {library_path}"
                _publish_scan_event({"type": "error", "message": str(library_path)})
                return

            video_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".3gp", ".ogv", ".mxf")
            video_files = []
            for ext in video_exts:
                video_files.extend(library_path.rglob(f"*{ext}"))

            if not video_files:
                with _scan_lock:
                    _scan_state["status"] = "completed"
                    _scan_state["total"] = 0
                    _scan_state["message"] = "No video files found in library"
                _publish_scan_event({"type": "complete", "total": 0})
                return

            video_files.sort(key=lambda p: p.name)
            import uuid as _uuid
            videos = []
            for vf in video_files:
                vid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(vf)))
                videos.append({"video_id": vid, "file_path": str(vf), "file_name": vf.name})

            with _scan_lock:
                _scan_state["total"] = len(videos)
                _scan_state["videos"] = videos
                _scan_state["completed"] = 0
                _scan_state["failed"] = 0

            _publish_scan_event({"type": "start", "total": len(videos), "videos": [v["file_name"] for v in videos]})

            from ..services.pipeline_proxy import start_pipeline, wait_for_completion

            for idx, video_info in enumerate(videos):
                if _scan_stop_event.is_set():
                    with _scan_lock:
                        _scan_state["status"] = "paused" if _scan_state["paused"] else "idle"
                        _scan_state["message"] = "Scan paused by user"
                    _publish_scan_event({"type": "paused"})
                    return

                with _scan_lock:
                    _scan_state["current_video"] = {"video_id": video_info["video_id"], "file_name": video_info["file_name"]}
                    _scan_state["current_stage"] = "Queued"
                    _scan_state["current_progress"] = 0

                _publish_scan_event({"type": "video_start", "file_name": video_info["file_name"], "index": idx + 1, "total": len(videos)})

                try:
                    def _make_cb(video_name):
                        def _cb(msg: str, pct: float):
                            with _scan_lock:
                                _scan_state["current_stage"] = msg
                                _scan_state["current_progress"] = pct
                            _publish_scan_event({"type": "video_progress", "file_name": video_name, "stage": msg, "progress": pct})
                        return _cb

                    vpath = video_info.get("file_path", "")
                    if not vpath:
                        # Fallback: query file_path from DB
                        try:
                            from ..database import sync_session_factory
                            from ..models.asset import Asset
                            db = sync_session_factory()
                            asset = db.query(Asset).filter(Asset.id == uuid.UUID(video_info["video_id"])).first()
                            vpath = asset.original_path if asset else ""
                            db.close()
                        except Exception:
                            pass
                    _task3 = start_pipeline(video_ids=[video_info["video_id"]]).get("task_id")
                    if _task3:
                        result = wait_for_completion(_task3)
                    else:
                        result = {"status": "error"}

                    with _scan_lock:
                        if result.get("status") == "completed":
                            _scan_state["completed"] += 1
                        else:
                            _scan_state["failed"] += 1
                        total_done = _scan_state["completed"] + _scan_state["failed"]
                        _scan_state["overall_progress"] = int((total_done / _scan_state["total"]) * 100)

                    _publish_scan_event({"type": "video_end", "file_name": video_info["file_name"], "status": result.get("status", "error"), "completed": _scan_state["completed"], "failed": _scan_state["failed"], "overall_progress": _scan_state["overall_progress"]})

                except Exception as e:
                    with _scan_lock:
                        _scan_state["failed"] += 1
                    _publish_scan_event({"type": "video_error", "file_name": video_info["file_name"], "error": str(e)})
                    logger.exception("AI pipeline failed for %s", video_info["file_name"])

            with _scan_lock:
                _scan_state["current_video"] = None
                _scan_state["current_stage"] = ""
                _scan_state["status"] = "completed"
                _scan_state["overall_progress"] = 100
                _scan_state["message"] = f"Scan complete: {_scan_state['completed']} done, {_scan_state['failed']} failed"

            _publish_scan_event({"type": "complete", "completed": _scan_state["completed"], "failed": _scan_state["failed"], "total": _scan_state["total"]})

        except Exception as e:
            with _scan_lock:
                _scan_state["status"] = "error"
                _scan_state["message"] = str(e)
            _publish_scan_event({"type": "error", "message": str(e)})
            logger.exception("Scan library thread failed")

    _scan_thread = threading.Thread(target=_run_scan, daemon=True)
    _scan_thread.start()
    return {"status": "started", "message": "Library scan started"}


@router.post("/scan-pause")
async def scan_pause():
    with _scan_lock:
        if _scan_state["status"] != "running":
            return {"status": "error", "message": "No scan is running"}
        _scan_state["paused"] = True
        _scan_stop_event.set()
    return {"status": "pausing", "message": "Scan will pause after current video"}


@router.post("/scan-resume")
async def scan_resume():
    global _scan_thread
    with _scan_lock:
        if _scan_state["status"] != "paused" and not _scan_state["paused"]:
            return {"status": "error", "message": "No paused scan to resume"}
        if _scan_state["status"] == "paused":
            _scan_state["status"] = "running"
            _scan_state["paused"] = False
            _scan_stop_event.clear()
        else:
            _scan_state["status"] = "running"
            _scan_state["paused"] = False
            _scan_stop_event.clear()

    def _resume():
        try:
            with _scan_lock:
                videos = _scan_state.get("videos", [])
                processed = _scan_state["completed"] + _scan_state["failed"]
                remaining = videos[processed:]
            if not remaining:
                with _scan_lock:
                    _scan_state["status"] = "completed"
                    _scan_state["message"] = "No remaining videos to process"
                return

            from ..services.pipeline_proxy import start_pipeline, wait_for_completion

            for idx, video_info in enumerate(remaining):
                if _scan_stop_event.is_set():
                    with _scan_lock:
                        _scan_state["status"] = "paused"
                        _scan_state["message"] = "Scan paused again"
                    return

                with _scan_lock:
                    _scan_state["current_video"] = {"video_id": video_info["video_id"], "file_name": video_info["file_name"]}
                    _scan_state["current_stage"] = "Queued"

                _publish_scan_event({"type": "video_start", "file_name": video_info["file_name"], "index": processed + idx + 1, "total": _scan_state["total"]})

                try:
                    def _make_cb(video_name):
                        def _cb(msg: str, pct: float):
                            with _scan_lock:
                                _scan_state["current_stage"] = msg
                                _scan_state["current_progress"] = pct
                            _publish_scan_event({"type": "video_progress", "file_name": video_name, "stage": msg, "progress": pct})
                        return _cb

                    vpath = video_info.get("file_path", "")
                    if not vpath:
                        # Fallback: query file_path from DB
                        try:
                            from ..database import sync_session_factory
                            from ..models.asset import Asset
                            db = sync_session_factory()
                            asset = db.query(Asset).filter(Asset.id == uuid.UUID(video_info["video_id"])).first()
                            vpath = asset.original_path if asset else ""
                            db.close()
                        except Exception:
                            pass
                    _task4 = start_pipeline(video_ids=[video_info["video_id"]]).get("task_id")
                    if _task4:
                        result = wait_for_completion(_task4)
                    else:
                        result = {"status": "error"}

                    with _scan_lock:
                        if result.get("status") == "completed":
                            _scan_state["completed"] += 1
                        else:
                            _scan_state["failed"] += 1
                        total_done = _scan_state["completed"] + _scan_state["failed"]
                        _scan_state["overall_progress"] = int((total_done / _scan_state["total"]) * 100)

                except Exception as e:
                    with _scan_lock:
                        _scan_state["failed"] += 1
                    _publish_scan_event({"type": "video_error", "file_name": video_info["file_name"], "error": str(e)})

            with _scan_lock:
                _scan_state["current_video"] = None
                _scan_state["status"] = "completed"
                _scan_state["overall_progress"] = 100
                _scan_state["message"] = f"Scan complete: {_scan_state['completed']} done, {_scan_state['failed']} failed"

            _publish_scan_event({"type": "complete", "completed": _scan_state["completed"], "failed": _scan_state["failed"], "total": _scan_state["total"]})

        except Exception as e:
            with _scan_lock:
                _scan_state["status"] = "error"
                _scan_state["message"] = str(e)
            _publish_scan_event({"type": "error", "message": str(e)})

    _scan_thread = threading.Thread(target=_resume, daemon=True)
    _scan_thread.start()
    return {"status": "resumed", "message": "Scan resumed"}


@router.get("/scan-status")
async def get_scan_status():
    with _scan_lock:
        return dict(_scan_state)


from fastapi.responses import StreamingResponse, JSONResponse

@router.get("/scan-events")
async def scan_events_sse():
    import asyncio

    async def event_stream():
        try:
            import redis.asyncio as redis_async
            r = redis_async.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe("ai:scan-events")
            try:
                while True:
                    msg = await pubsub.get_message(timeout=5.0)
                    if msg and msg["type"] == "message":
                        yield f"data: {msg['data']}\n\n"
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe("ai:scan-events")
                await pubsub.close()
                await r.close()
        except Exception as e:
            yield f"data: {{\"type\": \"error\", \"message\": \"{e}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

# ═══════════════════════════════════════════════════════════════════════════════
# P2: _orchestrate_batch — 分批多次引擎 (手动/自动共用)
# ═══════════════════════════════════════════════════════════════════════════════

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


def _orchestrate_batch(task_label: str, config: dict, batch_id: str | None = None, media_ids: list[str] | None = None) -> str | None:
    """分批多次：取全部 pending → 分 chunk → 逐批调 AI 容器 → checkpoint。

    在后台线程中执行。Server 只负责编排，不做计算（铁律 ①）。
    文件过滤全部在 AI 容器的 process_batch() 入口做（铁律 ⑮）。
    如果传入了 batch_id，则使用已有 checkpoint（由调用方创建）。
    """
    if not _orchestration_lock.acquire(blocking=False):
        logger.warning("_orchestrate_batch[%s]: 另一个 orchestration 正在运行，跳过", task_label)
        if batch_id is not None:
            _mark_checkpoint_cancelled(batch_id, reason="another orchestration is running")
        return None
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
            all_pending = get_pending_media_ids(session, engines)
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


# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/pipeline/manual/config")
async def get_manual_pipeline_config():
    """Get manual batch pipeline configuration."""
    from ..services.pipeline_config import get_manual_config
    return {"config": get_manual_config()}


@router.post("/pipeline/manual/config")
async def set_manual_pipeline_config(data: dict):
    """Save manual batch pipeline configuration."""
    from ..services.pipeline_config import save_manual_config
    save_manual_config(data.get("config", data))
    logger.info("Manual pipeline config saved: %s", data)
    return {"status": "saved"}


@router.post("/pipeline/manual/start")
async def start_manual_batch():
    """Start a manual batch pipeline run — creates checkpoint + background thread."""
    from ..services.pipeline_config import get_manual_config
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
        all_pending = get_pending_media_ids(session, engines)
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
    from ..services.pipeline_config import get_auto_config
    return {"config": get_auto_config()}


@router.post("/pipeline/auto/config")
async def set_auto_pipeline_config(data: dict):
    """Save auto batch pipeline configuration (JSON + PG double-write).

    P3: Orchestrator reads from PG, so config must be written to both locations.
    """
    from ..services.pipeline_config import save_auto_config
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
    from ..services.pipeline_config import get_single_config
    return {"config": get_single_config()}


@router.post("/pipeline/single/config")
async def set_single_pipeline_config(data: dict):
    """Save single video pipeline configuration."""
    from ..services.pipeline_config import save_single_config
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


@router.get("/pending-count")
async def get_pending_asset_count(engines: str = Query(None, description="Comma-separated engine names to scope pending count, e.g. scene,yolo")):
    """Return per-engine pending/success/error counts for AIPendingOverview.
    Optional ?engines=scene,yolo returns selected_pending (union-distinct)."""
    from app.database import sync_session_factory
    from app.core.job_helpers import get_pending_count_by_engine, get_success_error_count_by_engine, ENGINES
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import text

    session = sync_session_factory()
    try:
        total_assets = session.query(AIEngineJob.media_id).distinct().count()

        sql = text("""
            SELECT COUNT(*) FROM (
                SELECT media_id FROM ai_engine_jobs
                GROUP BY media_id
                HAVING COUNT(CASE WHEN status != 'pending' THEN 1 END) = 0
            ) sub
        """)
        total_pending = session.execute(sql).scalar() or 0

        pending_by_engine = get_pending_count_by_engine(session)
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
                    SELECT COUNT(DISTINCT media_id) FROM ai_engine_jobs
                    WHERE engine_name = ANY(:engines) AND status = 'pending'
                """)
                selected_pending = session.execute(
                    sql_selected, {"engines": engine_list}
                ).scalar() or 0
                result["selected_pending"] = selected_pending

        return result
    finally:
        session.close()


def start_event_scanner():
    """Start background thread to poll orchestration_events and dispatch auto batches."""
    from app.database import sync_session_factory
    from app.models.orchestration_event import OrchestrationEvent
    from app.services.pipeline_config import get_auto_config
    import time

    def _poll_events():
        logger.info("Event scanner started (polls every 5s)")
        while True:
            try:
                session = sync_session_factory()
                try:
                    events = session.query(OrchestrationEvent).filter(
                        OrchestrationEvent.event_type == "chunk_ready",
                        OrchestrationEvent.consumed == False,
                    ).order_by(OrchestrationEvent.id).limit(5).all()
                    for event in events:
                        event.consumed = True
                        session.commit()
                        data = event.data or {}
                        media_ids = data.get("media_ids", [])
                        batch_id = data.get("batch_id") or str(event.batch_id or "")
                        if not media_ids:
                            continue
                        auto_config = get_auto_config()
                        if not auto_config.get("enabled", False):
                            logger.info(
                                "Event scanner: auto mode disabled, skipping chunk batch=%s media_ids=%d",
                                batch_id, len(media_ids),
                            )
                            continue
                        logger.info(
                            "Event scanner: dispatching chunk batch=%s media_ids=%d",
                            batch_id, len(media_ids),
                        )
                        threading.Thread(
                            target=_orchestrate_batch,
                            args=("auto", auto_config, None, media_ids),
                            daemon=True,
                        ).start()
                finally:
                    session.close()
            except Exception:
                logger.exception("Event scanner error")
            time.sleep(5)

    t = threading.Thread(target=_poll_events, daemon=True, name="event-scanner")
    t.start()
    logger.info("Event scanner thread started")

# Start the event scanner on module load so auto-dispatch works
start_event_scanner()
