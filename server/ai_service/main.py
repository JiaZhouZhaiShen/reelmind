"""ReelMind AI Service — standalone FastAPI for GPU-powered video processing.



Called by reelmind-server via HTTP.  Directly reads/writes shared DB + volumes.

"""

from __future__ import annotations

import json

import logging

import os

import threading

import time

import uuid as _uuid

import asyncio

from pathlib import Path



from fastapi import FastAPI, HTTPException

from pydantic import BaseModel, Field, field_validator



from log_setup import setup_logging; setup_logging("ai")

os.environ.setdefault("PADDLE_HOME", os.environ.get("MODEL_ROOT", "/data/reelmind/models") + "/paddle")

os.environ.setdefault("HF_HOME", os.environ.get("MODEL_ROOT", "/data/reelmind/models") + "/huggingface")

os.environ.setdefault("TORCH_HOME", os.environ.get("MODEL_ROOT", "/data/reelmind/models") + "/torch")

from configs import pipeline as pipeline_cfg

logger = logging.getLogger("ai_service")



app = FastAPI(title="ReelMind AI Service", version="0.1.0")



# ── In-memory task registry ──────────────────────────────────────────────────

_tasks: dict[str, dict] = {}

_task_cancel_events: dict[str, threading.Event] = {}

_active_threads: dict[str, threading.Thread] = {}

_task_lock = threading.Lock()



_model_states: dict[str, bool] = {

    "transnet": False, "yolo": False, "ocr": False,

    "clip": False, "whisper": False, "diarization": False,

}

_model_lock = threading.Lock()





def _load_model_instance(model_name: str) -> bool:

    success = False

    try:

        if model_name == "transnet":

            from services.scene_service import _load_transnet

            _load_transnet()

        elif model_name == "yolo":

            from services.yolo_service import _load_yolo

            _load_yolo()

        elif model_name == "ocr":

            from services.ocr_service import _load_ocr

            _load_ocr()

        elif model_name == "clip":

            from services.clip_service import _load_clip

            _load_clip()

        elif model_name == "whisper":

            from services.whisper_service import _get_whisper

            success = _get_whisper() is not None

        elif model_name == "diarization":

            from services.diarization_service import _load_diarization

            _load_diarization()

        else:

            success = False

            return success

        success = True

    except Exception as e:

        logger.error("Failed to load model '%s': %s", model_name, e)

    finally:

        with _model_lock:

            _model_states[model_name] = success

    return success





def _unload_model_instance(model_name: str) -> bool:

    try:

        if model_name == "transnet":

            from services.scene_service import _unload_transnet

            _unload_transnet()

        elif model_name == "yolo":

            from services.yolo_service import _unload_yolo

            _unload_yolo()

        elif model_name == "ocr":

            from services.ocr_service import _unload_ocr

            _unload_ocr()

        elif model_name == "clip":

            from services.clip_service import _unload_clip

            _unload_clip()

        elif model_name == "whisper":

            from services.whisper_service import _unload_whisper

            _unload_whisper()

        elif model_name == "diarization":

            from services.diarization_service import _unload_diarization

            _unload_diarization()

        else:

            return False

        return True

    except Exception as e:

        logger.error("Failed to unload model '%s': %s", model_name, e)

        return False





# ── Request models ───────────────────────────────────────────────────────────

VALID_ENGINES = frozenset({'scene', 'yolo', 'ocr', 'clip', 'transcript', 'diarization'})

