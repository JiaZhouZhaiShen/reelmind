"""HTTP proxy to AI container — Server never imports AI code directly.

铁律 ①: Server only forwards, never computes.
铁律 ⑥: No import of ai_service packages.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AI_BASE_URL = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")
_POLL_INTERVAL = 2.0  # seconds between status checks
_DEFAULT_TIMEOUT = 180 * 60  # 180 minutes max for a batch


def start_pipeline(
    limit: int = 10,
    engines: list[str] | None = None,
    video_ids: list[str] | None = None,
    task_label: str = "manual",
    filters: dict | None = None,
) -> dict[str, Any]:
    """POST /pipeline/start → returns task_id."""
    payload: dict[str, Any] = {"limit": limit}
    if engines is not None:
        payload["engines"] = engines
    if video_ids is not None:
        payload["video_ids"] = video_ids
    payload["task_label"] = task_label
    if filters is not None:
        payload["filters"] = filters

    try:
        resp = httpx.post(
            f"{AI_BASE_URL}/pipeline/start",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.RequestError as e:
        logger.error("start_pipeline HTTP request failed: %s", e)
        return {"task_id": None, "error": str(e)}


def get_pipeline_status(task_id: str) -> dict[str, Any]:
    """GET /pipeline/status/{task_id}."""
    try:
        resp = httpx.get(
            f"{AI_BASE_URL}/pipeline/status/{task_id}",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"status": "not_found"}
        logger.error("get_pipeline_status HTTP error: %s", e)
        return {"status": "error", "error": str(e)}
    except httpx.RequestError as e:
        logger.error("get_pipeline_status request failed: %s", e)
        return {"status": "error", "error": str(e)}


def wait_for_completion(
    task_id: str,
    poll_interval: float | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Poll /pipeline/status until completed, error, or timeout.

    Returns the final status dict.  On timeout returns {"status": "timeout"}.
    """
    interval = poll_interval or _POLL_INTERVAL
    deadline = time.time() + (timeout or _DEFAULT_TIMEOUT)

    while time.time() < deadline:
        status = get_pipeline_status(task_id)
        st = status.get("status")
        if st in ("completed", "error", "cancelled", "not_found"):
            return status
        time.sleep(interval)

    logger.warning("wait_for_completion timed out for task %s", task_id)
    return {"status": "timeout", "task_id": task_id}


def get_gpu_health() -> dict[str, Any]:
    """GET /health — GPU status (used by orchestrator condition check)."""
    try:
        resp = httpx.get(f"{AI_BASE_URL}/health", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.RequestError as e:
        logger.warning("get_gpu_health failed: %s", e)
        return {"status": "unreachable", "gpu": False, "total_gb": 0, "total_used_gb": 0}
