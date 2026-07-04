"""AI module configuration (scene, yolo, ocr, clip, whisper, diarization)."""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException

from ...config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/modules/config")
async def get_modules_config():
    """Proxy to AI service: get all 6 AI module configs (scene, yolo, ocr, clip, whisper, diarization)."""
    import httpx
    ai_url = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ai_url}/config")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Failed to get module configs from AI service: %s", e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

@router.post("/modules/config")
async def save_modules_config(data: dict):
    """Proxy to AI service: save all AI module configs."""
    import httpx
    ai_url = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{ai_url}/config", json=data)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Failed to save module configs to AI service: %s", e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

@router.get("/modules/config/{module}")
async def get_single_module_config(module: str):
    """Proxy to AI service: get a single module config by name."""
    import httpx
    ai_url = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ai_url}/config/{module}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Failed to get module config '%s' from AI service: %s", module, e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

@router.post("/modules/config/{module}")
async def save_single_module_config(module: str, data: dict):
    """Proxy to AI service: save a single module config by name."""
    import httpx
    ai_url = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{ai_url}/config/{module}", json=data)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Failed to save module config '%s' to AI service: %s", module, e)
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