class StartRequest(BaseModel):

    limit: int = Field(default=10, ge=0, le=10000)
    video_ids: list[str] | None = Field(default=None, max_length=10000)
    engines: list[str] | None = Field(default=None, max_length=6)
    task_label: str = "manual"
    filters: dict | None = None

    @field_validator('engines')
    @classmethod
    def validate_engines(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        invalid = set(v) - VALID_ENGINES
        if invalid:
            raise ValueError(f"Unknown engines: {invalid}. Valid engines: {VALID_ENGINES}")
        return v



class ConfigUpdate(BaseModel):

    config: dict

class ModuleConfigRequest(BaseModel):

    """Update a single module's config."""

    config: dict





# ── Pipeline runner in background thread ─────────────────────────────────────

def _run_pipeline_task(task_id: str, limit: int, video_ids: list[str] | None,
                        engines: list[str] | None = None,
                        task_label: str = "manual",
                        filters: dict | None = None):

    cancel_event = threading.Event()

    with _task_lock:

        _task_cancel_events[task_id] = cancel_event

        _tasks[task_id] = {"status": "running", "progress": 0, "step": "starting", "video": ""}



    def progress_callback(message: str, percent: float):

        if cancel_event.is_set():

            return  # caller should check this and bail

        with _task_lock:

            t = _tasks.get(task_id)

            if t:

                t["progress"] = round(percent, 1)

                t["step"] = message[:120]

                # Parse video name only from TransNetV2 messages starting with [filename]

                if "]" in message and message.startswith("["):

                    try:

                        vname = message.split("]")[0].lstrip("[").strip()

                        if vname:

                            t["video"] = vname

                    except Exception as e:
                        logger.warning("Failed to parse video name from progress: %s", e)



    try:

        from pipeline import AIPipeline, process_batch, get_pipeline_steps, set_pipeline_steps

    except ImportError:

        logger.error("Failed to import pipeline module")

        with _task_lock:

            _tasks[task_id] = {"status": "error", "error": "Pipeline module not found"}

        return



    try:

        if video_ids:

            # Batch mode: collect all assets then process in model-by-model batches

            from models.db import get_pg_session

            from models.db import Asset

            pg = get_pg_session()
            try:
                assets = []

                for vid in video_ids:

                    try:

                        asset = pg.query(Asset).filter(Asset.id == _uuid.UUID(vid)).first()

                        if asset and os.path.isfile(str(asset.original_path)):

                            assets.append(asset)

                    except Exception:

                        pass
            finally:
                pg.close()

            # Single video: use AIPipeline for proper per-engine status tracking
            if len(video_ids) == 1 and task_label == "single" and assets:
                vid = str(assets[0].id)
                vpath = str(assets[0].original_path)
                ai_pipeline = AIPipeline(
                    video_id=vid,
                    video_path=vpath,
                    progress_callback=progress_callback,
                    engines=engines,
                )
                ai_pipeline.run()
                results = {"status": "completed", "video_id": vid, "processed": 1}
            else:
                results = process_batch(pending_assets=assets,
                                        progress_callback=progress_callback,
                                        cancel_event=cancel_event,
                                        engines=engines,
                                        filters=filters)



        else:

            # Batch mode: query pending assets from DB then process

            from models.db import get_pg_session

            from models.db import Asset

            from app.models.ai_engine_job import AIEngineJob as _AEJ

            pg = get_pg_session()
            pending_ids = pg.query(_AEJ.media_id).filter(
                _AEJ.status == "running",
            ).distinct().limit(limit).all()
            pending = pg.query(Asset).filter(
                Asset.id.in_([pid[0] for pid in pending_ids])
            ).all() if pending_ids else []

            pg.close()

            results = process_batch(pending_assets=pending,
                                    progress_callback=progress_callback,
                                    cancel_event=cancel_event,
                                    engines=engines,
                                    filters=filters)



        status = "cancelled" if cancel_event.is_set() else "completed"

        with _task_lock:

            _tasks[task_id] = {

                "status": status,

                "progress": 100 if status == "completed" else _tasks[task_id].get("progress", 0),

                "results": results,

            }

            _task_cancel_events.pop(task_id, None)
            _active_threads.pop(task_id, None)



    except Exception as e:

        logger.exception("Pipeline task failed: %s", e)

        with _task_lock:

            _tasks[task_id] = {"status": "error", "error": str(e)}

        _task_cancel_events.pop(task_id, None)
        _active_threads.pop(task_id, None)



# ── Health + GPU ─────────────────────────────────────────────────────────────

async def _get_torch_ai_memory(timeout=2.0):

    """Query torch.cuda.memory_allocated in a thread with timeout."""

    try:

        import torch

        def _query():

            if torch.cuda.is_available():

                return torch.cuda.memory_allocated() / 1073741824

            return None

        return await asyncio.wait_for(asyncio.to_thread(_query), timeout=timeout)

    except Exception:

        return None



@app.get("/health")

async def health():
    """Lightweight health check - GPU info via torch.cuda.mem_get_info (no nvidia-smi subprocess)."""
    gpu = False
    total_gb = 0
    total_used_gb = 0
    try:
        import torch
        if torch.cuda.is_available():
            gpu = True
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            total_gb = round(total_bytes / 1073741824, 2)
            total_used_gb = round((total_bytes - free_bytes) / 1073741824, 2)
    except Exception as e:
        logger.warning("GPU health check failed: %s", e)
    return {
        "status": "ok",
        "gpu": gpu,
        "total_gb": total_gb,
        "total_used_gb": total_used_gb,
        "models": dict(_model_states),
    }

@app.post("/pipeline/start")

async def start_pipeline(req: StartRequest):

    task_id = str(_uuid.uuid4())

    thread = threading.Thread(

        target=_run_pipeline_task, args=(task_id, req.limit, req.video_ids, req.engines, req.task_label, req.filters),

        daemon=False

    )

    _active_threads[task_id] = thread

    thread.start()

    return {"task_id": task_id}



@app.get("/pipeline/status/{task_id}")

async def get_status(task_id: str):

    with _task_lock:

        task = _tasks.get(task_id)

    if task is None:

        raise HTTPException(status_code=404, detail="Task not found")

    return task



@app.post("/pipeline/cancel/{task_id}")

async def cancel_task(task_id: str):

    if task_id == "all":

        count = 0

        with _task_lock:

            for event in _task_cancel_events.values():

                event.set()

                count += 1

        for t in list(_active_threads.values()):

            t.join(timeout=5)

        _active_threads.clear()

        return {"cancelled": count}

    with _task_lock:

        event = _task_cancel_events.get(task_id)

    if event:

        event.set()

        t = _active_threads.pop(task_id, None)

        if t:

            t.join(timeout=5)

        return {"status": "cancelling"}

    return {"status": "not_found_or_already_done"}



@app.get("/pipeline/active")

async def get_active_tasks():

    """Return count and details of currently running pipeline tasks."""

    with _task_lock:

        active_tasks = [k for k, v in _tasks.items() if v.get("status") == "running"]

        active = len(active_tasks)

        result = {"active": active}

        if active_tasks:

            tid = active_tasks[0]

            t = _tasks[tid]

            result["task_id"] = tid

            result["progress"] = t.get("progress", 0)

            result["step"] = t.get("step", "")

            result["video"] = t.get("video", "")

        return result



@app.post("/pipeline/load/{model_name}")

async def load_model(model_name: str):

    if model_name not in _model_states:

        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    success = _load_model_instance(model_name)

    return {"status": "ok" if success else "error", "model": model_name, "loaded": success}





@app.post("/pipeline/unload/{model_name}")

async def unload_model(model_name: str):

    if model_name not in _model_states:

        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    success = _unload_model_instance(model_name)

    with _model_lock:

        _model_states[model_name] = not success

    return {"status": "ok" if success else "error", "model": model_name, "loaded": not success}







# ── Config ───────────────────────────────────────────────────────────────────

@app.get("/config")

async def get_config():

    from pipeline import get_pipeline_steps

    return {"config": get_pipeline_steps()}



@app.post("/config")

async def set_config(data: ConfigUpdate):

    from pipeline import set_pipeline_steps

    set_pipeline_steps(data.config)

    logger.info("Pipeline config updated: %s", data.config)

    return {"status": "saved", "config": data.config}





@app.get("/config/templates")

async def get_templates():

    from configs.templates import get_templates as _get_templates

    return {"templates": _get_templates(), "active": pipeline_cfg.template}





class ApplyTemplateRequest(BaseModel):

    template: str





@app.post("/config/apply-template")

async def apply_template(req: ApplyTemplateRequest):

    from configs.templates import apply_template

    try:

        result = apply_template(req.template)

        logger.info("Template applied: %s", req.template)

        return result

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))





