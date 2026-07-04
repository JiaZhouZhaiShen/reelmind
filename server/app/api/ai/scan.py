"""Library scanning, auto-run, pending count, SSE event streaming."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from ...config import settings
from .shared import (_scan_state, _scan_lock, _scan_thread, _scan_stop_event,
    _publish_scan_event)

logger = logging.getLogger(__name__)

router = APIRouter()

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

