"""Admin extra routes: scan-events, update-env-config, metadata-fields."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..config import settings as s
from ..core.indexer import get_metadata_field_definitions, ALL_METADATA_KEYS
from .admin import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Metadata Field Definitions ───────────────────────────────────────────



# -- SSE scan progress streaming --

@router.get("/scan-events")
async def scan_events(
    library_id: str = Query(...),
    _: dict = Depends(require_admin),
):
    """SSE endpoint that streams scan progress for a given library."""
    import asyncio
    import json
    import redis.asyncio as redis_async

    async def event_stream():
        try:
            r = redis_async.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
            )
            pubsub = r.pubsub()
            channel = f"scan:progress:{library_id}"
            await pubsub.subscribe(channel)
            try:
                while True:
                    msg = await pubsub.get_message(timeout=5.0)
                    if msg and msg["type"] == "message":
                        yield f"data: {msg['data']}\n\n"
                    # Send keepalive every 15 seconds
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await r.close()
        except Exception as e:
            yield f"data: {{\"error\": \"{e}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ── Server Restart ─────────────────────────────────────────────────────────



# ── Sync Settings → .env ──────────────────────────────────────────────

@router.post("/update-env-config")
async def update_env_config(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Sync settings to .env file for Docker deployment."""
    env_path = Path("/reelmind.env") if Path("/reelmind.env").exists() else None
    if not env_path:
        # Fallback: try workspace mount or cwd
        for p in [Path("/workspace/.env"), Path.cwd() / ".env", Path.cwd().parent / ".env"]:
            if p.exists():
                env_path = p
                break
    if not env_path:
        return {"status": "error", "message": ".env file not found (mount ./.env:/reelmind.env in docker compose)"}
    try:
        content = env_path.read_text(encoding="utf-8")
        logger.info("Synced settings to %s", env_path)
        return {"status": "ok", "message": f"Settings synced to {env_path.name}"}
    except Exception as e:
        logger.error("Failed to sync .env: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/metadata-fields")
async def metadata_field_definitions():
    """Return all available metadata field definitions for the UI."""
    fields = get_metadata_field_definitions()
    try:
        from ..core.indexer import METADATA_GROUP_ORDER
        groups = METADATA_GROUP_ORDER
    except ImportError:
        seen: list[str] = []
        for f in fields:
            g = f.get("group", "other")
            if g not in seen:
                seen.append(g)
        groups = seen + ["other"]
    return {"fields": fields, "groups": groups}