@app.get("/config/{module}")

async def get_module_config(module: str):

    """Get a single module's config."""

    from configs import get

    cfg = get(module)

    if cfg is None:

        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")

    return {"module": module, "config": cfg.to_dict()}



@app.post("/config/{module}")

async def set_module_config(module: str, data: ModuleConfigRequest):

    """Update a single module's config."""

    from configs import get

    cfg = get(module)

    if cfg is None:

        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")

    cfg.from_dict(data.config)

    cfg.save()

    logger.info("Module config '%s' updated: %s", module, data.config)

    return {"status": "saved", "module": module, "config": cfg.to_dict()}





# ── Startup check ────────────────────────────────────────────────────────────



# ── CLIP semantic search ──────────────────────────────────────────────

class ClipSearchRequest(BaseModel):

    query: str

    top_k: int = 20



@app.post("/clip/search")

async def clip_search(req: ClipSearchRequest):

    from services.clip_service import search as clip_search_fn

    try:

        results = clip_search_fn(req.query, req.top_k)

        return {"results": results}

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))



@app.on_event("startup")

async def startup():

    logger.info("ReelMind AI Service starting...")

    # Create model cache directories on persistent volume

    for _d in [

        "/data/reelmind/models/huggingface",

        "/data/reelmind/models/torch",

        "/data/reelmind/models/hub",

        "/data/reelmind/models/paddle",

        "/data/reelmind/models/ultralytics",

    ]:

        os.makedirs(_d, exist_ok=True)

    # Symlink PaddleOCR hardcoded cache dir to persistent volume

    _ocr_dir = os.path.expanduser("~/.paddleocr")

    _paddle_cache = "/data/reelmind/models/paddle"

    if not os.path.islink(_ocr_dir) and not os.path.isdir(_ocr_dir):

        try:

            os.symlink(_paddle_cache, _ocr_dir, target_is_directory=True)

        except Exception as e:

            logger.warning("PaddleOCR symlink failed: %s", e)

    try:

        import torch

        logger.info("torch %s — CUDA available: %s", torch.__version__, torch.cuda.is_available())

        if torch.cuda.is_available():

            logger.info("GPU: %s — %d GB", torch.cuda.get_device_name(0),

                        round(torch.cuda.get_device_properties(0).total_memory / 1073741824))

    except Exception:
        pass


