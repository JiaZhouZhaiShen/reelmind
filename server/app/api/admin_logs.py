"""Admin Logs API — container-aware log aggregation using log_service.

Follows the REELMIND principle: server proxies/aggregates, does not compute.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
try:
    from .docker_api import DockerAPI
except Exception:
    DockerAPI = None  # docker.sock not available
from ..services.log_service import (
    list_sources,
    fetch_logs,
    search_logs,
    stream_logs,
    LogEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/logs", tags=["Admin Logs"])


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Reuse admin-only auth guard."""
    from .admin import require_admin as _ra
    return await _ra(current_user=current_user)


# ── Source listing ────────────────────────────────────────────────────────


@router.get("/sources")
async def get_log_sources(
    _: dict = Depends(require_admin),
):
    """List all available log sources (Docker containers + file logs)."""
    try:
        sources = await list_sources()
        return {
            "sources": [
                {
                    "id": s.id,
                    "label": s.label,
                    "type": s.type,
                    "status": s.status,
                    "has_logs": s.has_logs,
                }
                for s in sources
            ]
        }
    except Exception as e:
        logger.error("Failed to list log sources: %s", e, exc_info=True)
        return {"sources": [], "error": str(e)}


# ── Log fetching ──────────────────────────────────────────────────────────


@router.get("/source/{source_id}")
async def get_source_logs(
    source_id: str,
    tail: int = Query(200, ge=0, le=5000),
    search: str | None = Query(None),
    level: str | None = Query(None),
    _: dict = Depends(require_admin),
):
    """Fetch logs from a specific source with optional filtering."""
    try:
        result = await fetch_logs(source_id, tail=tail, search=search, level=level)
        return {
            "source": result.source,
            "total_lines": result.total_lines,
            "truncated": result.truncated,
            "docker_available": result.docker_available,
            "lines": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "logger": e.logger,
                    "message": e.message,
                    "raw": e.raw,
                }
                for e in result.lines
            ],
        }
    except Exception as e:
        logger.error("Failed to fetch logs for '%s': %s", source_id, e, exc_info=True)
        return {
            "source": source_id,
            "lines": [],
            "total_lines": 0,
            "truncated": False,
            "error": str(e),
        }


# ── Cross-source search ───────────────────────────────────────────────────


@router.get("/search")
async def search_across_logs(
    q: str = Query(..., min_length=1),
    sources: str | None = Query(None, description="Comma-separated source IDs"),
    tail: int = Query(50, ge=10, le=1000),
    _: dict = Depends(require_admin),
):
    """Search across all log sources for a given query string."""
    try:
        source_list = sources.split(",") if sources else None
        results = await search_logs(query=q, sources=source_list, tail=tail)
        return {"query": q, "results": results}
    except Exception as e:
        logger.error("Search logs failed: %s", e, exc_info=True)
        return {"query": q, "results": [], "error": str(e)}


# ── SSE streaming ─────────────────────────────────────────────────────────


@router.get("/stream/{source_id}")
async def stream_source_logs(
    source_id: str,
    _: dict = Depends(require_admin),
):
    """SSE stream of real-time logs from a Docker container."""
    return StreamingResponse(
        stream_logs(source_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/diagnostics")
async def get_diagnostics(
    _: dict = Depends(require_admin),
):
    """Aggregate ERROR logs across all sources + container health."""
    import asyncio
    try:
        sources = await list_sources()
        docker_sources = [s for s in sources if s.type == "docker"]

        error_counts = {}
        top_error_counter = {}
        recent_errors = []
        container_health = {}

        for src in docker_sources:
            container_health[src.id] = src.status
            try:
                result = await fetch_logs(src.id, tail=200, level="ERROR")
                if result.lines:
                    error_counts[src.id] = len(result.lines)
                    for entry in result.lines:
                        msg = (entry.message or "")[:120]
                        if msg:
                            top_error_counter[msg] = top_error_counter.get(msg, 0) + 1
                        recent_errors.append({
                            "source": src.id,
                            "timestamp": entry.timestamp,
                            "level": entry.level,
                            "message": entry.message,
                        })
                else:
                    error_counts[src.id] = 0
            except Exception as e:
                logger.warning("Diagnostics fetch failed for %s: %s", src.id, e)
                error_counts[src.id] = -1

        recent_errors.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        recent_errors = recent_errors[:50]

        top_errors = sorted(
            [{"message": k, "count": v} for k, v in top_error_counter.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:20]

        container_details = {}
        try:
            if DockerAPI is not None:
                api = DockerAPI()
                loop = asyncio.get_event_loop()
                containers = await loop.run_in_executor(None, api.list_containers)
                for c in containers[:20]:
                    names = c.get("Names", [])
                    name = names[0].lstrip("/") if names else "?"
                    container_details[name] = {
                        "state": c.get("State", "?"),
                        "status": c.get("Status", "?"),
                        "id": c.get("Id", "")[:12],
                    }
        except Exception as e:
            logger.warning("Could not fetch container details: %s", e)

        return {
            "error_counts": error_counts,
            "top_errors": top_errors,
            "recent_errors": recent_errors,
            "container_health": container_health,
            "container_details": container_details,
            "total_docker_sources": len(docker_sources),
        }
    except Exception as e:
        logger.error("Diagnostics failed: %s", e, exc_info=True)
        return {
            "error_counts": {},
            "top_errors": [],
            "recent_errors": [],
            "container_health": {},
            "container_details": {},
            "error": str(e),
        }
