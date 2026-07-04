"""Scan SSE event streaming and event scanner."""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...config import settings
from .shared import _orchestrate_batch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/scan-events")
async def scan_events_sse():
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
                        data = event.data or {}
                        media_ids = data.get("media_ids", [])
                        batch_id = data.get("batch_id") or str(event.batch_id or "")
                        if not media_ids:
                            event.consumed = True
                            continue
                        auto_config = get_auto_config()
                        if not auto_config.get("enabled", False):
                            event.consumed = True
                            logger.info(
                                "Event scanner: auto mode disabled, consuming event %s",
                                event.id,
                            )
                            continue
                        logger.info(
                            "Event scanner: dispatching chunk batch=%s media_ids=%d",
                            batch_id, len(media_ids),
                        )
                        threading.Thread(
                            target=_orchestrate_batch,
                            args=("auto", auto_config, None, media_ids, event.id),
                            daemon=True,
                        ).start()
                    session.commit()
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
