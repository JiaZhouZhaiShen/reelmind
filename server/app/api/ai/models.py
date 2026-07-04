"""AI model management, HF token, legacy pipeline config."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

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