@app.post("/pipeline/reset-asset/{video_id}")

async def reset_asset(video_id: str):

    """Delete all AI analysis data for a single video from SQLite + disk."""

    from models.ai_models import Video, get_ai_session

    import shutil

    from pathlib import Path

 

    # Delete from SQLite (cascade handles scenes, scene_tags, scene_ocr, frames, subtitles)

    ai_s = get_ai_session()

    try:

        video = ai_s.query(Video).filter(Video.id == video_id).first()

        if video:

            ai_s.delete(video)

            ai_s.commit()

            logger.info("Deleted SQLite records for video %s", video_id)

        else:

            logger.info("No SQLite record found for video %s", video_id)

    except Exception as e:

        logger.error("Failed to delete SQLite data for %s: %s", video_id, e)

        ai_s.rollback()

    finally:

        ai_s.close()

 

    # Delete scene thumbnails from disk

    cache_root = os.environ.get("CACHE_ROOT", "/data/reelmind/cache")

    thumb_dir = Path(cache_root) / "scene-thumbnails" / video_id

    if thumb_dir.exists():

        shutil.rmtree(str(thumb_dir))

        logger.info("Deleted scene thumbnails: %s", thumb_dir)

    # Reset PG engine jobs so pipeline does not skip re-processing
    try:
        from job_helpers import reset_jobs_for_asset
        reset_jobs_for_asset(video_id)
    except Exception as e:
        logger.warning("Failed to reset PG engine jobs for %s: %s", video_id, e)

    return {"status": "ok", "video_id": video_id}
